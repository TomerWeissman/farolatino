"""Chartmetric artist data — pull full artist profile from multiple endpoints.

This is the core data-fetching tool. Given a Chartmetric artist ID, it calls
~10 API endpoints and assembles the results into the unified dict format
that the scoring engine expects.

Endpoints called:
1. GET /api/artist/:id              — metadata (name, genres, label, career)
2. GET /api/artist/:id/cmStats      — all platform metrics + diffs
3. GET /api/artist/:id/career       — career stage + momentum (latest)
4. GET /api/artist/:id/cpp          — cross-platform performance score
5. GET /api/artist/:id/stat/spotify — Spotify stats (followers_to_listeners_ratio)
6. GET /api/artist/:id/instagram-audience-stats — IG engagement rate + geo
7. GET /api/artist/:id/milestones   — platform milestones
8. GET /api/artist/:id/neighboring-artists — similar artists
9. GET /api/artist/:id/albums       — discography
10. GET /api/artist/:id/spotify_top_daily/charts — chart appearances
11. GET /api/artist/:id/spotify/current/playlists — playlist placements
"""

import time
from datetime import datetime, timedelta

from mcp_server.server import mcp
from mcp_server.tools.chartmetric_auth import api_get
from mcp_server.tools.data_cache import raw_cache_get, raw_cache_set


