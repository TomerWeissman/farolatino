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
from datetime import date, timedelta
from typing import Any

import pytest

from core.agent_runner import THINKING_PREFIX, run_claude_streaming
from core.cadence import compute_release_cadence
from core.llm import detect_provider_name
from core.llm.tool_dispatch import dispatch
from mcp_server.models import Album, ArtistProfile
from mcp_server.tools.scoring.bot_detection import assess_bot_risk
from mcp_server.tools.signing_check import verify_signing_status
from mcp_server.tools.spotify_search import _avg_features

# Stable, well-known artist with rich Chartmetric data. Bad Bunny has
# been the canonical V1/V2 smoke artist since launch — millions of
# listeners across every platform, never disambiguates to anything else.
REGRESSION_ARTIST = "Bad Bunny"
# Empty-dossier stub scores ~13/100. Real artists with millions of
# listeners come back well above 30. Gives margin without being so
# loose that a regression to "no streaming data, partial geo" passes.
MIN_REAL_DOSSIER_SCORE = 30


# ─── v0.5.0 unit tests — cadence + audio-feature averaging ─────────────


def test_release_cadence_accelerating():
    """Cadence trend: 6m gaps tighter than 12m → accelerating."""
    today = date(2026, 5, 1)
    # 12m window: releases every ~60 days; 6m window: every ~14 days.
    dates_12m = [(today - timedelta(days=60 * i)).isoformat() for i in range(6, 0, -1)]
    dates_6m = [(today - timedelta(days=14 * i)).isoformat() for i in range(10, 0, -1)]
    out = compute_release_cadence(dates_12m + dates_6m, today=today)
    assert out["trend"] == "accelerating", out
    assert out["days_since_latest"] is not None
    assert out["cadence_days_6m"] is not None
    assert out["cadence_days_12m"] is not None
    assert out["cadence_days_6m"] < out["cadence_days_12m"]


def test_release_cadence_decelerating():
    """Cadence trend: 6m gaps much wider than 12m → decelerating."""
    today = date(2026, 5, 1)
    # Dense releases in months 7-12 (every 30 days), then a long gap.
    dates_old = [(today - timedelta(days=185 + 30 * i)).isoformat() for i in range(7)]
    # Only two releases inside the 6m window, spaced ~160 days apart.
    dates_recent = [
        (today - timedelta(days=170)).isoformat(),
        (today - timedelta(days=10)).isoformat(),
    ]
    out = compute_release_cadence(dates_old + dates_recent, today=today)
    assert out["trend"] == "decelerating", out
    assert out["cadence_days_6m"] > out["cadence_days_12m"]


def test_release_cadence_steady():
    """Cadence trend: comparable 6m vs 12m gaps → steady."""
    today = date(2026, 5, 1)
    # Even 30-day spacing across both windows.
    dates = [(today - timedelta(days=30 * i)).isoformat() for i in range(11, 0, -1)]
    out = compute_release_cadence(dates, today=today)
    assert out["trend"] == "steady", out


def test_release_cadence_empty_input():
    """No dates → all-None numerics + steady trend (silent degrade)."""
    out = compute_release_cadence([])
    assert out["latest_date"] is None
    assert out["days_since_latest"] is None
    assert out["cadence_days_6m"] is None
    assert out["cadence_days_12m"] is None
    assert out["trend"] == "steady"


def test_sound_profile_averaging():
    """Five audio-feature dicts average correctly across each metric."""
    features = [
        {"id": "a", "danceability": 0.90, "energy": 0.80, "tempo": 96.0},
        {"id": "b", "danceability": 0.92, "energy": 0.78, "tempo": 92.0},
        {"id": "c", "danceability": 0.88, "energy": 0.82, "tempo": 100.0},
        {"id": "d", "danceability": 0.94, "energy": 0.76, "tempo": 88.0},
        {"id": "e", "danceability": 0.86, "energy": 0.84, "tempo": 94.0},
    ]
    avg = _avg_features(features)
    assert avg["sample_size"] == 5
    assert abs(avg["danceability"] - 0.90) < 0.001
    assert abs(avg["energy"] - 0.80) < 0.001
    assert abs(avg["tempo"] - 94.0) < 0.001


def test_bot_detection_high_risk_signature():
    """Three firing signals → composite level "high"."""
    artist = ArtistProfile(
        name="Suspicious Test Artist",
        sp_monthly_listeners=800_000,
        sp_followers=30_000,
        sp_followers_to_listeners_ratio=0.04,  # signal 1: < 0.05 on > 10K listeners
        sp_monthly_listeners_diff_pct=350.0,   # signal 2a: huge listener spike
        sp_followers_diff_pct=8.0,             # signal 2b: flat followers → divergence
        yt_subscribers=5_000,                   # signal 5a
        tiktok_followers=10_000,                # signal 5b
    )
    yt_videos = []  # no YT data → signals 3, 4 don't fire
    out = assess_bot_risk(artist, yt_videos)
    assert out["level"] == "high", out
    # signals 1, 2, 5 should all fire
    assert len(out["reasons"]) >= 3
    assert out["score"] <= 50


def test_bot_detection_clean_artist():
    """Healthy metrics → no signals fire, level stays low."""
    artist = ArtistProfile(
        name="Clean Test Artist",
        sp_monthly_listeners=2_000_000,
        sp_followers=400_000,
        sp_followers_to_listeners_ratio=0.20,
        sp_monthly_listeners_diff_pct=15.0,
        sp_followers_diff_pct=10.0,
        yt_subscribers=500_000,
        tiktok_followers=300_000,
    )
    out = assess_bot_risk(artist, [])
    assert out["level"] == "low"
    assert out["reasons"] == []
    assert out["score"] == 100


