"""D7 — Platform Diversification (Default Weight: 5%)

Risk mitigation through multi-platform presence. An artist dependent
on a single platform is riskier than one balanced across several.
"""

from mcp_server.models import ArtistProfile, DimensionResult

# Minimum thresholds to consider "meaningful presence" on a platform
PRESENCE_THRESHOLDS = {
    "spotify": 500,        # monthly listeners
    "youtube": 200,        # subscribers
    "tiktok": 500,         # followers
    "instagram": 500,      # followers
    "deezer": 100,         # fans
    "shazam": 50,          # shazam count
    "soundcloud": 200,     # followers
}


def _clamp(val: float) -> float:
    return max(0.0, min(100.0, val))


def score_platform_diversification(artist: ArtistProfile) -> DimensionResult:
    # Primary signal: CM's Cross-Platform Performance score (0-1)
    cpp_score = artist.cpp_score

    # Secondary: count platforms with meaningful presence
    platform_metrics = {
        "spotify": artist.sp_monthly_listeners,
        "youtube": artist.yt_subscribers,
        "tiktok": artist.tiktok_followers,
        "instagram": artist.ig_followers,
        "deezer": artist.deezer_fans,
        "shazam": artist.shazam_count,
        "soundcloud": artist.soundcloud_followers,
    }

    active_platforms = []
    for platform, value in platform_metrics.items():
        threshold = PRESENCE_THRESHOLDS.get(platform, 100)
        if value >= threshold:
            active_platforms.append(platform)

    platform_count = len(active_platforms)

    # Calculate evenness (how balanced the distribution is)
    # Using a simplified Gini-like metric on the active platform values
    if platform_count >= 2:
        values = [platform_metrics[p] for p in active_platforms]
        max_val = max(values)
        if max_val > 0:
            normalized = [v / max_val for v in values]
            evenness = sum(normalized) / len(normalized)  # 1.0 = perfectly even
        else:
            evenness = 0
    else:
        evenness = 0

    # Combine signals
    if cpp_score > 0:
        # CPP available — weight it heavily
        raw = cpp_score * 60 + (platform_count / 7) * 25 + evenness * 15
    else:
        # No CPP — use platform count and evenness
        count_score = {0: 5, 1: 20, 2: 40, 3: 60, 4: 75, 5: 85, 6: 92, 7: 100}.get(
            min(platform_count, 7), 50
        )
        raw = count_score * 0.7 + evenness * 30

    score = _clamp(raw)

    confidence = 0.8 if cpp_score > 0 else (0.5 if platform_count > 0 else 0.2)

    rationale = f"Active on {platform_count}/7 platforms ({', '.join(active_platforms) or 'none'}). "
    if cpp_score > 0:
        rationale += f"CPP score: {cpp_score:.2f}. "
    if platform_count == 1:
        rationale += "Single-platform risk."
    elif evenness < 0.3 and platform_count >= 2:
        dominant = max(active_platforms, key=lambda p: platform_metrics[p])
        rationale += f"Heavily concentrated on {dominant}."

    return DimensionResult(score=round(score, 1), confidence=round(confidence, 2), rationale=rationale.strip())
