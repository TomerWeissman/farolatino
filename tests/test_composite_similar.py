"""Tests for the composite find_similar_artists tool."""
from __future__ import annotations

import json
from pathlib import Path

from mcp_server.tools import composite_similar
from mcp_server.tools.composite_similar import _tier_band, find_similar_artists

MOCK_DIR = Path(__file__).parent / "mock_data"


def _load_mock(name: str) -> dict:
    return json.loads((MOCK_DIR / f"{name}.json").read_text())


def test_tier_band_buckets():
    # Larger: 3x or more
    assert _tier_band(1_000_000, 3_000_000) == "larger"
    assert _tier_band(1_000_000, 5_000_000) == "larger"
    # Smaller: 1/3 or less
    assert _tier_band(1_000_000, 100_000) == "smaller"
    assert _tier_band(1_000_000, 333_000) == "smaller"
    # Tier-similar: between
    assert _tier_band(1_000_000, 800_000) == "tier-similar"
    assert _tier_band(1_000_000, 1_500_000) == "tier-similar"
    # Unknown when either side is zero
    assert _tier_band(0, 1_000_000) == "unknown"
    assert _tier_band(1_000_000, 0) == "unknown"


def test_full_path_with_neighbors(monkeypatch):
    """Synthesize an artist payload with neighbors and assert the response shape."""
    artist_data = {
        "name": "Seed Artist",
        "country_code": "AR",
        "career_stage": "developing",
        "genres": ["reggaeton", "trap"],
        "sp_monthly_listeners": 1_000_000,
        "neighboring_artists": [
            {"name": "Big One", "cm_id": 11, "country_code": "MX", "career_stage": "superstar",
             "sp_monthly_listeners": 50_000_000, "source": "neighbors"},
            {"name": "Peer A", "cm_id": 12, "country_code": "AR", "career_stage": "mainstream",
             "sp_monthly_listeners": 1_200_000, "source": "neighbors"},
            {"name": "Peer B", "cm_id": 13, "country_code": "CO", "career_stage": "mainstream",
             "sp_monthly_listeners": 900_000, "source": "neighbors"},
            {"name": "Tiny", "cm_id": 14, "country_code": "AR", "career_stage": "developing",
             "sp_monthly_listeners": 50_000, "source": "genre_search"},
        ],
    }

    monkeypatch.setattr(composite_similar, "search_artists", lambda q, limit=3: {
        "artists": [{"cm_id": 99, "name": "Seed Artist", "sp_followers": 100_000_000}],
    })
    monkeypatch.setattr(composite_similar, "get_artist_data", lambda cm_id, use_cache=True: artist_data)

    out = find_similar_artists("Seed Artist")

    assert "error" not in out
    assert "needs_disambiguation" not in out
    assert out["seed"]["name"] == "Seed Artist"
    assert len(out["neighbors"]) == 4

    bands = [n["tier_band"] for n in out["neighbors"]]
    assert bands == ["larger", "tier-similar", "tier-similar", "smaller"]

    assert out["tier_distribution"] == {
        "tier-similar": 2, "smaller": 1, "larger": 1, "unknown": 0,
    }
    assert "2 tier-similar" in out["summary"]


def test_disambiguation_short_circuits(monkeypatch):
    """Close-followers candidates → return needs_disambiguation; no data pull."""
    monkeypatch.setattr(composite_similar, "search_artists", lambda q, limit=3: {
        "artists": [
            {"cm_id": 1, "name": "A", "sp_followers": 1_000_000},
            {"cm_id": 2, "name": "B", "sp_followers": 950_000},
        ],
    })

    def _should_not_fetch(*a, **k):
        raise AssertionError("get_artist_data should not be called for ambiguous search")

    monkeypatch.setattr(composite_similar, "get_artist_data", _should_not_fetch)

    out = find_similar_artists("Common Name")
    assert "needs_disambiguation" in out
    assert len(out["needs_disambiguation"]) == 2


