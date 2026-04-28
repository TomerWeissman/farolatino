"""D5 — Content Velocity (Default Weight: 8%)

Measures release frequency as a signal of an active, committed project.
One track/month = commitment. One isolated hit 6 months ago = risk.
"""

from datetime import datetime, timedelta
from statistics import stdev

from mcp_server.models import ArtistProfile, DimensionResult


def _clamp(val: float) -> float:
    return max(0.0, min(100.0, val))


def _parse_date(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00").split("T")[0])
    except ValueError:
        return None


def score_content_velocity(artist: ArtistProfile) -> DimensionResult:
    now = datetime.now()
    six_months_ago = now - timedelta(days=180)
    twelve_months_ago = now - timedelta(days=365)

    # Filter to original tracks only (exclude remixes, live versions)
    original_tracks = [
        t for t in artist.tracks
        if t.version_type in ("original", "", None)
    ]

    # Parse release dates
    dated_tracks = []
    for t in original_tracks:
        dt = _parse_date(t.release_date)
        if dt:
            dated_tracks.append((t, dt))

    dated_tracks.sort(key=lambda x: x[1], reverse=True)

    releases_6m = sum(1 for _, dt in dated_tracks if dt >= six_months_ago)
    releases_12m = sum(1 for _, dt in dated_tracks if dt >= twelve_months_ago)

    if not dated_tracks:
        return DimensionResult(
            score=0.0,
            confidence=0.1,
            rationale="No release date data available.",
        )

    # Base score from release frequency (6m)
    # 6+ in 6 months = excellent, 3-5 = good, 1-2 = low, 0 = very low
    if releases_6m >= 6:
        freq_score = 90
    elif releases_6m >= 4:
        freq_score = 75
    elif releases_6m >= 2:
        freq_score = 55
    elif releases_6m >= 1:
        freq_score = 35
    else:
        freq_score = 15

    # Gap analysis: longest gap between consecutive releases in last 12m
    recent_dates = sorted([dt for _, dt in dated_tracks if dt >= twelve_months_ago])
    max_gap_days = 0
    if len(recent_dates) >= 2:
        for i in range(1, len(recent_dates)):
            gap = (recent_dates[i] - recent_dates[i - 1]).days
            max_gap_days = max(max_gap_days, gap)

    # Penalty for long gaps
    gap_penalty = 0
    if max_gap_days > 120:
        gap_penalty = 20
    elif max_gap_days > 90:
        gap_penalty = 10

    # Bonus for consistency (low variance in release intervals)
    consistency_bonus = 0
    if len(recent_dates) >= 3:
        intervals = [(recent_dates[i] - recent_dates[i - 1]).days for i in range(1, len(recent_dates))]
        if intervals:
            sd = stdev(intervals) if len(intervals) > 1 else 0
            avg_interval = sum(intervals) / len(intervals)
            if avg_interval > 0 and sd / avg_interval < 0.5:
                consistency_bonus = 10

    score = _clamp(freq_score - gap_penalty + consistency_bonus)

    # Days since last release
    last_release = dated_tracks[0][1]
    days_since = (now - last_release).days

    confidence = min(len(dated_tracks) / 5, 1.0)

    rationale = f"{releases_6m} releases in 6 months, {releases_12m} in 12 months. "
    rationale += f"Last release: {days_since} days ago. "
    if max_gap_days > 90:
        rationale += f"Longest gap: {max_gap_days} days. "
    if consistency_bonus > 0:
        rationale += "Consistent cadence."

    return DimensionResult(score=round(score, 1), confidence=round(confidence, 2), rationale=rationale.strip())
