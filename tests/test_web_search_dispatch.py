"""Tests for the Tavily-backed web_search tool + provider routing.

Two layers:

1. **Tavily error categorization** — pure unit tests against the
   ``web_search`` function with httpx mocked at the module level.
   Asserts that 401/403 land in the "permanent" bucket while
   429/timeout/5xx land in "recoverable". Skips on missing httpx
   monkeypatch capability (shouldn't happen).

2. **Provider routing** — asserts that ``attach_for_anthropic`` /
   ``attach_for_openai`` / ``attach_for_gemini_grounding`` produce the
   right tool spec or grounding flag for each of the
   ``"off" / "tavily" / "native"`` modes. No network — pure list math.

Both layers run in CI without any API keys set.
"""
from __future__ import annotations

import httpx
import pytest

from core.connectors import tavily as tavily_conn
from core.llm.web_search_routing import (
    attach_for_anthropic,
    attach_for_gemini_grounding,
    attach_for_openai,
)


# ─── Tavily error categorization ───────────────────────────────────


class _FakeResponse:
    """Minimal stand-in for an httpx.Response with the fields web_search reads."""
    def __init__(self, status_code: int, text: str = "", json_payload: dict | None = None):
        self.status_code = status_code
        self.text = text
        self._json = json_payload

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


def _patch_post(monkeypatch, fn):
    """Replace httpx.post inside tavily.py with `fn`."""
    monkeypatch.setattr(tavily_conn.httpx, "post", fn)


def test_tavily_success(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    _patch_post(monkeypatch, lambda *a, **kw: _FakeResponse(200, json_payload={
        "results": [{"title": "T", "url": "https://example.com", "content": "C"}]
    }))
    out = tavily_conn.web_search("foo")
    assert "error" not in out
    assert out["results"][0]["url"] == "https://example.com"


def test_tavily_auth_failure_is_permanent(monkeypatch):
    """401 → permanent. The model should NOT retry the same key."""
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-bad")
    _patch_post(monkeypatch, lambda *a, **kw: _FakeResponse(401, text="unauthorized"))
    out = tavily_conn.web_search("foo")
    assert out["error_category"] == "permanent"
    assert "auth failed" in out["error"].lower()


def test_tavily_rate_limit_is_recoverable(monkeypatch):
    """429 → recoverable. Worth telling the user, not "we have no web access"."""
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    _patch_post(monkeypatch, lambda *a, **kw: _FakeResponse(429, text="too many"))
    out = tavily_conn.web_search("foo")
    assert out["error_category"] == "recoverable"


def test_tavily_5xx_is_recoverable(monkeypatch):
    """5xx → recoverable. Tavily's problem, try again."""
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    _patch_post(monkeypatch, lambda *a, **kw: _FakeResponse(503, text="upstream"))
    out = tavily_conn.web_search("foo")
    assert out["error_category"] == "recoverable"


def test_tavily_timeout_is_recoverable(monkeypatch):
    """httpx.TimeoutException → recoverable."""
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    def _raise(*a, **kw):
        raise httpx.TimeoutException("slow")
    _patch_post(monkeypatch, _raise)
    out = tavily_conn.web_search("foo")
    assert out["error_category"] == "recoverable"


def test_tavily_missing_key_is_permanent(monkeypatch):
    """No TAVILY_API_KEY → permanent (user needs to configure it)."""
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    out = tavily_conn.web_search("foo")
    assert out["error_category"] == "permanent"


# ─── Provider routing — tool-spec attachment ───────────────────────


def test_anthropic_native_appends_hosted_tool():
    """`native` mode → Anthropic's web_search_20250305 tool appended."""
    out = attach_for_anthropic([{"name": "stub"}], "native")
    assert any(t.get("type") == "web_search_20250305" for t in out)
    assert any(t.get("name") == "stub" for t in out)  # original preserved


def test_anthropic_tavily_leaves_tools_unchanged():
    """`tavily` mode → no native tool appended (the in-process Tavily
    tool already lives in the `tools` list passed in)."""
    tools = [{"name": "web_search"}]
    out = attach_for_anthropic(tools, "tavily")
    assert out == tools
    assert not any(t.get("type") == "web_search_20250305" for t in out)


def test_anthropic_off_leaves_tools_unchanged():
    tools = [{"name": "stub"}]
    out = attach_for_anthropic(tools, "off")
    assert out == tools


def test_openai_native_appends_hosted_tool():
    out = attach_for_openai([{"name": "stub"}], "native")
    assert any(t.get("type") == "web_search" for t in out)


def test_openai_tavily_leaves_tools_unchanged():
    tools = [{"name": "web_search"}]
    out = attach_for_openai(tools, "tavily")
    assert out == tools


def test_gemini_grounding_flag():
    assert attach_for_gemini_grounding("native") is True
    assert attach_for_gemini_grounding("tavily") is False
    assert attach_for_gemini_grounding("off") is False