def test_cm_id_skips_search(monkeypatch):
    artist_data = _load_mock("rising_colombian")

    def _should_not_search(*a, **k):
        raise AssertionError("search_artists should not be called when cm_id is given")

    monkeypatch.setattr(composite_similar, "search_artists", _should_not_search)
    monkeypatch.setattr(composite_similar, "get_artist_data", lambda cm_id, use_cache=True: artist_data)

    out = find_similar_artists("ignored", cm_id=42)
    assert "seed" in out
    assert out["seed"]["cm_id"] == 42


def test_country_filter_drops_cross_country_neighbors(monkeypatch):
    """Bad Bunny seed (PR) should drop Justin Bieber (CA) and USHER (US),
    keep the PR/CO neighbors. Regression for the cross-genre noise we saw
    in the headless verification (Latin superstars next to global pop)."""
    artist_data = {
        "name": "Bad Bunny",
        "country_code": "PR",
        "sp_monthly_listeners": 100_000_000,
        "neighboring_artists": [
            {"name": "Justin Bieber", "cm_id": 1, "country_code": "CA", "sp_monthly_listeners": 95_000_000},
            {"name": "Anuel AA",      "cm_id": 2, "country_code": "PR", "sp_monthly_listeners": 50_000_000},
            {"name": "Daddy Yankee",  "cm_id": 3, "country_code": "PR", "sp_monthly_listeners": 40_000_000},
            {"name": "Wisin",         "cm_id": 4, "country_code": "PR", "sp_monthly_listeners": 25_000_000},
            {"name": "USHER",         "cm_id": 5, "country_code": "US", "sp_monthly_listeners": 30_000_000},
        ],
    }
    monkeypatch.setattr(composite_similar, "search_artists", lambda q, limit=3: {
        "artists": [{"cm_id": 214945, "name": "Bad Bunny", "sp_followers": 200_000_000}],
    })
    monkeypatch.setattr(composite_similar, "get_artist_data", lambda cm_id, use_cache=True: artist_data)

    out = find_similar_artists("Bad Bunny")
    assert out["country_filter_applied"] is True
    names = [n["name"] for n in out["neighbors"]]
    assert "Justin Bieber" not in names
    assert "USHER" not in names
    assert {"Anuel AA", "Daddy Yankee", "Wisin"}.issubset(set(names))
    assert out["seed"]["country_code"] == "PR"


def test_country_filter_falls_back_when_no_match(monkeypatch):
    """If the country cluster matches zero neighbors, return the unfiltered
    pool — better noisy results than empty results. (PR seed with only
    GB/JP/KR neighbors means there's no useful filter to apply.)"""
    artist_data = {
        "name": "PR superstar with global-only neighbors",
        "country_code": "PR",
        "sp_monthly_listeners": 50_000,
        "neighboring_artists": [
            {"name": "GB act", "cm_id": 11, "country_code": "GB", "sp_monthly_listeners": 5_000_000},
            {"name": "JP act", "cm_id": 12, "country_code": "JP", "sp_monthly_listeners": 5_000_000},
            {"name": "KR act", "cm_id": 13, "country_code": "KR", "sp_monthly_listeners": 5_000_000},
        ],
    }
    monkeypatch.setattr(composite_similar, "search_artists", lambda q, limit=3: {
        "artists": [{"cm_id": 999, "name": "PR superstar with global-only neighbors", "sp_followers": 1_000_000}],
    })
    monkeypatch.setattr(composite_similar, "get_artist_data", lambda cm_id, use_cache=True: artist_data)

    out = find_similar_artists("PR superstar with global-only neighbors")
    assert out["country_filter_applied"] is False  # fallback kicked in
    assert len(out["neighbors"]) == 3  # all kept


