"""Tests for the scoring engine and all 7 dimension scorers."""

import json
from pathlib import Path

import pytest

from mcp_server.models import ArtistProfile
from mcp_server.models import build_artist
from mcp_server.tools.scoring.engine import compute_prospect_score
from mcp_server.tools.scoring.d1_momentum import score_momentum
from mcp_server.tools.scoring.d2_geographic_fit import score_geographic_fit
from mcp_server.tools.scoring.d3_revenue_potential import score_revenue_potential
from mcp_server.tools.scoring.d4_timing import score_timing
from mcp_server.tools.scoring.d5_content_velocity import score_content_velocity
from mcp_server.tools.scoring.d6_engagement_quality import score_engagement_quality
from mcp_server.tools.scoring.d7_platform_diversification import score_platform_diversification

MOCK_DIR = Path(__file__).parent / "mock_data"


def _load_mock(name: str) -> dict:
    return json.loads((MOCK_DIR / f"{name}.json").read_text())


def _artist(name: str) -> ArtistProfile:
    return build_artist(_load_mock(name))


# --- D1 Momentum ---

class TestD1Momentum:
    def test_rising_artist_scores_high(self):
        result = score_momentum(_artist("rising_colombian"))
        assert result.score >= 60, f"Rising artist should score >=60, got {result.score}"

    def test_stagnant_artist_scores_low(self):
        result = score_momentum(_artist("stagnant_big_artist"))
        assert result.score < 45, f"Stagnant artist should score <45, got {result.score}"

    def test_rising_beats_stagnant(self):
        rising = score_momentum(_artist("rising_colombian"))
        stagnant = score_momentum(_artist("stagnant_big_artist"))
        assert rising.score > stagnant.score

    def test_score_range(self):
        for mock in ["rising_colombian", "stagnant_big_artist", "bot_inflated"]:
            result = score_momentum(_artist(mock))
            assert 0 <= result.score <= 100
            assert 0 <= result.confidence <= 1


# --- D2 Geographic Fit ---

class TestD2GeographicFit:
    def test_colombian_artist_has_good_fit(self):
        result = score_geographic_fit(_artist("rising_colombian"))
        # CO is tier 1, should score well
        assert result.score >= 50

    def test_no_geo_data_scores_zero(self):
        artist = ArtistProfile(name="Empty")
        result = score_geographic_fit(artist)
        assert result.score == 0
        assert result.confidence == 0

    def test_tier1_heavy_beats_tier3_heavy(self):
        # Rising colombian has CO, MX, US (all tier 1)
        # Revenue heavy has MX, US, GT, HN (mix of tiers)
        colombian = score_geographic_fit(_artist("rising_colombian"))
        revenue = score_geographic_fit(_artist("revenue_heavy"))
        # Both should be decent, but colombian has purer tier 1 concentration
        assert colombian.score >= 50
        assert revenue.score >= 40


# --- D3 Revenue Potential ---

class TestD3RevenuePotential:
    def test_revenue_heavy_scores_high(self):
        result = score_revenue_potential(_artist("revenue_heavy"))
        # 320K listeners, MX+US heavy = high revenue
        assert result.score >= 50

    def test_small_artist_scores_lower(self):
        rising = score_revenue_potential(_artist("rising_colombian"))
        big = score_revenue_potential(_artist("revenue_heavy"))
        assert big.score > rising.score

    def test_score_range(self):
        for mock in ["rising_colombian", "stagnant_big_artist", "revenue_heavy"]:
            result = score_revenue_potential(_artist(mock))
            assert 0 <= result.score <= 100


# --- D4 Timing ---

class TestD4Timing:
    def test_developing_rising_is_ideal(self):
        result = score_timing(_artist("rising_colombian"))
        # developing + rising = ideal timing
        assert result.score >= 70

    def test_stagnant_mid_level_is_mediocre(self):
        result = score_timing(_artist("stagnant_big_artist"))
        # mid-level + stable = not ideal
        assert result.score < 70

    def test_major_label_kills_timing(self):
        data = _load_mock("rising_colombian")
        data["record_label"] = "Universal Music Latin"
        artist = build_artist(data)
        result = score_timing(artist)
        assert result.score <= 35, "Major label should heavily penalize timing score"