def test_signing_check_major_label_verified():
    """record_label matches a major → signed_major + high confidence."""
    artist = ArtistProfile(
        name="Bad Bunny Test",
        record_label="Rimas",
        albums=[Album(name="Test Album", release_date="2026-01-01", album_type="album", track_count=12)],
    )
    out = verify_signing_status(artist)
    assert out["verified_status"] == "signed_major"
    assert out["confidence"] == "high"
    assert out["discrepancy"] is False
    assert "rimas" in out["label_display"].lower()


def test_signing_check_discrepancy_flag():
    """No record_label + no album label evidence → unknown.
    When chartmetric_flag (via record_label presence) is None, we
    classify as unknown without a discrepancy.
    """
    artist = ArtistProfile(
        name="Mystery Artist",
        record_label=None,
        albums=[],
    )
    out = verify_signing_status(artist)
    # No CM signed flag and no album evidence → unknown
    assert out["verified_status"] in ("unknown", "self_released")


def test_signing_check_self_released():
    """Empty/self label → self_released."""
    artist = ArtistProfile(
        name="Indie Test",
        record_label="Independent",
        albums=[Album(name="EP", release_date="2025-12-01", album_label="Independent", album_type="ep", track_count=4)],
    )
    out = verify_signing_status(artist)
    assert out["verified_status"] in ("self_released", "unknown")


def test_sound_profile_averaging_skips_missing():
    """A partial response (one track missing tempo) shouldn't crash."""
    features = [
        {"id": "a", "danceability": 0.9, "energy": 0.8, "tempo": 100.0},
        {"id": "b", "danceability": 0.8, "energy": 0.7},  # missing tempo
    ]
    avg = _avg_features(features)
    assert "danceability" in avg
    assert "energy" in avg
    assert avg["tempo"] == 100.0


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

    Verifies the runner called the evaluate tool, the tool returned a
    populated dossier (not the cm_id=0 stub), and the visible response
    is the canonical server-rendered Markdown — identical regardless of
    LLM provider, since V2 bypasses the LLM for this skill.
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

    # The dossier is server-rendered, so the visible response MUST
    # contain the canonical headers — not LLM-paraphrased prose. These
    # are structural anchors the Option B renderer always emits.
    # Updated when the renderer flipped from "Prospect score:" header
    # to the inline score line.
    text = trace["text"]
    canonical_markers = [
        f"# {REGRESSION_ARTIST}",
        "/100",  # the score is rendered as `**N**/100`
        "Annual gross (BRUTO)",
        "## Reach",
    ]
    for marker in canonical_markers:
        assert marker in text, (
            f"visible response is missing canonical marker {marker!r} — "
            f"the LLM may be paraphrasing instead of relaying the "
            f"server-rendered dossier verbatim. First 300 chars: "
            f"{text[:300]!r}"
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


def test_similar_output_is_provider_independent(monkeypatch):
    """``@similar`` output must also be byte-identical across providers.
    Same rationale as ``test_evaluate_output_is_provider_independent``."""
    captured: dict[str, str] = {}
    for provider in ("anthropic", "openai", "gemini"):
        monkeypatch.setenv("LLM_API_KEY", {
            "anthropic": "sk-ant-fake-test-key",
            "openai": "sk-fake-test-key",
            "gemini": "AIzaFakeTestKey",
        }[provider])
        trace = _capture_evaluate_run(f"@similar {REGRESSION_ARTIST}")
        captured[provider] = trace["text"]

    a, o, g = captured["anthropic"], captured["openai"], captured["gemini"]
    assert a == o, (
        "Anthropic and OpenAI produced different @similar output. "
        f"  anthropic: {a[:200]!r}\n  openai:    {o[:200]!r}"
    )
    assert a == g, "Anthropic and Gemini produced different @similar output."


def test_evaluate_output_is_provider_independent(monkeypatch):
    """V2 lifts dossier rendering server-side, so the visible chat
    response is byte-identical regardless of which LLM provider is
    configured. This test pretends to be each provider in turn (no
    real LLM call — the runner sees the @evaluate prefix and bypasses
    the LLM path entirely) and asserts the rendered Markdown matches
    exactly.

    Without this guarantee, the model's prose framing differs by
    provider, which is what the user spotted on May 6 ("each LLM
    produces the same thing").
    """
    captured: dict[str, str] = {}
    for provider in ("anthropic", "openai", "gemini"):
        # Force the registry to think the matching key is set so
        # detect_provider_name() returns this provider. The skill
        # bypass triggers BEFORE provider instantiation, so no real
        # SDK is touched.
        monkeypatch.setenv("LLM_API_KEY", {
            "anthropic": "sk-ant-fake-test-key",
            "openai": "sk-fake-test-key",
            "gemini": "AIzaFakeTestKey",
        }[provider])

        trace = _capture_evaluate_run(f"@evaluate {REGRESSION_ARTIST}")
        captured[provider] = trace["text"]

    # All three should render identically.
    a, o, g = captured["anthropic"], captured["openai"], captured["gemini"]
    assert a == o, (
        "Anthropic and OpenAI produced different @evaluate output. "
        "First diff context:\n"
        f"  anthropic: {a[:200]!r}\n  openai:    {o[:200]!r}"
    )
    assert a == g, (
        "Anthropic and Gemini produced different @evaluate output."
    )
