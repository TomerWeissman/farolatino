"""D4 — Timing (Default Weight: 15%)

Detects whether the artist is in the "sweet spot": post-viralization but
pre-major-label interest. The window where signing delivers maximum ROI.
"""

from mcp_server.models import ArtistProfile, DimensionResult

# Career stage → base timing score
# Developing + rising = ideal window
STAGE_SCORES = {
    "undiscovered": 40,
    "developing": 80,
    "mid-level": 65,
    "mainstream": 30,
    "superstar": 10,
    "legendary": 5,
}

TREND_BOOSTS = {
    "explosive growth": 25,
    "rising": 15,
    "gaining": 5,
    "stable": -5,
    "losing": -15,
    "decline": -25,
}

MAJOR_LABELS = {
    "universal music", "universal music group", "universal music latin",
    "sony music", "sony music entertainment", "sony music latin",
    "warner music", "warner music group", "warner records",
    "interscope", "atlantic records", "columbia records", "republic records",
    "def jam", "rca records", "capitol records", "epic records",
}


def _clamp(val: float) -> float:
    return max(0.0, min(100.0, val))


def score_timing(artist: ArtistProfile) -> DimensionResult:
    signals = []

    # Base score from career stage
    base = STAGE_SCORES.get(artist.career_stage, 50)
    trend_adj = TREND_BOOSTS.get(artist.career_trend, 0)
    raw = base + trend_adj

    # Negative: already signed to a major
    if artist.record_label:
        label_lower = artist.record_label.lower()
        if any(major in label_lower for major in MAJOR_LABELS):
            raw = min(raw, 15)
            signals.append(f"already on major label ({artist.record_label})")

    # Positive: Shazam spikes = early virality
    if artist.shazam_count_diff_pct is not None and artist.shazam_count_diff_pct > 100:
        raw += 10
        signals.append(f"Shazam spike (+{artist.shazam_count_diff_pct:.0f}%)")

    # Positive: editorial playlist adds
    recent_editorial = [p for p in artist.editorial_playlists if p.added_date]
    if recent_editorial:
        raw += 5
        signals.append(f"{len(recent_editorial)} editorial playlist(s)")

    # Positive: TikTok virality
    if artist.tiktok_followers_diff_pct is not None and artist.tiktok_followers_diff_pct > 100:
        raw += 8
        signals.append("TikTok momentum")

    # Negative: chart appearances in major markets = majors may be circling
    major_charts = [c for c in artist.chart_appearances if c.country in ("US", "GB", "ES", "MX")]
    if len(major_charts) > 2:
        raw -= 10
        signals.append(f"{len(major_charts)} major market chart appearances (window may be closing)")

    # Context: neighboring artists getting signed = market heat
    signed_neighbors = [n for n in artist.neighboring_artists if n.signed]
    if len(signed_neighbors) >= 3:
        raw -= 5
        signals.append(f"{len(signed_neighbors)} similar artists recently signed")

    score = _clamp(raw)

    # Confidence based on data availability
    has_career = artist.career_stage != "" and artist.career_trend != ""
    has_charts = len(artist.chart_appearances) > 0 or True  # absence of charts is data too
    has_label_info = True  # record_label being None is valid info
    confidence = 0.5 * has_career + 0.3 * has_charts + 0.2 * has_label_info

    rationale = f"Career: {artist.career_stage or 'unknown'} / {artist.career_trend or 'unknown'}. "
    if signals:
        rationale += " | ".join(signals)
    else:
        rationale += "No standout timing signals."

    return DimensionResult(score=round(score, 1), confidence=round(confidence, 2), rationale=rationale.strip())