def _safe_int(val, default=0) -> int:
    """Safely convert a value to int, handling None and strings."""
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _safe_float(val, default=None) -> float | None:
    """Safely convert a value to float."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _safe_get(data: dict, *keys, default=None):
    """Safely navigate nested dicts."""
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def _cached_fetch(cm_id: int, data_type: str, fetch_fn, use_cache: bool = True):
    """Check cache before calling the API. Stores the result after fetching."""
    if use_cache:
        cached = raw_cache_get(cm_id, data_type)
        if cached is not None:
            return cached

    result = fetch_fn(cm_id)
    raw_cache_set(cm_id, data_type, result)
    return result


def _fetch_metadata(cm_id: int) -> dict:
    """GET /api/artist/:id — core identity and metadata."""
    try:
        data = api_get(f"/api/artist/{cm_id}")
        return data.get("obj", {})
    except Exception:
        return {}


def _fetch_cm_stats(cm_id: int) -> dict:
    """GET /api/artist/:id/cmStats — all platform metrics + diffs."""
    try:
        data = api_get(f"/api/artist/{cm_id}/cmStats")
        return data.get("obj", {})
    except Exception:
        return {}


def _fetch_career(cm_id: int) -> dict:
    """GET /api/artist/:id/career — latest career stage + momentum."""
    try:
        data = api_get(f"/api/artist/{cm_id}/career", params={"limit": 1})
        entries = data.get("obj", [])
        if entries and isinstance(entries, list):
            return entries[0]
        return {}
    except Exception:
        return {}


def _fetch_cpp(cm_id: int) -> float:
    """GET /api/artist/:id/cpp — latest CPP score."""
    try:
        data = api_get(
            f"/api/artist/{cm_id}/cpp",
            params={"stat": "score", "latest": "true"},
        )
        entries = data.get("obj", [])
        if entries and isinstance(entries, list):
            return _safe_float(entries[0].get("score"), 0.0)
        return 0.0
    except Exception:
        return 0.0


def _fetch_spotify_stats(cm_id: int) -> dict:
    """GET /api/artist/:id/stat/spotify — follower/listener ratio + time series."""
    try:
        since = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        data = api_get(
            f"/api/artist/{cm_id}/stat/spotify",
            params={"since": since, "latest": "true"},
        )
        return data.get("obj", {})
    except Exception:
        return {}


def _fetch_ig_audience(cm_id: int) -> dict:
    """GET /api/artist/:id/instagram-audience-stats — engagement rate + geo."""
    try:
        data = api_get(f"/api/artist/{cm_id}/instagram-audience-stats")
        return data.get("obj", {})
    except Exception:
        return {}


def _fetch_milestones(cm_id: int) -> list:
    """GET /api/artist/:id/milestones — platform milestones."""
    try:
        data = api_get(
            f"/api/artist/{cm_id}/milestones",
            params={"limit": 20, "sortOrderDesc": "true"},
        )
        return _safe_get(data, "obj", "insights", default=[])
    except Exception:
        return []


def _fetch_neighboring_artists(cm_id: int) -> list:
    """GET /api/artist/:id/neighboring-artists — similar genre artists."""
    try:
        data = api_get(
            f"/api/artist/{cm_id}/neighboring-artists",
            params={"limit": 10},
        )
        return data.get("obj", {}).get("cluster_artists", [])
    except Exception:
        return []


def _fetch_albums(cm_id: int) -> list:
    """GET /api/artist/:id/albums — discography."""
    try:
        data = api_get(f"/api/artist/{cm_id}/albums")
        return data.get("obj", [])
    except Exception:
        return []


def _fetch_charts(cm_id: int) -> dict:
    """GET /api/artist/:id/spotify_top_daily/charts — chart appearances."""
    try:
        since = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
        data = api_get(
            f"/api/artist/{cm_id}/spotify_top_daily/charts",
            params={"since": since},
        )
        return data.get("obj", {})
    except Exception:
        return {}


def _fetch_playlists(cm_id: int) -> list:
    """GET /api/artist/:id/spotify/current/playlists — current playlist placements."""
    try:
        data = api_get(
            f"/api/artist/{cm_id}/spotify/current/playlists",
            params={"editorial": "true", "indie": "true"},
        )
        return data.get("obj", [])
    except Exception:
        return []


def _fetch_tracks(cm_id: int) -> list:
    """GET /api/artist/:id/tracks — full track catalog with per-track release dates.

    Chartmetric's /tracks endpoint supports neither sort nor date filters,
    so we paginate (up to 5 pages of 200 = 1000 tracks) to capture recent
    releases even when the catalog ordering is oldest-first.
    """
    page_size = 200
    max_pages = 5
    all_tracks: list = []
    try:
        for page in range(max_pages):
            data = api_get(
                f"/api/artist/{cm_id}/tracks",
                params={"limit": page_size, "offset": page * page_size},
            )
            obj = data.get("obj", [])
            if isinstance(obj, dict):
                obj = obj.get("data", []) or obj.get("tracks", []) or []
            if not isinstance(obj, list) or not obj:
                break
            all_tracks.extend(obj)
            if len(obj) < page_size:
                break
        return all_tracks
    except Exception:
        return all_tracks


def _fetch_where_people_listen(cm_id: int) -> dict:
    """GET /api/artist/:id/where-people-listen — per-country/city listener stats
    with current + previous snapshots."""
    try:
        data = api_get(f"/api/artist/{cm_id}/where-people-listen")
        return data.get("obj", {})
    except Exception:
        return {}


def _fetch_noteworthy_insights(cm_id: int) -> list:
    """GET /api/artist/:id/noteworthy-insights — breakout/trend signals."""
    try:
        data = api_get(f"/api/artist/{cm_id}/noteworthy-insights")
        obj = data.get("obj", [])
        if isinstance(obj, dict):
            return obj.get("insights", []) or obj.get("data", []) or []
        return obj if isinstance(obj, list) else []
    except Exception:
        return []


def _extract_genres(metadata: dict) -> list[str]:
    """Extract genre names from the nested genres structure."""
    genres_obj = metadata.get("genres", {})
    if not isinstance(genres_obj, dict):
        return []

    genre_names = []
    primary = genres_obj.get("primary")
    if primary and isinstance(primary, dict):
        genre_names.append(primary["name"])

    for secondary in genres_obj.get("secondary", []):
        if isinstance(secondary, dict) and "name" in secondary:
            genre_names.append(secondary["name"])

    for sub in genres_obj.get("sub", []):
        if isinstance(sub, dict) and "name" in sub:
            genre_names.append(sub["name"])

    return genre_names


def _rollup_timeseries(series: list) -> tuple[int, int, str, str]:
    """Collapse a time-series of listener samples into (current, previous, code2, latest_timestp).

    Takes the most recent sample as current and the earliest in the window as
    previous. Skips entries missing timestp or listeners.
    """
    if not isinstance(series, list) or not series:
        return 0, 0, "", ""
    valid = [e for e in series if isinstance(e, dict) and e.get("timestp")]
    if not valid:
        return 0, 0, "", ""
    valid.sort(key=lambda e: e["timestp"])
    latest = valid[-1]
    earliest = valid[0]
    code = (latest.get("code2") or "").upper()
    return (
        _safe_int(latest.get("listeners")),
        _safe_int(earliest.get("listeners")),
        code,
        latest.get("timestp", ""),
    )


def _build_listener_countries(wpl_data: dict, metadata: dict) -> list[dict]:
    """Extract per-country listener stats from the where-people-listen endpoint.

    The endpoint returns {countries: {CountryName: [time-series]}}. We roll up
    each series: last sample = current listeners, first sample = prev listeners.
    Falls back to metadata's embedded `cm_statistics.sp_where_people_listen`
    if the dedicated endpoint returned nothing.
    """
    countries = wpl_data.get("countries") if isinstance(wpl_data, dict) else None

    result: list[dict] = []
    if isinstance(countries, dict):
        for _name, series in countries.items():
            current, prev, code, _ = _rollup_timeseries(series)
            if not code:
                continue
            result.append({
                "country_code": code,
                "listeners": current,
                "prev_listeners": prev,
            })
        result.sort(key=lambda c: c["listeners"], reverse=True)
        if result:
            return result

    # Fallback: metadata's embedded snapshot (no prev_listeners available)
    cm_stats = metadata.get("cm_statistics", {}) if isinstance(metadata, dict) else {}
    wpl = cm_stats.get("sp_where_people_listen", [])
    if not wpl:
        return []
    return [
        {
            "country_code": entry.get("code2", "").upper(),
            "listeners": _safe_int(entry.get("listeners")),
            "prev_listeners": 0,
        }
        for entry in wpl
        if entry.get("code2")
    ]


def _build_listener_cities(wpl_data: dict) -> list[dict]:
    """Extract per-city listener stats from the where-people-listen endpoint.

    Shape: {cities: {CityName: [time-series]}}. Latest sample = current, earliest = prev.
    """
    if not isinstance(wpl_data, dict):
        return []
    cities = wpl_data.get("cities")
    if not isinstance(cities, dict):
        return []

    rows = []
    for name, series in cities.items():
        current, prev, code, _ = _rollup_timeseries(series)
        if not name or not code:
            continue
        rows.append({
            "city": name,
            "country_code": code,
            "listeners": current,
            "prev_listeners": prev,
        })
    rows.sort(key=lambda c: c["listeners"], reverse=True)
    return rows[:50]


def _build_noteworthy_insights(raw_insights: list) -> list[dict]:
    """Normalize noteworthy-insights entries to a stable shape.

    Chartmetric keys observed: insight, insightType, platform, insightDate,
    title, metricName, variant.
    """
    result = []
    for item in raw_insights[:30]:
        if not isinstance(item, dict):
            continue
        date = item.get("insightDate") or item.get("date") or item.get("timestamp") or ""
        result.append({
            "type": item.get("insightType") or item.get("type") or "",
            "platform": item.get("platform") or item.get("source") or "",
            "date": (date or "")[:10],
            "text": (
                item.get("insight")
                or item.get("title")
                or item.get("text")
                or item.get("summary")
                or ""
            ),
            "metric": item.get("metricName") or "",
            "variant": item.get("variant") or "",
        })
    return result


def _build_tracks_from_api(raw_tracks: list) -> list[dict]:
    """Normalize the /tracks endpoint payload to the profile's track shape.

    Chartmetric returns `release_dates` as a list (one per album appearance);
    we use the earliest as the track's first-release date. `version_types` is
    a dict of flags — first True key wins.
    """
    tracks = []
    for t in raw_tracks:
        if not isinstance(t, dict):
            continue

        release_dates = t.get("release_dates") or []
        if isinstance(release_dates, list) and release_dates:
            dates = sorted(d for d in release_dates if isinstance(d, str) and d)
            release_date = dates[0][:10] if dates else ""
        else:
            release_date = (t.get("release_date") or "")[:10]

        vtypes = t.get("version_types")
        if isinstance(vtypes, dict):
            version_type = next(
                (k for k, v in vtypes.items() if v),
                t.get("version_type") or "original",
            )
        else:
            version_type = t.get("version_type") or "original"

        labels = t.get("album_label")
        if isinstance(labels, list) and labels:
            album_label = labels[0] or ""
        else:
            album_label = t.get("album_label") or t.get("label") or ""

        tracks.append({
            "name": t.get("name") or t.get("title") or "",
            "release_date": release_date,
            "isrc": t.get("isrc") or "",
            "version_type": version_type,
            "album_label": album_label,
        })
    return tracks


def _build_tracks_from_albums(albums: list) -> list[dict]:
    """Build a simplified track list from album data.

    The full track catalog comes from album data since there's no
    direct artist/tracks endpoint that returns release dates cleanly.
    """
    tracks = []
    for album in albums:
        if not isinstance(album, dict):
            continue
        release_date = album.get("release_date", "")
        label = album.get("label", "")
        name = album.get("name", "")
        is_single = album.get("is_single", False)

        tracks.append({
            "name": name,
            "release_date": release_date[:10] if release_date else "",
            "isrc": "",
            "version_type": "original",
            "album_label": label,
        })

    return tracks


def _build_albums(raw_albums: list) -> list[dict]:
    """Convert raw album API data to our album format."""
    albums = []
    for album in raw_albums:
        if not isinstance(album, dict):
            continue
        albums.append({
            "name": album.get("name", ""),
            "release_date": (album.get("release_date", "") or "")[:10],
            "track_count": _safe_int(album.get("num_track")),
            "album_type": "single" if album.get("is_single") else "album",
        })
    return albums


def _build_playlists(raw_playlists: list) -> list[dict]:
    """Convert raw playlist API data to our playlist format."""
    playlists = []
    for entry in raw_playlists:
        if not isinstance(entry, dict):
            continue
        playlist = entry.get("playlist", entry)
        if not isinstance(playlist, dict):
            continue
        playlists.append({
            "playlist_name": playlist.get("name", ""),
            "platform": "spotify",
            "is_editorial": bool(playlist.get("editorial", False)),
            "followers": _safe_int(playlist.get("followers")),
            "position": entry.get("position"),
            "added_date": entry.get("added_at", ""),
        })
    return playlists


def _build_chart_appearances(chart_data: dict) -> list[dict]:
    """Convert raw chart API data to our chart format."""
    entries = _safe_get(chart_data, "data", "entries", default=[])
    charts = []
    for entry in entries[:50]:  # cap at 50 to keep payload reasonable
        if not isinstance(entry, dict):
            continue
        charts.append({
            "chart_name": entry.get("chart_name", ""),
            "platform": "spotify",
            "country": entry.get("code2", ""),
            "peak_position": _safe_int(entry.get("peak_rank")),
            "date": entry.get("added_at", ""),
        })
    return charts


def _build_milestones(raw_milestones: list) -> list[dict]:
    """Convert raw milestone API data to our milestone format."""
    milestones = []
    for ms in raw_milestones[:30]:
        if not isinstance(ms, dict):
            continue
        milestones.append({
            "text": ms.get("summary", ""),
            "date": ms.get("date", ""),
            "platform": ms.get("platform", ""),
            "star_rating": _safe_int(ms.get("stars")),
        })
    return milestones


def _build_neighboring(raw_neighbors: list) -> list[dict]:
    """Convert raw neighboring artist data to our format."""
    neighbors = []
    for n in raw_neighbors[:15]:
        if not isinstance(n, dict):
            continue
        neighbors.append({
            "name": n.get("name", ""),
            "cm_id": _safe_int(n.get("id")),
            "career_stage": "",
            "signed": bool(n.get("signed", False)),
            "recent_momentum": "",
        })
    return neighbors


def _count_recent_releases(tracks: list[dict], months: int) -> int:
    """Count releases within the last N months."""
    if not tracks:
        return 0
    cutoff = (datetime.now() - timedelta(days=months * 30)).strftime("%Y-%m-%d")
    return sum(
        1 for t in tracks
        if t.get("release_date", "") >= cutoff
    )


# Fields that must be populated for a profile to be considered "complete".
# Zero is an implausible real-world value for most of these, so we treat it
# the same as missing. Lists/dicts must be non-empty.
_COMPLETENESS_FIELDS = [
    ("name", "str"),
    ("genres", "list"),
    ("career_stage", "str"),
    ("sp_monthly_listeners", "num"),
    ("sp_followers", "num"),
    ("sp_popularity", "num"),
    ("yt_subscribers", "num"),
    ("tiktok_followers", "num"),
    ("ig_followers", "num"),
    ("cpp_score", "num"),
    ("listener_countries", "list"),
    ("tracks", "list"),
    ("albums", "list"),
    ("playlists", "list"),
    ("milestones", "list"),
    ("noteworthy_insights", "list"),
]


def _is_populated(value, kind: str) -> bool:
    if value is None:
        return False
    if kind == "list":
        return isinstance(value, list) and len(value) > 0
    if kind == "dict":
        return isinstance(value, dict) and len(value) > 0
    if kind == "str":
        return isinstance(value, str) and bool(value.strip())
    if kind == "num":
        try:
            return float(value) != 0.0
        except (TypeError, ValueError):
            return False
    return bool(value)


def _compute_completeness(profile: dict) -> float:
    """Fraction of required fields that are meaningfully populated."""
    populated = sum(
        1 for key, kind in _COMPLETENESS_FIELDS
        if _is_populated(profile.get(key), kind)
    )
    return round(populated / len(_COMPLETENESS_FIELDS), 3)


@mcp.tool()
def get_artist_data(cm_artist_id: int, use_cache: bool = True) -> dict:
    """Pull complete artist data from Chartmetric for scoring.

    Calls ~10 API endpoints and assembles the results into the unified
    format expected by the scoring engine. Results are cached automatically
    so repeated lookups don't burn API calls — each data type has its own
    TTL (streaming stats expire daily, discography every 2 weeks, etc.).

    Args:
        cm_artist_id: The Chartmetric artist ID (from search_artists)
        use_cache: If True (default), return cached data when fresh.
                   Set to False to force a full refresh from the API.

    Returns:
        A dict matching the ArtistProfile structure, ready for
        compute_prospect_score() or generate_dossier().
    """
    c = use_cache  # shorthand

    # Fetch all data sources (sequential to respect rate limits, cached per-endpoint)
    metadata = _cached_fetch(cm_artist_id, "metadata", _fetch_metadata, c)
    cm_stats = _cached_fetch(cm_artist_id, "cmstats", _fetch_cm_stats, c)
    career = _cached_fetch(cm_artist_id, "career", _fetch_career, c)
    cpp = _cached_fetch(cm_artist_id, "cpp", _fetch_cpp, c)
    sp_stats = _cached_fetch(cm_artist_id, "spotify_stats", _fetch_spotify_stats, c)
    ig_audience = _cached_fetch(cm_artist_id, "ig_audience", _fetch_ig_audience, c)
    raw_milestones = _cached_fetch(cm_artist_id, "milestones", _fetch_milestones, c)
    raw_neighbors = _cached_fetch(cm_artist_id, "neighboring", _fetch_neighboring_artists, c)
    raw_albums = _cached_fetch(cm_artist_id, "albums", _fetch_albums, c)
    chart_data = _cached_fetch(cm_artist_id, "charts", _fetch_charts, c)
    raw_playlists = _cached_fetch(cm_artist_id, "playlists", _fetch_playlists, c)
    raw_tracks = _cached_fetch(cm_artist_id, "tracks", _fetch_tracks, c)
    wpl_data = _cached_fetch(cm_artist_id, "where_people_listen", _fetch_where_people_listen, c)
    raw_insights = _cached_fetch(cm_artist_id, "insights", _fetch_noteworthy_insights, c)

    # Extract stats from cmStats response
    latest = cm_stats.get("latest", {})
    weekly_diff_pct = cm_stats.get("weekly_diff_percent", {})
    monthly_diff_pct = cm_stats.get("monthly_diff_percent", {})

    # Extract career info (prefer metadata's career_status, fall back to career endpoint)
    career_status = metadata.get("career_status", {})
    if not career_status and career:
        career_status = career

    # Extract follower-to-listener ratio from Spotify stats
    sp_ftl_ratio = None
    ftl_data = sp_stats.get("followers_to_listeners_ratio", [])
    if ftl_data and isinstance(ftl_data, list):
        sp_ftl_ratio = _safe_float(ftl_data[0].get("value"))

    # If no ratio from time series, check metadata's cm_statistics
    if sp_ftl_ratio is None:
        cm_statistics = metadata.get("cm_statistics", {})
        sp_ftl_ratio = _safe_float(
            cm_statistics.get("sp_followers_to_listeners_ratio")
        )

    # Build the unified artist profile dict.
    # Prefer the dedicated /tracks endpoint; fall back to deriving from albums
    # (1 album = 1 track) if the endpoint returned nothing.
    tracks = _build_tracks_from_api(raw_tracks)
    if not tracks:
        tracks = _build_tracks_from_albums(raw_albums)

    profile = {
        # Identity
        "cm_id": cm_artist_id,
        "name": metadata.get("name", ""),
        "genres": _extract_genres(metadata),
        "career_stage": career_status.get("stage", ""),
        "career_trend": career_status.get("trend", ""),
        "career_momentum_score": _safe_float(
            career_status.get("trend_score"), 0.0
        ),
        "record_label": metadata.get("record_label"),
        "distributor": None,
        "image_url": metadata.get("image_url"),

        # Streaming & social metrics
        "sp_monthly_listeners": _safe_int(latest.get("sp_monthly_listeners")),
        "sp_monthly_listeners_diff_pct": _safe_float(
            monthly_diff_pct.get("sp_monthly_listeners")
        ),
        "sp_followers": _safe_int(latest.get("sp_followers")),
        "sp_followers_diff_pct": _safe_float(
            monthly_diff_pct.get("sp_followers")
        ),
        "sp_followers_to_listeners_ratio": sp_ftl_ratio,
        "sp_popularity": _safe_int(latest.get("sp_popularity")),
        "yt_subscribers": _safe_int(latest.get("ycs_subscribers")),
        "yt_subscribers_diff_pct": _safe_float(
            monthly_diff_pct.get("ycs_subscribers")
        ),
        "yt_views": _safe_int(latest.get("ycs_views")),
        "yt_daily_views": _safe_int(latest.get("youtube_daily_video_views")),
        "tiktok_followers": _safe_int(latest.get("tiktok_followers")),
        "tiktok_followers_diff_pct": _safe_float(
            monthly_diff_pct.get("tiktok_followers")
        ),
        "tiktok_likes": _safe_int(latest.get("tiktok_likes")),
        "ig_followers": _safe_int(latest.get("ins_followers")),
        "ig_followers_diff_pct": _safe_float(
            monthly_diff_pct.get("ins_followers")
        ),
        "shazam_count": _safe_int(latest.get("shazam_count")),
        "shazam_count_diff_pct": _safe_float(
            monthly_diff_pct.get("shazam_count")
        ),
        "deezer_fans": _safe_int(latest.get("deezer_fans")),
        "soundcloud_followers": _safe_int(latest.get("soundcloud_followers")),
        "cpp_score": cpp,

        # Geographic
        "listener_countries": _build_listener_countries(wpl_data, metadata),
        "listener_cities": _build_listener_cities(wpl_data),
        "social_audience_countries": {},

        # Catalog
        "tracks": tracks,
        "albums": _build_albums(raw_albums),
        "recent_release_count_6m": _count_recent_releases(tracks, 6),
        "recent_release_count_12m": _count_recent_releases(tracks, 12),

        # Playlists & charts
        "playlists": _build_playlists(raw_playlists),
        "chart_appearances": _build_chart_appearances(chart_data),

        # Signals
        "milestones": _build_milestones(raw_milestones),
        "noteworthy_insights": _build_noteworthy_insights(raw_insights),
        "neighboring_artists": _build_neighboring(raw_neighbors),

        # Engagement
        "ig_engagement_rate": _safe_float(ig_audience.get("engagement_rate")),

        # Metadata
        "data_fetched_at": datetime.now().isoformat(),
        "data_completeness": 0.0,
    }

    # Add IG audience geographic data if available
    ig_countries = ig_audience.get("top_countries", [])
    if ig_countries:
        profile["social_audience_countries"]["instagram"] = [
            {"country_code": c.get("code", ""), "percent": _safe_float(c.get("percent"), 0)}
            for c in ig_countries
        ]

    profile["data_completeness"] = _compute_completeness(profile)

    return profile
