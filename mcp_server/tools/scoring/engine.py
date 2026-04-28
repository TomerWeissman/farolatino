"""Scoring engine — composes all 7 dimension scorers and applies profile weights."""

from mcp_server.models import ArtistProfile, DimensionResult, build_artist
from mcp_server.server import mcp
from mcp_server.tools.config_manager import get_profile

from .d1_momentum import score_momentum
from .d2_geographic_fit import score_geographic_fit
from .d3_revenue_potential import score_revenue_potential
from .d4_timing import score_timing
from .d5_content_velocity import score_content_velocity
from .d6_engagement_quality import score_engagement_quality
from .d7_platform_diversification import score_platform_diversification

SCORERS: dict[str, callable] = {
    "momentum": score_momentum,
    "geographic_fit": score_geographic_fit,
    "revenue_potential": score_revenue_potential,
    "timing": score_timing,
    "content_velocity": score_content_velocity,
    "engagement_quality": score_engagement_quality,
    "platform_diversification": score_platform_diversification,
}

TIER_THRESHOLDS = [
    (85, "HOT"),
    (70, "WARM"),
    (55, "WATCH"),
    (0, "PASS"),
]


def _classify_tier(score: float) -> str:
    for threshold, tier in TIER_THRESHOLDS:
        if score >= threshold:
            return tier
    return "PASS"


@mcp.tool()
def compute_prospect_score(artist_data: dict, profile_name: str = "default") -> dict:
    """Score an artist across all 7 dimensions using the specified search profile.

    Args:
        artist_data: Dict with artist fields matching ArtistProfile model.
        profile_name: Search profile to use for weights (default, emerging_momentum,
                      revenue_focus, latam_expansion).
    """
    artist = build_artist(artist_data)
    artist.compute_data_completeness()

    profile = get_profile(profile_name)
    if "error" in profile:
        return profile
    weights = profile["weights"]

    dimensions = {}
    total_score = 0.0
    total_confidence = 0.0

    for name, scorer in SCORERS.items():
        result: DimensionResult = scorer(artist)
        weight = weights.get(name, 0)
        dimensions[name] = {
            "score": result.score,
            "confidence": result.confidence,
            "rationale": result.rationale,
            "weight": weight,
            "weighted_contribution": round(result.score * weight, 1),
        }
        total_score += result.score * weight
        total_confidence += result.confidence * weight

    tier = _classify_tier(total_score)

    return {
        "prospect_score": round(total_score, 1),
        "tier": tier,
        "confidence": round(total_confidence, 2),
        "data_completeness": round(artist.data_completeness, 2),
        "profile_used": profile["name"],
        "dimensions": dimensions,
    }
