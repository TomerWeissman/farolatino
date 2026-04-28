"""Chartmetric discovery — find unsigned artists matching search criteria.

Used for Mode 1 (automatic discovery): the system scans Chartmetric
for artists matching FaroLatino's configured search criteria and returns
a ranked list of candidates for scoring.

Uses two complementary endpoints:
1. GET /api/artist/list/filter — filter by career stage, trend, country, genre
2. GET /api/artist/:type/list  — filter by metric ranges + unsigned=true
"""

from mcp_server.server import mcp
from mcp_server.tools.chartmetric_auth import api_get
from mcp_server.tools.config_manager import load_config, get_profile


def _build_filter_params(criteria: dict, profile_overrides: dict | None = None) -> dict:
    """Build query params for /api/artist/list/filter from config."""
    filters = criteria.get("filters", criteria)

    # Apply profile overrides if present
    if profile_overrides:
        overrides = profile_overrides.get("filter_overrides", {})
        filters = {**filters, **overrides}

    params = {
        "limit": 100,
        "offset": 0,
        "sortColumn": "weekly_diff_percent.sp_monthly_listeners",
        "sortOrderDesc": "true",
    }

    # Country filter
    countries = filters.get("countries", [])
    if countries and isinstance(countries, list):
        # API accepts code2 as a single value, so we'll use the first one
        # and iterate for multiple countries in the caller
        params["code2"] = countries[0]

    # Career stage
    stages = filters.get("career_stages", [])
    if stages and isinstance(stages, list):
        params["career_stage"] = stages[0]

    # Career trend
    trends = filters.get("career_trends", [])
    if trends and isinstance(trends, list):
        params["career_trend"] = trends[0]

    # Spotify monthly listeners range
    ml_config = filters.get("monthly_listeners", {})
    if ml_config:
        ml_min = ml_config.get("min")
        ml_max = ml_config.get("max")
        if ml_min is not None and ml_max is not None:
            params["sp_ml"] = f"[{ml_min},{ml_max}]"

    return params


def _build_stat_params(criteria: dict, profile_overrides: dict | None = None) -> dict:
    """Build query params for /api/artist/:type/list from config."""
    filters = criteria.get("filters", criteria)

    if profile_overrides:
        overrides = profile_overrides.get("filter_overrides", {})
        filters = {**filters, **overrides}

    params = {
        "limit": 100,
        "offset": 0,
    }

    # Country
    countries = filters.get("countries", [])
    if countries:
        params["code2"] = countries[0]

    # Unsigned only
    if filters.get("unsigned_only", True):
        params["unsigned"] = "true"

    # Listener range
    ml_config = filters.get("monthly_listeners", {})
    if ml_config:
        params["min"] = ml_config.get("min", 1000)
        params["max"] = ml_config.get("max", 200000)

    return params


def _is_excluded(artist: dict, criteria: dict) -> bool:
    """Check if an artist should be excluded based on config rules."""
    filters = criteria.get("filters", criteria)

    # Check excluded artist IDs
    excluded_ids = filters.get("excluded_artists", [])
    cm_id = str(artist.get("cm_artist", artist.get("chartmetric_artist_id", "")))
    if cm_id in [str(x) for x in excluded_ids]:
        return True

    # Check excluded labels
    excluded_labels = [l.lower() for l in filters.get("excluded_labels", [])]
    artist_label = (artist.get("record_label") or "").lower()
    if artist_label and any(el in artist_label for el in excluded_labels):
        return True

    return False


def _format_artist_result(artist: dict) -> dict:
    """Extract the fields we care about from a filter/list API result."""
    return {
        "cm_id": artist.get("cm_artist", artist.get("chartmetric_artist_id")),
        "name": artist.get("name", ""),
        "code2": artist.get("code2", ""),
        "genres": artist.get("genres", ""),
        "sp_monthly_listeners": artist.get("sp_monthly_listeners"),
        "sp_followers": artist.get("sp_followers"),
        "sp_followers_to_listeners_ratio": artist.get("sp_followers_to_listeners_ratio"),
        "career_stage": (artist.get("career_status") or {}).get("stage", ""),
        "career_trend": (artist.get("career_status") or {}).get("trend", ""),
        "signed": artist.get("signed"),
        "image_url": artist.get("image_url", ""),
    }


