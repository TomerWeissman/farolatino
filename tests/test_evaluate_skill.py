"""Tests for the @evaluate skill across LLM providers.

Two layers, both deliberate:

1. **Fast regression test** (no LLM, no network beyond Chartmetric).
   Directly invokes the dispatch path with the adversarial args that
   broke production on May 6 — GPT-4o filling the optional ``cm_id``
   parameter with ``0`` instead of omitting it. The composite skill
   used to short-circuit search on ``cm_id is not None``, so a 0
   skipped artist resolution and queried Chartmetric for ID 0,
   producing an empty dossier with score ~13/100. This test asserts
   we get a real dossier even when ``cm_id=0`` slips through.

2. **End-to-end provider tests** (live LLM call). Drives the full V2
   agent runner against the active provider and asserts the assistant's
   tool call returned a non-stub dossier. Skipped when the matching
   API key isn't set so the suite stays green offline + in CI.
   Run a single provider's test with::

       LLM_API_KEY=sk-ant-...    pytest -k anthropic
       LLM_API_KEY=sk-proj-...   pytest -k openai

   Each end-to-end run costs roughly $0.01-$0.05 depending on the
   provider and model.
"""
from __future__ import annotations

import json
import os
from typing import Any

import pytest

from core.agent_runner import THINKING_PREFIX, run_claude_streaming
from core.llm import detect_provider_name
from core.llm.tool_dispatch import dispatch

# Stable, well-known artist with rich Chartmetric data. Bad Bunny has
# been the canonical V1/V2 smoke artist since launch — millions of
# listeners across every platform, never disambiguates to anything else.
REGRESSION_ARTIST = "Bad Bunny"
# Empty-dossier stub scores ~13/100. Real artists with millions of
# listeners come back well above 30. Gives margin without being so
# loose that a regression to "no streaming data, partial geo" passes.
MIN_REAL_DOSSIER_SCORE = 30


# ─── Fast regression test (no LLM) ──────────────────────────────────────


def test_evaluate_dispatch_with_cm_id_zero_falls_through_to_search():
    """The May-6 production regression.

    GPT-4o emits ``cm_id: 0`` for the optional ``int | None`` parameter
    instead of omitting it. The fix lives in ``composite_evaluate.py``:
    treat any falsy ``cm_id`` as missing so the search path runs.
    Without the fix, this test sees ``score ~13`` (empty dossier).
    """
    result = dispatch(
        "mcp__farolatino__evaluate_artist",
        {"artist": REGRESSION_ARTIST, "profile_name": "default", "cm_id": 0},
    )
    assert "error" not in result, f"dispatch returned an error: {result.get('error')!r}"
    assert "dossier" in result, f"missing dossier; got keys {list(result)}"

    score = (
        result["dossier"]
        .get("prospect_score", {})
        .get("overall")
    )
    assert score is not None, "dossier produced no overall"
    assert score >= MIN_REAL_DOSSIER_SCORE, (
        f"@evaluate {REGRESSION_ARTIST!r} returned an empty-stub dossier "
        f"(score={score}). The cm_id=0 short-circuit is back."
    )


def test_evaluate_dispatch_with_cm_id_missing_works():
    """Sanity check: the canonical happy path (no cm_id) still works.
    Regression-protects against a future overcorrection that breaks the
    common case.
    """
    result = dispatch(
        "mcp__farolatino__evaluate_artist",
        {"artist": REGRESSION_ARTIST},
    )
    assert "error" not in result
    assert "dossier" in result
    score = result["dossier"]["prospect_score"]["overall"]
    assert score >= MIN_REAL_DOSSIER_SCORE


# ─── Provider end-to-end tests (live LLM) ───────────────────────────────


def _has_provider_key(provider: str) -> bool:
    """Detect whether the configured key matches the named provider.

    We check ``LLM_API_KEY`` first (V2 single-key UX), then the legacy
    per-provider env vars. Returns True only when the active provider
    matches ``provider`` so we never spend an Anthropic key on the
    OpenAI test (or vice-versa).
    """
    if detect_provider_name() == provider:
        return True
    return False


