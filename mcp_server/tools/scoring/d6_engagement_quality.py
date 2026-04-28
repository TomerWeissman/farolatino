"""D6 — Engagement Quality (Default Weight: 7%)

The "lie detector." Detects whether metrics are organic or artificially inflated
using follower-to-listener ratios, engagement rates, and cross-platform consistency.
"""

from mcp_server.models import ArtistProfile, DimensionResult


def _clamp(val: float) -> float:
    return max(0.0, min(100.0, val))


def score_engagement_quality(artist: ArtistProfile) -> DimensionResult:
    signals = []
    scores = []
    data_points = 0

    # Signal 1: Spotify followers-to-listeners ratio
    # Healthy range: 0.10-0.50. Below 0.05 = likely bot streams.
    # Above 0.60 = unusual but not necessarily bad (niche loyal fanbase).
    ratio = artist.sp_followers_to_listeners_ratio
    if ratio is not None and artist.sp_monthly_listeners > 0:
        data_points += 1
        if 0.10 <= ratio <= 0.50:
            ratio_score = 80 + (0.30 - abs(ratio - 0.30)) * 60  # peaks at 0.30
            signals.append(f"Healthy follower/listener ratio ({ratio:.2f})")
        elif ratio < 0.05:
            ratio_score = 15
            signals.append(f"Very low follower/listener ratio ({ratio:.2f}) — possible bot streams")
        elif ratio < 0.10:
            ratio_score = 45
            signals.append(f"Low follower/listener ratio ({ratio:.2f})")
        else:
            ratio_score = 65  # high ratio, unusual but not a red flag
            signals.append(f"High follower/listener ratio ({ratio:.2f})")
        scores.append(ratio_score)

    # Signal 2: Instagram engagement rate
    # Healthy: > 2%. Excellent: > 5%. Suspicious if very high (>15%) on small accounts.
    if artist.ig_engagement_rate is not None:
        data_points += 1
        er = artist.ig_engagement_rate
        if er >= 5.0:
            ig_score = 90
            signals.append(f"Strong IG engagement ({er:.1f}%)")
        elif er >= 2.0:
            ig_score = 70
            signals.append(f"Healthy IG engagement ({er:.1f}%)")
        elif er >= 1.0:
            ig_score = 50
            signals.append(f"Below-average IG engagement ({er:.1f}%)")
        else:
            ig_score = 25
            signals.append(f"Low IG engagement ({er:.1f}%)")
        scores.append(ig_score)

    # Signal 3: Cross-platform consistency
    # If Spotify is huge but YouTube/TikTok/IG are tiny, suspicious.
    platforms_with_presence = 0
    if artist.sp_monthly_listeners > 1000:
        platforms_with_presence += 1
    if artist.yt_subscribers > 500:
        platforms_with_presence += 1
    if artist.tiktok_followers > 1000:
        platforms_with_presence += 1
    if artist.ig_followers > 1000:
        platforms_with_presence += 1

    if artist.sp_monthly_listeners > 0:
        data_points += 1
        if platforms_with_presence >= 3:
            consistency_score = 85
            signals.append(f"Consistent presence on {platforms_with_presence} platforms")
        elif platforms_with_presence >= 2:
            consistency_score = 60
        elif artist.sp_monthly_listeners > 50000:
            # High Spotify but only 1 platform with presence = suspicious
            consistency_score = 30
            signals.append("High Spotify but weak cross-platform presence")
        else:
            consistency_score = 50
        scores.append(consistency_score)

    # Signal 4: Growth pattern analysis (simplified)
    # Organic growth rates should be correlated across platforms
    growth_rates = [
        artist.sp_monthly_listeners_diff_pct,
        artist.yt_subscribers_diff_pct,
        artist.tiktok_followers_diff_pct,
    ]
    valid_growth = [r for r in growth_rates if r is not None]
    if len(valid_growth) >= 2:
        data_points += 1
        # If one platform is growing 500%+ while others are flat, suspicious
        max_growth = max(valid_growth)
        min_growth = min(valid_growth)
        if max_growth > 200 and min_growth < 10:
            growth_pattern_score = 35
            signals.append("Uneven growth pattern across platforms")
        else:
            growth_pattern_score = 75
        scores.append(growth_pattern_score)

    if not scores:
        return DimensionResult(
            score=50.0,  # neutral if no data
            confidence=0.1,
            rationale="Insufficient engagement data for quality assessment.",
        )

    score = _clamp(sum(scores) / len(scores))
    confidence = min(data_points / 4, 1.0)

    rationale = " | ".join(signals) if signals else "No engagement anomalies detected."

    return DimensionResult(score=round(score, 1), confidence=round(confidence, 2), rationale=rationale)
