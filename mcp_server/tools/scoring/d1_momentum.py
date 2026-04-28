"""D1 — Momentum Score (Default Weight: 25%)

Measures growth velocity, not absolute size. An artist at 5K listeners
growing 40% MoM outscores a stagnant 500K-listener artist.
"""

from statistics import mean

from mcp_server.models import ArtistProfile, DimensionResult

# Career trend → multiplier applied to raw score
TREND_MULTIPLIERS = {
    "explosive growth": 1.30,
    "rising": 1.15,
    "gaining": 1.00,
    "stable": 0.75,
    "losing": 0.50,
    "decline": 0.30,
}


def _normalize_growth(pct: float) -> float:
    """Map a monthly growth percentage to a 0-100 scale.
    0% → 30, 20% → 60, 50%+ → 90, negative → scaled down from 30.
    """
    if pct >= 50:
        return min(90 + (pct - 50) * 0.2, 100)
    if pct >= 0:
        return 30 + pct * 1.2
    # Negative growth
    return max(0, 30 + pct * 0.6)


def _clamp(val: float) -> float:
    return max(0.0, min(100.0, val))


def score_momentum(artist: ArtistProfile) -> DimensionResult:
    signals = []

    # Primary: CM career momentum score (0-100)
    momentum_base = artist.career_momentum_score
    trend_mult = TREND_MULTIPLIERS.get(artist.career_trend, 0.75)

    # Secondary: cross-platform growth rates
    growth_rates = [
        artist.sp_monthly_listeners_diff_pct,
        artist.sp_followers_diff_pct,
        artist.yt_subscribers_diff_pct,
        artist.tiktok_followers_diff_pct,
    ]
    valid_rates = [r for r in growth_rates if r is not None]
    data_points = len(valid_rates)

    if valid_rates:
        avg_growth = mean(valid_rates)
        growth_score = _normalize_growth(avg_growth)
    else:
        avg_growth = 0.0
        growth_score = 30.0  # neutral if no data

    # Combine: 60% CM momentum, 40% cross-platform growth
    raw = (momentum_base * 0.6 + growth_score * 0.4) * trend_mult

    # Penalty: any major platform declining significantly
    declining = [r for r in valid_rates if r < -10]
    if declining:
        raw *= 0.85
        signals.append(f"declining on {len(declining)} platform(s)")

    # Boost: noteworthy insights flagging acceleration
    accel_insights = [i for i in artist.noteworthy_insights if "accel" in i.type.lower() or "spike" in i.type.lower()]
    if accel_insights:
        raw *= 1.10
        signals.append("recent acceleration detected")

    score = _clamp(raw)
    confidence = data_points / 4 if data_points > 0 else 0.2

    rationale = f"Career trend: {artist.career_trend or 'unknown'}. "
    if valid_rates:
        rationale += f"Avg cross-platform growth: {avg_growth:+.1f}%/month. "
    if signals:
        rationale += " | ".join(signals)

    return DimensionResult(score=round(score, 1), confidence=round(confidence, 2), rationale=rationale.strip())
