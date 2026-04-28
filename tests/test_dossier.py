"""Tests for the dossier generator."""

import json
from pathlib import Path

import pytest

from mcp_server.tools.scoring.engine import compute_prospect_score
from mcp_server.tools.scoring.d3_revenue_potential import estimate_artist_revenue
from mcp_server.models import build_artist
from mcp_server.tools.dossier_generator import generate_dossier

MOCK_DIR = Path(__file__).parent / "mock_data"


def _load_mock(name: str) -> dict:
    return json.loads((MOCK_DIR / f"{name}.json").read_text())


def _full_dossier(name: str) -> dict:
    data = _load_mock(name)
    score = compute_prospect_score(data)
    artist = build_artist(data)
    revenue = estimate_artist_revenue(artist)
    return generate_dossier(data, score, revenue)


class TestDossierStructure:
    def test_has_all_sections(self):
        dossier = _full_dossier("rising_colombian")
        expected_sections = [
            "identity", "metrics", "prospect_score", "geographic_profile",
            "revenue_projection", "career_trajectory", "catalog",
            "risk_signals", "competitive_context", "actionable",
        ]
        for section in expected_sections:
            assert section in dossier, f"Missing section: {section}"

    def test_identity_populated(self):
        dossier = _full_dossier("rising_colombian")
        identity = dossier["identity"]
        assert identity["name"] == "Valentina Reyes"
        assert len(identity["genres"]) > 0
        assert identity["career_stage"] == "developing"

    def test_metrics_has_platforms(self):
        dossier = _full_dossier("rising_colombian")
        metrics = dossier["metrics"]
        assert "spotify" in metrics
        assert "youtube" in metrics
        assert "tiktok" in metrics
        assert "instagram" in metrics

    def test_prospect_score_included(self):
        dossier = _full_dossier("rising_colombian")
        ps = dossier["prospect_score"]
        assert "overall" in ps
        assert "tier" in ps
        assert "dimensions" in ps
        assert len(ps["dimensions"]) == 7

    def test_geographic_has_top_markets(self):
        dossier = _full_dossier("rising_colombian")
        geo = dossier["geographic_profile"]
        assert len(geo["top_markets"]) > 0
        assert geo["top_markets"][0]["country"] == "CO"

    def test_revenue_projection_present(self):
        dossier = _full_dossier("rising_colombian")
        rev = dossier["revenue_projection"]
        assert "monthly_total" in rev
        assert "annual_projected" in rev

    def test_catalog_shows_recent_tracks(self):
        dossier = _full_dossier("rising_colombian")
        catalog = dossier["catalog"]
        assert catalog["releases_6m"] == 6
        assert len(catalog["latest_tracks"]) > 0

    def test_competitive_context(self):
        dossier = _full_dossier("rising_colombian")
        comp = dossier["competitive_context"]
        assert len(comp["similar_artists"]) > 0

    def test_all_mock_artists_generate(self):
        for name in ["rising_colombian", "stagnant_big_artist", "bot_inflated", "single_platform", "revenue_heavy"]:
            dossier = _full_dossier(name)
            assert dossier["identity"]["name"] != ""
            assert dossier["prospect_score"]["overall"] >= 0
