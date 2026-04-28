"""Tests for the revenue estimation model."""

import json
from pathlib import Path

import pytest

from mcp_server.models import build_artist
from mcp_server.tools.scoring.d3_revenue_potential import estimate_artist_revenue

MOCK_DIR = Path(__file__).parent / "mock_data"


def _load_mock(name: str) -> dict:
    return json.loads((MOCK_DIR / f"{name}.json").read_text())


class TestRevenueEstimation:
    def test_returns_all_fields(self):
        artist = build_artist(_load_mock("rising_colombian"))
        result = estimate_artist_revenue(artist)
        assert "monthly_revenue_by_platform" in result
        assert "monthly_total" in result
        assert "annual_projected" in result
        assert "growth_factor" in result
        assert "top_revenue_countries" in result

    def test_bigger_artist_more_revenue(self):
        small = build_artist(_load_mock("rising_colombian"))
        big = build_artist(_load_mock("revenue_heavy"))
        small_rev = estimate_artist_revenue(small)
        big_rev = estimate_artist_revenue(big)
        assert big_rev["monthly_total"] > small_rev["monthly_total"]

    def test_revenue_is_positive(self):
        for mock in ["rising_colombian", "stagnant_big_artist", "revenue_heavy"]:
            artist = build_artist(_load_mock(mock))
            result = estimate_artist_revenue(artist)
            assert result["monthly_total"] > 0
            assert result["annual_projected"] > 0

    def test_growth_factor_reflects_trend(self):
        rising = build_artist(_load_mock("rising_colombian"))
        stagnant = build_artist(_load_mock("stagnant_big_artist"))
        rising_rev = estimate_artist_revenue(rising)
        stagnant_rev = estimate_artist_revenue(stagnant)
        # Rising artist should have higher growth factor
        assert rising_rev["growth_factor"] > stagnant_rev["growth_factor"]

    def test_has_platform_breakdown(self):
        artist = build_artist(_load_mock("revenue_heavy"))
        result = estimate_artist_revenue(artist)
        platforms = result["monthly_revenue_by_platform"]
        assert "spotify" in platforms
        assert "youtube" in platforms
        assert platforms["spotify"] > 0
        assert platforms["youtube"] > 0

    def test_us_mexico_heavy_earns_more(self):
        # Revenue heavy has MX + US = high CPM markets
        # Bot inflated has MX + CO + AR = lower average CPM
        revenue = build_artist(_load_mock("revenue_heavy"))
        bot = build_artist(_load_mock("bot_inflated"))
        rev_result = estimate_artist_revenue(revenue)
        bot_result = estimate_artist_revenue(bot)
        # Revenue heavy has 320K listeners vs bot's 180K, and better geo mix
        assert rev_result["monthly_total"] > bot_result["monthly_total"]
