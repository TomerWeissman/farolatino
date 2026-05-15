"""Tests for the Gemini auto-fallback behavior.

The Gemini provider chains models (gemini-2.5-flash → gemini-2.0-flash) so
that a user whose Google Cloud project happens to have free-tier credit
on only one of them gets a working chat without manual intervention.

We test three properties:
  1. On the "limit: 0" quota error, the provider transparently retries
     the request with the next model in the chain.
  2. The winning model is cached per API key so subsequent provider
     instances skip the failing probe.
  3. FAROAI_GEMINI_MODEL pins one model and disables fallback (so explicit
     user choice is honored exactly).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from google.genai import errors as genai_errors

from core.llm import gemini_provider as gp
from core.llm.gemini_provider import GeminiProvider


def _make_quota_error() -> genai_errors.APIError:
    """The exact 'project has zero free-tier credit for this model' error
    shape (RESOURCE_EXHAUSTED + 'limit: 0' in the message)."""
    return genai_errors.APIError(
        429,
        {
            "error": {
                "code": 429,
                "status": "RESOURCE_EXHAUSTED",
                "message": "Quota exceeded ... quota limit: 0 model: gemini-2.5-flash",
            }
        },
        None,
    )


def _make_rate_limit_error() -> genai_errors.APIError:
    """A transient rate limit — same code/status but limit > 0. We must
    NOT auto-fall back on this one (waiting is the right answer)."""
    return genai_errors.APIError(
        429,
        {
            "error": {
                "code": 429,
                "status": "RESOURCE_EXHAUSTED",
                "message": "Quota exceeded ... limit: 60 per minute",
            }
        },
        None,
    )


def _ok_stream(text: str = "hi"):
    """A minimal successful stream: one chunk, one text part, no tools."""
    chunk = SimpleNamespace(
        candidates=[
            SimpleNamespace(content=SimpleNamespace(parts=[SimpleNamespace(text=text, function_call=None)]))
        ],
        usage_metadata=SimpleNamespace(prompt_token_count=10, candidates_token_count=2),
    )
    return iter([chunk])


@pytest.fixture(autouse=True)
def _clear_cache():
    """Each test starts with an empty per-key model cache."""
    gp._working_model_cache.clear()
    yield
    gp._working_model_cache.clear()


@pytest.fixture
def _no_env(monkeypatch):
    """Disable any ambient FAROAI_GEMINI_MODEL override so the fallback
    chain is in effect."""
    monkeypatch.delenv("FAROAI_GEMINI_MODEL", raising=False)


def _run_provider(provider: GeminiProvider) -> list:
    """Drive the provider and return all yielded events."""
    return list(provider.run(
        messages=[{"role": "user", "content": "ping"}],
        tools=[],
        system="you are a test",
    ))


def test_falls_back_to_next_model_on_no_quota(_no_env):
    """First model returns 'limit: 0' → provider retries with the next
    model in the chain and surfaces the fallback model in the result."""
    # Sequence: 2.5-flash fails with no-quota, 2.0-flash succeeds.
    call_log: list[str] = []

    def fake_stream(*, model, contents, config):
        call_log.append(model)
        if model == "gemini-2.5-flash":
            raise _make_quota_error()
        return _ok_stream("hello from fallback")

    with patch.object(gp, "genai") as fake_genai:
        fake_genai.Client.return_value = SimpleNamespace(
            models=SimpleNamespace(generate_content_stream=fake_stream)
        )
        provider = GeminiProvider(api_key="AIzaTESTKEY1")
        events = _run_provider(provider)

    assert call_log == ["gemini-2.5-flash", "gemini-2.0-flash"]
    # The user-facing stream got text + a successful result (no error events).
    text_events = [e for e in events if e.type == "text"]
    result_events = [e for e in events if e.type == "result"]
    error_events = [e for e in events if e.type == "error"]
    assert text_events and text_events[0].content == "hello from fallback"
    assert result_events and result_events[0].content == "ok"
    assert result_events[0].extra == {"model": "gemini-2.0-flash"}
    assert not error_events


def test_caches_winning_model_per_key(_no_env):
    """Once a model has worked for a given key, a new provider instance
    starts from that model directly (no failing probe)."""
    call_log: list[str] = []

    def fake_stream(*, model, contents, config):
        call_log.append(model)
        if model == "gemini-2.5-flash":
            raise _make_quota_error()
        return _ok_stream()

    with patch.object(gp, "genai") as fake_genai:
        fake_genai.Client.return_value = SimpleNamespace(
            models=SimpleNamespace(generate_content_stream=fake_stream)
        )
        # First run: falls back, populates cache.
        _run_provider(GeminiProvider(api_key="AIzaTESTKEY2"))
        # Second run with the same key: should go straight to 2.0-flash.
        call_log.clear()
        _run_provider(GeminiProvider(api_key="AIzaTESTKEY2"))

    assert call_log == ["gemini-2.0-flash"], (
        "second run must skip the failing 2.5-flash probe"
    )


def test_env_override_disables_fallback(monkeypatch):
    """When FAROAI_GEMINI_MODEL is set, the provider honors it exactly and
    surfaces the quota error to the user instead of silently swapping."""
    monkeypatch.setenv("FAROAI_GEMINI_MODEL", "gemini-2.5-flash")
    call_log: list[str] = []

    def fake_stream(*, model, contents, config):
        call_log.append(model)
        raise _make_quota_error()

    with patch.object(gp, "genai") as fake_genai:
        fake_genai.Client.return_value = SimpleNamespace(
            models=SimpleNamespace(generate_content_stream=fake_stream)
        )
        events = _run_provider(GeminiProvider(api_key="AIzaTESTKEY3"))

    assert call_log == ["gemini-2.5-flash"], "no retry should happen when pinned"
    error_events = [e for e in events if e.type == "error"]
    assert error_events, "pinned model must surface the error, not swallow it"


def test_transient_rate_limit_does_not_fall_back(_no_env):
    """A 429 with a non-zero limit is a transient rate limit, not a quota
    misconfiguration. Falling back would mask the real signal + could
    shift cost tiers, so we surface the error instead."""
    call_log: list[str] = []

    def fake_stream(*, model, contents, config):
        call_log.append(model)
        raise _make_rate_limit_error()

    with patch.object(gp, "genai") as fake_genai:
        fake_genai.Client.return_value = SimpleNamespace(
            models=SimpleNamespace(generate_content_stream=fake_stream)
        )
        events = _run_provider(GeminiProvider(api_key="AIzaTESTKEY4"))

    assert call_log == ["gemini-2.5-flash"], (
        "transient rate limits must NOT trigger a model swap"
    )
    error_events = [e for e in events if e.type == "error"]
    assert error_events
    assert error_events[0].content == "Gemini rate-limited"
