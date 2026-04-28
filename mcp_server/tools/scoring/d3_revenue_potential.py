"""D3 — Revenue Potential (Default Weight: 20%)

Projects 12-month revenue from streaming metrics and geographic distribution,
then normalizes to a 0-100 score using configurable thresholds.
"""

from pathlib import Path

import yaml

from mcp_server.models import ArtistProfile, DimensionResult

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent.parent / "config"


def _load_cpm_config() -> dict:
    path = CONFIG_DIR / "cpm_rates.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def _clamp(val: float) -> float:
    return max(0.0, min(100.0, val))


def _is_legacy_catalog(artist: ArtistProfile) -> bool:
    """Detect deceased/legacy artists with passive catalog presence.

    Their Chartmetric monthly_listeners count includes everyone who
    saved a track years ago, but actual stream volume is far lower
    than for an active artist of the same listener count. Two signals
    we use, both requiring no releases in the last 12 months and a
    mainstream/superstar tier:

    1. Career trend explicitly tagged "decline" or "gradual decline".
    2. Listener-to-follower ratio < 2.0 (active artists usually have
       L/F 3-10x because algorithmic recommendations push them to
       non-followers; legacy catalog has L/F near or below 1 because
       people saved tracks years ago without active listening).

    Calibrated against 36-artist sample from FaroLatino royalty data:
    catches Chalino Sanchez, Cornelio Reyna, Ramon Ayala (all classic
    deceased/heritage artists with empirical streams-per-listener
    ratios <0.01 vs active median ~4). False positive risk: active
    artists whose last release fell just outside the 12-month window
    AND whose L/F is unusually low — accepted as edge case.
    """
    trend = (artist.career_trend or "").lower()
    stage = (artist.career_stage or "").lower()
    no_recent = (
        artist.recent_release_count_12m == 0
        and artist.recent_release_count_6m == 0
    )
    legacy_tier = stage in ("superstar", "mainstream")
    if not (no_recent and legacy_tier):
        return False
    declining = "decline" in trend
    if declining:
        return True
    # L/F < 2 with no recent releases at mainstream/superstar tier:
    # passive saved-tracks pattern.
    sp_followers = artist.sp_followers or 0
    sp_listeners = artist.sp_monthly_listeners or 0
    if sp_followers > 100_000 and sp_listeners > 0:
        ratio = sp_listeners / sp_followers
        if ratio < 2.0:
            return True
    return False


def _estimate_monthly_streams(artist: ArtistProfile, platform: str) -> float:
    """Rough estimate of monthly streams per platform from available metrics.

    Multipliers calibrated against FaroLatino's 24-month royalty data
    (Mar 2024 - Mar 2026, ~10M rows + 45-artist stratified sample).

    Active artists (default tier):
      Spotify:  monthly_listeners x 4   (full-catalog median from 4 active artists)
      YouTube:  yt_daily_views x 30 if available; else yt_subscribers x 3
                (subscribers-based estimate is unreliable for Latin music
                 where view counts decouple from subscriber count;
                 yt_daily_views is far more predictive when present)
      Apple:    4% of (Spotify + YouTube) stream volume (anchored on
                Apple's actual share of total streams across the book,
                not on Spotify alone — fixes over-projection for
                YouTube-heavy artists)
      Deezer:   deezer_fans x 0.5 (down from 8; book data shows Deezer
                                    is <1% of revenue, prior multiplier
                                    over-projected by 10-40x)
      Facebook: sp_monthly_listeners x 12 (book-wide ratio; CPM is so low
                                            (~$0.016/1000) that absolute
                                            stream count tolerance is wide)
      Amazon:   sp_monthly_listeners x 0.6 (small share of streams,
                                             decent CPM ~$2.30/1000)

    Legacy/deceased: heavy dampening because Chartmetric monthly_listeners
    includes passive saved tracks that don't actively stream.
    """
    if _is_legacy_catalog(artist):
        # Heavy dampening for passive-catalog tier.
        if platform == "spotify":
            return artist.sp_monthly_listeners * 0.05
        if platform == "youtube":
            if artist.yt_daily_views:
                return artist.yt_daily_views * 30
            return artist.yt_subscribers * 0.5
        if platform == "apple_music":
            sp = artist.sp_monthly_listeners * 0.05
            yt = (artist.yt_daily_views * 30) if artist.yt_daily_views else (artist.yt_subscribers * 0.5)
            return (sp + yt) * 0.04
        if platform == "deezer":
            return artist.deezer_fans * 0.05
        if platform == "facebook":
            return artist.sp_monthly_listeners * 0.6  # very dampened
        if platform == "amazon":
            return artist.sp_monthly_listeners * 0.05
        return 0

    if platform == "spotify":
        return artist.sp_monthly_listeners * 4
    if platform == "youtube":
        if artist.yt_daily_views:
            return artist.yt_daily_views * 30
        return artist.yt_subscribers * 3
    if platform == "apple_music":
        sp = artist.sp_monthly_listeners * 4
        yt = (artist.yt_daily_views * 30) if artist.yt_daily_views else (artist.yt_subscribers * 3)
        return (sp + yt) * 0.04
    if platform == "deezer":
        return artist.deezer_fans * 0.5
    if platform == "facebook":
        return artist.sp_monthly_listeners * 12
    if platform == "amazon":
        return artist.sp_monthly_listeners * 0.6
    return 0


