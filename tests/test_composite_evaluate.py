"""Tests for the composite evaluate_artist tool.

Verifies that the full pipeline (search → data → score → revenue → dossier
→ alert) chains correctly, the Insight kwargs bug stays fixed, and the
ambiguous-search short-circuit works.

Network is stubbed: search_artists / get_artist_data are monkey-patched to
return mock data so we don't hit Chartmetric.
"""
from __future__ import annotations

import json
from pathlib import Path

from mcp_server.models import build_artist
from mcp_server.tools import composite_evaluate
from mcp_server.tools.composite_evaluate import _is_url, _pick_unambiguous, evaluate_artist

MOCK_DIR = Path(__file__).parent / "mock_data"


def _load_mock(name: str) -> dict:
    return json.loads((MOCK_DIR / f"{name}.json").read_text())


def test_url_detection():
    assert _is_url("https://open.spotify.com/artist/123")
    assert _is_url("http://chartmetric.com/x")
    assert not _is_url("Bad Bunny")
    assert not _is_url("Dread Mar I")


def test_pick_unambiguous_dominant_top_hit():
    # Top has 100M followers, runner-up has 1k → top dominates.
    res = _pick_unambiguous({"artists": [
        {"cm_id": 1, "name": "Big", "sp_followers": 100_000_000},
        {"cm_id": 2, "name": "Small", "sp_followers": 1_000},
    ]})
    assert res is not None
    assert res["cm_id"] == 1


def test_pick_unambiguous_close_call_returns_none():
    # Top has 1M, runner-up has 800k → not dominant, ask user.
    res = _pick_unambiguous({"artists": [
        {"cm_id": 1, "name": "A", "sp_followers": 1_000_000},
        {"cm_id": 2, "name": "B", "sp_followers": 800_000},
    ]})
    assert res is None


def test_pick_unambiguous_single_match():
    res = _pick_unambiguous({"artists": [{"cm_id": 1, "name": "Solo", "sp_followers": 5000}]})
    assert res is not None and res["cm_id"] == 1


def test_pick_unambiguous_empty():
    assert _pick_unambiguous({"artists": []}) is None


def test_full_pipeline_happy_path(monkeypatch):
    """End-to-end: name → cm_id → data → score → revenue → dossier → alert."""
    artist_data = _load_mock("rising_colombian")

    monkeypatch.setattr(composite_evaluate, "search_artists", lambda q, limit=3: {
        "artists": [{"cm_id": 999, "name": artist_data.get("name", "Test"), "sp_followers": 100_000_000}],
    })
    monkeypatch.setattr(composite_evaluate, "get_artist_data", lambda cm_id, use_cache=True: artist_data)

    out = evaluate_artist("Rising Colombian Artist")

    assert "error" not in out, f"unexpected error: {out.get('error')}"
    assert "needs_disambiguation" not in out
    assert "dossier" in out
    assert "alert" in out
    assert out["cm_id"] == 999
    # Dossier shape
    assert "prospect_score" in out["dossier"]
    assert out["dossier"]["prospect_score"]["tier"] in {"HOT", "WARM", "WATCH", "PASS"}


def test_disambiguation_short_circuits(monkeypatch):
    """Two close-followers candidates → return needs_disambiguation; no data pull."""
    monkeypatch.setattr(composite_evaluate, "search_artists", lambda q, limit=3: {
        "artists": [
            {"cm_id": 1, "name": "Common A", "sp_followers": 1_000_000},
            {"cm_id": 2, "name": "Common B", "sp_followers": 900_000},
            {"cm_id": 3, "name": "Common C", "sp_followers": 100_000},
        ],
    })
    # If get_artist_data is called we want a noisy failure.
    def _should_not_fetch(*a, **k):
        raise AssertionError("get_artist_data should not be called for ambiguous search")
    monkeypatch.setattr(composite_evaluate, "get_artist_data", _should_not_fetch)

    out = evaluate_artist("Common Name")
    assert "needs_disambiguation" in out
    assert len(out["needs_disambiguation"]) == 3
    assert out["needs_disambiguation"][0]["cm_id"] == 1


def test_cm_id_skips_search(monkeypatch):
    """When cm_id is given, search must not run."""
    artist_data = _load_mock("rising_colombian")

    def _should_not_search(*a, **k):
        raise AssertionError("search_artists should not be called when cm_id is provided")
    monkeypatch.setattr(composite_evaluate, "search_artists", _should_not_search)
    monkeypatch.setattr(composite_evaluate, "get_artist_data", lambda cm_id, use_cache=True: artist_data)

    out = evaluate_artist("ignored-name", cm_id=42)
    assert out["cm_id"] == 42
    assert "dossier" in out


def test_insight_extra_kwargs_regression():
    """Regression for `Insight.__init__() got an unexpected keyword argument`.

    Previously, build_artist did `cls(**item)` blindly, so any extra key from
    Chartmetric (or a model-rewritten payload) blew up. After the fix, unknown
    keys must be silently dropped at both top-level and nested-list levels.
    """
    payload = {
        "name": "Test Artist",
        "cm_id": 1,
        "noteworthy_insights": [
            {"text": "spike", "type": "acceleration", "extra_unknown_key": "ignored", "priority": 5},
            {"text": "stable"},
        ],
        "milestones": [
            {"text": "first 100k", "date": "2024", "weird_chartmetric_field": "nope"},
        ],
        "brand_new_chartmetric_top_level_field": {"a": 1},
    }
    artist = build_artist(payload)  # must not raise
    assert artist.name == "Test Artist"
    assert len(artist.noteworthy_insights) == 2
    assert artist.noteworthy_insights[0].text == "spike"
    assert artist.milestones[0].text == "first 100k"