def _capture_evaluate_run(prompt: str) -> dict:
    """Drive ``run_claude_streaming`` and return the captured trace.

    Collects assembled response text, every tool call's name + raw
    output (via the on_event hook), and the final cost. Lets
    individual tests assert exactly what they care about.
    """
    text_parts: list[str] = []
    thinking_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    tool_results: list[dict[str, Any]] = []
    final_cost: dict[str, Any] = {}

    def on_event(event: dict) -> None:
        etype = event.get("type")
        if etype == "assistant":
            for block in (event.get("message") or {}).get("content") or []:
                if block.get("type") == "tool_use":
                    tool_calls.append(
                        {"name": block.get("name"), "input": block.get("input")}
                    )
        elif etype == "user":
            for block in (event.get("message") or {}).get("content") or []:
                if block.get("type") == "tool_result":
                    raw = block.get("content")
                    parsed: Any
                    try:
                        parsed = json.loads(raw) if isinstance(raw, str) else raw
                    except (TypeError, ValueError):
                        parsed = raw
                    tool_results.append(
                        {"tool_name": block.get("tool_name"), "output": parsed}
                    )
        elif etype == "result":
            final_cost.update(
                {
                    "cost_usd": event.get("total_cost_usd"),
                    "input_tokens": event.get("input_tokens"),
                    "output_tokens": event.get("output_tokens"),
                }
            )

    for chunk in run_claude_streaming(prompt, on_event=on_event, messages=[]):
        if chunk.startswith(THINKING_PREFIX):
            thinking_parts.append(chunk[len(THINKING_PREFIX) :])
        else:
            text_parts.append(chunk)

    return {
        "text": "".join(text_parts),
        "thinking": "".join(thinking_parts),
        "tool_calls": tool_calls,
        "tool_results": tool_results,
        "cost": final_cost,
    }


def _assert_evaluate_dossier_is_real(trace: dict) -> None:
    """Common assertions every provider's @evaluate run must satisfy.

    Verifies the runner actually called the evaluate tool, the tool
    returned a populated dossier (not the cm_id=0 stub), and the
    visible response mentions the artist by name. Failure messages
    point at which assumption broke so a single test failure tells you
    whether the bug is in dispatch / schema / model behaviour.
    """
    tool_names = [t["name"] for t in trace["tool_calls"]]
    assert "mcp__farolatino__evaluate_artist" in tool_names, (
        f"runner never called the evaluate tool. Tools used: {tool_names}"
    )

    evaluate_results = [
        t for t in trace["tool_results"]
        if t.get("tool_name") == "mcp__farolatino__evaluate_artist"
    ]
    assert evaluate_results, (
        "evaluate_artist was called but no tool_result was captured. "
        "Check that on_event is forwarding tool_result events."
    )

    output = evaluate_results[-1]["output"]
    assert isinstance(output, dict), f"tool output is not a dict: {output!r}"
    assert "error" not in output, f"tool returned error: {output['error']!r}"
    assert "dossier" in output, (
        f"tool output missing dossier. Keys: {list(output)}. "
        f"This is the cm_id=0 regression — check composite_evaluate."
    )

    score = output["dossier"]["prospect_score"]["overall"]
    assert score >= MIN_REAL_DOSSIER_SCORE, (
        f"dossier score {score} is below {MIN_REAL_DOSSIER_SCORE}; "
        f"likely an empty-data stub. Output snippet: "
        f"{json.dumps(output['dossier'].get('metrics', {}))[:200]}"
    )

    # Final visible text should at least mention the artist — guards
    # against a "tool called but model output is empty" failure mode.
    assert REGRESSION_ARTIST.lower() in trace["text"].lower(), (
        f"assistant response doesn't mention {REGRESSION_ARTIST}. "
        f"First 300 chars: {trace['text'][:300]!r}"
    )


@pytest.mark.skipif(
    not _has_provider_key("anthropic"),
    reason="Anthropic key not configured (set LLM_API_KEY=sk-ant-...)",
)
def test_evaluate_skill_via_anthropic():
    trace = _capture_evaluate_run(f"@evaluate {REGRESSION_ARTIST}")
    _assert_evaluate_dossier_is_real(trace)


@pytest.mark.skipif(
    not _has_provider_key("openai"),
    reason="OpenAI key not configured (set LLM_API_KEY=sk-...)",
)
def test_evaluate_skill_via_openai():
    trace = _capture_evaluate_run(f"@evaluate {REGRESSION_ARTIST}")
    _assert_evaluate_dossier_is_real(trace)


@pytest.mark.skipif(
    not _has_provider_key("gemini"),
    reason="Gemini key not configured (set LLM_API_KEY=AIza...)",
)
def test_evaluate_skill_via_gemini():
    trace = _capture_evaluate_run(f"@evaluate {REGRESSION_ARTIST}")
    _assert_evaluate_dossier_is_real(trace)