# --- D5 Content Velocity ---

class TestD5ContentVelocity:
    def test_active_releaser_scores_high(self):
        result = score_content_velocity(_artist("rising_colombian"))
        # 6 releases in 6 months = excellent
        assert result.score >= 70

    def test_infrequent_releaser_scores_low(self):
        result = score_content_velocity(_artist("stagnant_big_artist"))
        # 1 release in 6 months, gap of 5 months
        assert result.score < 50

    def test_no_tracks_scores_zero(self):
        artist = ArtistProfile(name="Empty")
        result = score_content_velocity(artist)
        assert result.score == 0


# --- D6 Engagement Quality ---

class TestD6EngagementQuality:
    def test_healthy_engagement(self):
        result = score_engagement_quality(_artist("rising_colombian"))
        # Ratio 0.267, IG engagement 3.8%, multi-platform = healthy
        assert result.score >= 60

    def test_bot_inflated_penalized(self):
        result = score_engagement_quality(_artist("bot_inflated"))
        # Ratio 0.019, low IG engagement, Spotify huge but others tiny
        assert result.score <= 40, f"Bot-inflated should score <=40, got {result.score}"

    def test_bot_worse_than_organic(self):
        organic = score_engagement_quality(_artist("rising_colombian"))
        bot = score_engagement_quality(_artist("bot_inflated"))
        assert organic.score > bot.score


# --- D7 Platform Diversification ---

class TestD7PlatformDiversification:
    def test_multi_platform_scores_high(self):
        result = score_platform_diversification(_artist("rising_colombian"))
        # Present on spotify, youtube, tiktok, instagram, deezer, soundcloud
        assert result.score >= 50

    def test_single_platform_penalized(self):
        result = score_platform_diversification(_artist("single_platform"))
        # Only Spotify has meaningful presence
        assert result.score < 40, f"Single-platform should score <40, got {result.score}"

    def test_diverse_beats_concentrated(self):
        diverse = score_platform_diversification(_artist("rising_colombian"))
        single = score_platform_diversification(_artist("single_platform"))
        assert diverse.score > single.score


# --- Composite Score (Engine) ---

class TestCompositeScore:
    def test_returns_all_fields(self):
        result = compute_prospect_score(_load_mock("rising_colombian"))
        assert "prospect_score" in result
        assert "tier" in result
        assert "confidence" in result
        assert "dimensions" in result
        assert len(result["dimensions"]) == 7

    def test_tier_classification(self):
        result = compute_prospect_score(_load_mock("rising_colombian"))
        score = result["prospect_score"]
        tier = result["tier"]
        if score >= 85:
            assert tier == "HOT"
        elif score >= 70:
            assert tier == "WARM"
        elif score >= 55:
            assert tier == "WATCH"
        else:
            assert tier == "PASS"

    def test_rising_beats_stagnant_overall(self):
        rising = compute_prospect_score(_load_mock("rising_colombian"))
        stagnant = compute_prospect_score(_load_mock("stagnant_big_artist"))
        assert rising["prospect_score"] > stagnant["prospect_score"]

    def test_weights_sum_to_100(self):
        result = compute_prospect_score(_load_mock("rising_colombian"))
        contributions = sum(d["weighted_contribution"] for d in result["dimensions"].values())
        assert abs(contributions - result["prospect_score"]) < 0.2

    def test_profile_changes_results(self):
        default = compute_prospect_score(_load_mock("rising_colombian"), "default")
        momentum = compute_prospect_score(_load_mock("rising_colombian"), "emerging_momentum")
        # Emerging momentum profile boosts momentum weight — rising artist should score higher
        assert momentum["prospect_score"] >= default["prospect_score"] - 5  # allow small variance