def _momentum_growth_factor(career_trend: str, sp_growth_pct: float | None) -> float:
    """Convert momentum into a 12-month growth adjustment factor."""
    base = {
        "explosive growth": 1.8,
        "rising": 1.4,
        "gaining": 1.2,
        "stable": 1.0,
        "losing": 0.85,
        "decline": 0.7,
    }.get(career_trend, 1.0)

    # Refine with actual growth rate if available
    if sp_growth_pct is not None and sp_growth_pct > 0:
        # Compound monthly growth over 12 months, dampened
        monthly_mult = 1 + (sp_growth_pct / 100) * 0.5  # dampen by 50%
        compound = monthly_mult ** 6  # ~6 months of growth (conservative)
        return max(base, min(compound, 3.0))

    return base


def _score_from_revenue(annual: float, thresholds: dict) -> float:
    """Interpolate annual revenue to a 0-100 score using threshold table."""
    # Sort thresholds by revenue amount
    points = sorted((float(k), float(v)) for k, v in thresholds.items())

    if annual <= points[0][0]:
        return points[0][1]
    if annual >= points[-1][0]:
        return points[-1][1]

    for i in range(len(points) - 1):
        rev_lo, score_lo = points[i]
        rev_hi, score_hi = points[i + 1]
        if rev_lo <= annual <= rev_hi:
            ratio = (annual - rev_lo) / (rev_hi - rev_lo)
            return score_lo + ratio * (score_hi - score_lo)

    return 50.0


def _spotify_country_shares(artist: ArtistProfile) -> dict[str, float]:
    """Default country shares from Spotify's where-people-listen."""
    total = sum(c.listeners for c in artist.listener_countries)
    if total <= 0:
        return {"default": 1.0}
    return {c.country_code: c.listeners / total for c in artist.listener_countries}