def test_country_cluster_includes_other_latin_markets(monkeypatch):
    """A PR seed should keep CO/MX/AR neighbors (Latin music cluster)
    and drop US/CA pop stars. Mirrors the real-world Bad Bunny case."""
    artist_data = {
        "name": "Bad Bunny",
        "country_code": "PR",
        "sp_monthly_listeners": 100_000_000,
        "neighboring_artists": [
            {"name": "Justin Bieber", "cm_id": 1, "country_code": "CA", "sp_monthly_listeners": 95_000_000},
            {"name": "Karol G",       "cm_id": 2, "country_code": "CO", "sp_monthly_listeners": 90_000_000},
            {"name": "Peso Pluma",    "cm_id": 3, "country_code": "MX", "sp_monthly_listeners": 27_000_000},
            {"name": "Trueno",        "cm_id": 4, "country_code": "AR", "sp_monthly_listeners": 10_000_000},
            {"name": "Taylor Swift",  "cm_id": 5, "country_code": "US", "sp_monthly_listeners": 95_000_000},
        ],
    }
    monkeypatch.setattr(composite_similar, "search_artists", lambda q, limit=3: {
        "artists": [{"cm_id": 214945, "name": "Bad Bunny", "sp_followers": 200_000_000}],
    })
    monkeypatch.setattr(composite_similar, "get_artist_data", lambda cm_id, use_cache=True: artist_data)

    out = find_similar_artists("Bad Bunny")
    assert out["country_filter_applied"] is True
    names = [n["name"] for n in out["neighbors"]]
    assert "Justin Bieber" not in names
    assert "Taylor Swift" not in names
    assert {"Karol G", "Peso Pluma", "Trueno"}.issubset(set(names))


def test_no_country_filter_when_seed_country_unknown(monkeypatch):
    artist_data = {
        "name": "X",
        "country_code": None,
        "sp_monthly_listeners": 1_000,
        "neighboring_artists": [
            {"name": "A", "cm_id": 100, "country_code": "US", "sp_monthly_listeners": 100},
            {"name": "B", "cm_id": 200, "country_code": "MX", "sp_monthly_listeners": 100},
        ],
    }
    monkeypatch.setattr(composite_similar, "search_artists", lambda q, limit=3: {
        # Seed cm_id different from neighbor cm_ids so the self-exclusion
        # filter doesn't drop neighbors.
        "artists": [{"cm_id": 999, "name": "X", "sp_followers": 100_000}],
    })
    monkeypatch.setattr(composite_similar, "get_artist_data", lambda cm_id, use_cache=True: artist_data)

    out = find_similar_artists("X")
    assert out["country_filter_applied"] is False
    assert len(out["neighbors"]) == 2


def test_self_excluded_from_neighbors(monkeypatch):
    """Chartmetric often returns the seed itself as its own first neighbor.
    We drop it so the user doesn't see 'Bad Bunny is similar to Bad Bunny'."""
    artist_data = {
        "name": "Bad Bunny",
        "country_code": "PR",
        "sp_monthly_listeners": 100_000_000,
        "neighboring_artists": [
            {"name": "Bad Bunny",  "cm_id": 214945, "country_code": "PR", "sp_monthly_listeners": 100_000_000},
            {"name": "Karol G",    "cm_id": 2, "country_code": "CO", "sp_monthly_listeners": 90_000_000},
            {"name": "Peso Pluma", "cm_id": 3, "country_code": "MX", "sp_monthly_listeners": 27_000_000},
        ],
    }
    monkeypatch.setattr(composite_similar, "search_artists", lambda q, limit=3: {
        "artists": [{"cm_id": 214945, "name": "Bad Bunny", "sp_followers": 200_000_000}],
    })
    monkeypatch.setattr(composite_similar, "get_artist_data", lambda cm_id, use_cache=True: artist_data)

    out = find_similar_artists("Bad Bunny")
    names = [n["name"] for n in out["neighbors"]]
    assert "Bad Bunny" not in names  # self-excluded
    assert "Karol G" in names


def test_limit_caps_neighbors(monkeypatch):
    artist_data = {
        "name": "X",
        "sp_monthly_listeners": 1_000_000,
        "neighboring_artists": [
            {"name": f"N{i}", "sp_monthly_listeners": 1_000_000} for i in range(30)
        ],
    }
    monkeypatch.setattr(composite_similar, "search_artists", lambda q, limit=3: {
        "artists": [{"cm_id": 1, "name": "X", "sp_followers": 999_999_999}],
    })
    monkeypatch.setattr(composite_similar, "get_artist_data", lambda cm_id, use_cache=True: artist_data)

    out = find_similar_artists("X", limit=5)
    assert len(out["neighbors"]) == 5
    out2 = find_similar_artists("X", limit=100)
    assert len(out2["neighbors"]) == 20  # hard cap