@mcp.tool()
def discover_artists(profile_name: str = "default") -> dict:
    """Discover unsigned artists matching FaroLatino's search criteria.

    Queries Chartmetric's filter endpoints using the configured search
    criteria and scoring profile. Returns a list of artist candidates
    ready for full evaluation and scoring.

    Args:
        profile_name: Which search profile to use (default, emerging_momentum,
                       revenue_focus, latam_expansion). Each profile has
                       different filter and weight settings.

    Returns:
        A dict with the profile used, search parameters, and a list
        of artist candidates with their basic metrics.
    """
    # Load search criteria config
    criteria_result = load_config("search_criteria")
    criteria = criteria_result.get("config", {})

    # Load profile overrides if not default
    profile_overrides = None
    if profile_name != "default":
        profile_result = get_profile(profile_name)
        profile_overrides = profile_result.get("profile", {})

    # Strategy 1: Use the filter endpoint (career stage + trend filtering)
    filter_params = _build_filter_params(criteria, profile_overrides)
    try:
        filter_data = api_get("/api/artist/list/filter", params=filter_params)
        filter_artists = filter_data.get("obj", {}).get("obj", [])
    except Exception:
        filter_artists = []

    # Strategy 2: Use the stat list endpoint (metric range + unsigned filter)
    stat_params = _build_stat_params(criteria, profile_overrides)
    try:
        stat_data = api_get(
            "/api/artist/sp_monthly_listeners/list",
            params=stat_params,
        )
        stat_artists = stat_data.get("obj", {}).get("data", [])
    except Exception:
        stat_artists = []

    # Merge results, deduplicate by cm_id
    seen_ids = set()
    candidates = []

    for artist in filter_artists + stat_artists:
        cm_id = artist.get("cm_artist", artist.get("chartmetric_artist_id"))
        if cm_id is None or cm_id in seen_ids:
            continue
        seen_ids.add(cm_id)

        if _is_excluded(artist, criteria):
            continue

        candidates.append(_format_artist_result(artist))

    # Sort by monthly listeners descending as a baseline ranking
    candidates.sort(
        key=lambda a: a.get("sp_monthly_listeners") or 0,
        reverse=True,
    )

    return {
        "profile": profile_name,
        "profile_description": (
            profile_overrides.get("description", "Default search criteria")
            if profile_overrides
            else "Default search criteria"
        ),
        "filter_params": filter_params,
        "stat_params": stat_params,
        "candidate_count": len(candidates),
        "candidates": candidates[:50],  # cap at 50 to keep response reasonable
    }


@mcp.tool()
def discover_artists_multi_country(profile_name: str = "default") -> dict:
    """Run discovery across all configured target countries.

    Unlike discover_artists which queries one country, this iterates
    through all countries in the search criteria and merges results.
    Use this for the weekly discovery scan.

    Args:
        profile_name: Which search profile to use.
    """
    criteria_result = load_config("search_criteria")
    criteria = criteria_result.get("config", {})

    profile_overrides = None
    if profile_name != "default":
        profile_result = get_profile(profile_name)
        profile_overrides = profile_result.get("profile", {})

    filters = criteria.get("filters", criteria)
    if profile_overrides:
        overrides = profile_overrides.get("filter_overrides", {})
        filters = {**filters, **overrides}

    countries = filters.get("countries", ["CO", "MX", "AR", "CL", "PE"])

    all_candidates = []
    seen_ids = set()
    country_counts = {}

    for country in countries:
        # Override country for this iteration
        country_criteria = {**criteria}
        country_filters = {**criteria.get("filters", {}), "countries": [country]}
        country_criteria["filters"] = country_filters

        params = _build_filter_params(country_criteria, profile_overrides)
        try:
            data = api_get("/api/artist/list/filter", params=params)
            artists = data.get("obj", {}).get("obj", [])
        except Exception:
            artists = []

        count = 0
        for artist in artists:
            cm_id = artist.get("cm_artist", artist.get("chartmetric_artist_id"))
            if cm_id is None or cm_id in seen_ids:
                continue
            seen_ids.add(cm_id)

            if _is_excluded(artist, criteria):
                continue

            result = _format_artist_result(artist)
            result["discovery_country"] = country
            all_candidates.append(result)
            count += 1

        country_counts[country] = count

    all_candidates.sort(
        key=lambda a: a.get("sp_monthly_listeners") or 0,
        reverse=True,
    )

    return {
        "profile": profile_name,
        "countries_searched": countries,
        "candidates_per_country": country_counts,
        "total_candidates": len(all_candidates),
        "candidates": all_candidates[:100],
    }
