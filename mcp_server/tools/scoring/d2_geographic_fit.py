"""D2 — Geographic Fit (Default Weight: 20%)

Measures alignment between the artist's audience geography and
FaroLatino's distribution infrastructure / market priorities.
"""

import yaml

from core.paths import resource_path
from mcp_server.models import ArtistProfile, DimensionResult

# Bundle-aware: source mode → PROJECT_ROOT/config; bundled .app →
# Contents/Resources/config/.
CONFIG_DIR = resource_path("config")


def _load_market_tiers() -> dict:
    path = CONFIG_DIR / "market_tiers.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _clamp(val: float) -> float:
    return max(0.0, min(100.0, val))


def score_geographic_fit(artist: ArtistProfile) -> DimensionResult:
    tiers = _load_market_tiers()
    tier_weights = tiers.get("tier_weights", {"tier_1": 1.0, "tier_2": 0.7, "tier_3": 0.4, "unclassified": 0.2})

    tier_1 = set(tiers.get("tier_1", []))
    tier_2 = set(tiers.get("tier_2", []))
    tier_3 = set(tiers.get("tier_3", []))

    if not artist.listener_countries:
        return DimensionResult(
            score=0.0,
            confidence=0.0,
            rationale="No geographic data available.",
        )

    total_listeners = sum(c.listeners for c in artist.listener_countries)
    if total_listeners == 0:
        return DimensionResult(score=0.0, confidence=0.1, rationale="Zero listeners across all markets.")

    # Calculate weighted geographic score
    tier_1_listeners = 0
    tier_2_listeners = 0
    tier_3_listeners = 0
    unclassified_listeners = 0

    for c in artist.listener_countries:
        if c.country_code in tier_1:
            tier_1_listeners += c.listeners
        elif c.country_code in tier_2:
            tier_2_listeners += c.listeners
        elif c.country_code in tier_3:
            tier_3_listeners += c.listeners
        else:
            unclassified_listeners += c.listeners

    weighted_score = (
        (tier_1_listeners / total_listeners) * tier_weights["tier_1"]
        + (tier_2_listeners / total_listeners) * tier_weights["tier_2"]
        + (tier_3_listeners / total_listeners) * tier_weights["tier_3"]
        + (unclassified_listeners / total_listeners) * tier_weights["unclassified"]
    ) * 100

    # Bonus: growth in target markets
    growing_markets = [
        c for c in artist.listener_countries
        if c.prev_listeners > 0 and c.listeners > c.prev_listeners
        and c.country_code in (tier_1 | tier_2)
    ]
    if growing_markets:
        growth_bonus = min(len(growing_markets) * 3, 15)
        weighted_score += growth_bonus

    # Bonus: multi-platform geographic consistency
    # If social_audience_countries has data for multiple platforms showing
    # the same top countries, that's a strong signal
    if artist.social_audience_countries:
        platform_top_countries = []
        for platform, countries in artist.social_audience_countries.items():
            if countries:
                top = [c.get("country_code", "") for c in countries[:3]]
                platform_top_countries.append(set(top))
        if len(platform_top_countries) >= 2:
            overlap = platform_top_countries[0]
            for s in platform_top_countries[1:]:
                overlap = overlap & s
            if overlap & (tier_1 | tier_2):
                weighted_score += 5  # consistency bonus

    score = _clamp(weighted_score)

    # Build rationale
    top_markets = sorted(artist.listener_countries, key=lambda c: c.listeners, reverse=True)[:3]
    market_strs = []
    for m in top_markets:
        pct = (m.listeners / total_listeners) * 100
        market_strs.append(f"{m.country_code} {pct:.0f}%")

    tier_1_pct = (tier_1_listeners / total_listeners) * 100
    rationale = f"Top markets: {', '.join(market_strs)}. "
    rationale += f"Tier 1 concentration: {tier_1_pct:.0f}%. "
    if growing_markets:
        rationale += f"{len(growing_markets)} target market(s) growing."

    confidence = min(len(artist.listener_countries) / 5, 1.0)

    return DimensionResult(score=round(score, 1), confidence=round(confidence, 2), rationale=rationale.strip())