def _platform_country_shares(artist: ArtistProfile, platform: str) -> dict[str, float]:
    """Per-platform listener geography. Falls back to Spotify when the
    platform's audience data isn't available.

    Chartmetric exposes platform-specific audience geography via
    /youtube-audience-stats and /tiktok-audience-stats (and /instagram-...
    for engagement). Country distributions differ markedly across platforms
    for the same artist (e.g. Dread Mar I: TikTok is ~85% Argentina but
    Spotify reads ~30% Mexico), so applying per-(platform, country) CPMs
    requires platform-specific shares — Spotify shares for non-Spotify
    platforms can be 30-50% off in CO/AR/MX-heavy LATAM mixes.
    """
    pcs = artist.social_audience_countries or {}
    entries = pcs.get(platform) or []
    if entries:
        # Entries are dicts with country_code and percent (already 0-100)
        shares: dict[str, float] = {}
        total_pct = 0.0
        for e in entries:
            code = (e.get("country_code") or "").upper() if isinstance(e, dict) else ""
            pct = e.get("percent", 0) if isinstance(e, dict) else 0
            if code and pct:
                shares[code] = shares.get(code, 0.0) + float(pct)
                total_pct += float(pct)
        if total_pct > 0:
            return {k: v / total_pct for k, v in shares.items()}

    # Special case: apple_music has no dedicated Chartmetric audience endpoint;
    # in practice its listener geography overlaps closely with Spotify.
    return _spotify_country_shares(artist)


def estimate_artist_revenue(artist: ArtistProfile) -> dict:
    """Core revenue estimation logic, reusable by both the scorer and the MCP tool."""
    config = _load_cpm_config()

    spotify_shares = _spotify_country_shares(artist)

    # Per-platform geography: YouTube and TikTok have their own audience
    # endpoints in Chartmetric. Apple Music, Deezer, Facebook, and Amazon
    # fall back to Spotify shares (no per-platform geography available).
    platforms = ["spotify", "youtube", "apple_music", "deezer", "facebook", "amazon"]
    monthly_revenue = {}
    geo_by_platform: dict[str, dict[str, float]] = {}

    for platform in platforms:
        if platform == "spotify":
            shares = spotify_shares
        else:
            shares = _platform_country_shares(artist, platform)
        geo_by_platform[platform] = shares

        monthly_streams = _estimate_monthly_streams(artist, platform)
        platform_cpms = config.get(platform, {})
        default_cpm = platform_cpms.get("default", 0.50)

        platform_total = 0
        for country, share in shares.items():
            cpm = platform_cpms.get(country, default_cpm)
            country_streams = monthly_streams * share
            platform_total += country_streams * cpm / 1000

        monthly_revenue[platform] = round(platform_total, 2)

    # For the dossier output: union of top countries across platforms,
    # weighted by stream volume. Falls back to Spotify shares.
    country_shares = spotify_shares

    monthly_total = sum(monthly_revenue.values())
    growth_factor = _momentum_growth_factor(artist.career_trend, artist.sp_monthly_listeners_diff_pct)
    annual_projected = monthly_total * 12 * growth_factor

    top_countries = sorted(country_shares.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "monthly_revenue_by_platform": monthly_revenue,
        "monthly_total": round(monthly_total, 2),
        "annual_projected": round(annual_projected, 2),
        "growth_factor": round(growth_factor, 2),
        "top_revenue_countries": [{"country": c, "share": round(s, 3)} for c, s in top_countries],
    }


def score_revenue_potential(artist: ArtistProfile) -> DimensionResult:
    config = _load_cpm_config()
    thresholds = config.get("revenue_score_thresholds", {0: 0, 1000: 20, 5000: 40, 15000: 60, 50000: 80, 150000: 100})

    rev = estimate_artist_revenue(artist)
    annual = rev["annual_projected"]
    score = _clamp(_score_from_revenue(annual, thresholds))

    has_geo = len(artist.listener_countries) > 0
    has_streams = artist.sp_monthly_listeners > 0
    confidence = (0.5 if has_streams else 0.0) + (0.3 if has_geo else 0.0) + 0.2

    rationale = f"Projected annual revenue: ${annual:,.0f}. "
    rationale += f"Monthly: ${rev['monthly_total']:,.0f}. "
    rationale += f"Growth factor: {rev['growth_factor']}x. "
    if rev["top_revenue_countries"]:
        top = rev["top_revenue_countries"][0]
        rationale += f"Top market: {top['country']} ({top['share']*100:.0f}%)."

    return DimensionResult(score=round(score, 1), confidence=round(confidence, 2), rationale=rationale.strip())
