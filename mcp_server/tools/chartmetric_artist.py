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

from core.cadence import compute_release_cadence
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


def _fetch_youtube_audience(cm_id: int) -> dict:
    """GET /api/artist/:id/youtube-audience-stats — YouTube subscriber geography."""
    try:
        data = api_get(f"/api/artist/{cm_id}/youtube-audience-stats")
        return data.get("obj", {})
    except Exception:
        return {}


def _fetch_tiktok_audience(cm_id: int) -> dict:
    """GET /api/artist/:id/tiktok-audience-stats — TikTok follower geography."""
    try:
        data = api_get(f"/api/artist/{cm_id}/tiktok-audience-stats")
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
    """GET /api/artist/:id/neighboring-artists — similar artists by Chartmetric clustering.

    Response shape is `{"obj": [...]}` — the list comes back directly, NOT
    nested under `cluster_artists`. (Easy to miss; was causing empty
    similar-artists lists in early phases.)
    """
    try:
        data = api_get(
            f"/api/artist/{cm_id}/neighboring-artists",
            params={"limit": 15},
        )
        obj = data.get("obj")
        if isinstance(obj, list):
            return obj
        if isinstance(obj, dict):
            # Defensive fallback in case the API ever changes shape
            return obj.get("cluster_artists") or obj.get("data") or obj.get("artists") or []
        return []
    except Exception:
        return []


def _search_similar_artists_by_genre(
    primary_genre: str,
    sp_monthly_listeners: int | None,
    exclude_cm_id: int | None = None,
    limit: int = 10,
) -> list:
    """Fallback similar-artists search via genre query.

    Used when /neighboring-artists returns too few results, or when the
    cluster artists are off-genre (Chartmetric's clustering occasionally
    returns globally-similar acts that aren't a real LATAM-music match).

    Filters search results to a 3x band around the seed artist's Spotify
    monthly listeners so the comparison is tier-appropriate.
    """
    if not primary_genre:
        return []
    try:
        # search_artists is imported lazily to avoid circular imports
        from mcp_server.tools.chartmetric_search import search_artists

        result = search_artists(primary_genre, limit=20)
        candidates = result.get("artists") or []
    except Exception:
        return []

    if sp_monthly_listeners and sp_monthly_listeners > 0:
        lo = sp_monthly_listeners / 3
        hi = sp_monthly_listeners * 3
    else:
        lo, hi = 0, float("inf")

    out: list[dict] = []
    for c in candidates:
        cm_id_val = _safe_int(c.get("cm_id"))
        if not cm_id_val or cm_id_val == exclude_cm_id:
            continue
        listeners = _safe_int(c.get("sp_monthly_listeners"))
        # Allow null-listener entries through but deprioritize them at end
        if listeners and not (lo <= listeners <= hi):
            continue
        out.append({
            "id": cm_id_val,
            "name": c.get("name") or "",
            "code2": (c.get("code2") or ""),
            "image_url": c.get("image_url") or "",
            "sp_monthly_listeners": listeners,
            "sp_followers": _safe_int(c.get("sp_followers")),
            "signed": bool(c.get("signed", False)),
        })
        if len(out) >= limit:
            break
    return out


def _merge_similar_artists(neighbors: list, fallback: list, limit: int = 10) -> list:
    """Merge Chartmetric neighbors + genre-search fallback, dedupe by cm_id."""
    seen: set[int] = set()
    merged: list = []
    for source_label, items in (("chartmetric_neighbors", neighbors), ("genre_search", fallback)):
        for n in items:
            if not isinstance(n, dict):
                continue
            cid = _safe_int(n.get("id") or n.get("cm_id"))
            if not cid or cid in seen:
                continue
            seen.add(cid)
            merged.append({**n, "_similarity_source": source_label})
            if len(merged) >= limit * 2:
                return merged
    return merged


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
    """Convert raw neighboring artist data to our format.

    Chartmetric returns rich fields (name, country, image, social URLs,
    Spotify monthly listeners) — keep the ones useful for ranking and
    surfacing in a "similar artists" view.
    """
    neighbors = []
    for n in raw_neighbors[:15]:
        if not isinstance(n, dict):
            continue
        neighbors.append({
            "name": n.get("name", ""),
            "cm_id": _safe_int(n.get("id")),
            "country_code": (n.get("code2") or "").upper(),
            "image_url": n.get("image_url") or "",
            "career_stage": "",
            "signed": bool(n.get("signed", False)),
            "recent_momentum": "",
            "sp_monthly_listeners": _safe_int(n.get("sp_monthly_listeners")),
            "sp_followers": _safe_int(n.get("sp_followers")),
            "source": "chartmetric_neighbors",
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


# ─── v0.5.0 enrichment ──────────────────────────────────────────────
#
# These pull data directly from Spotify and YouTube (not Chartmetric) to
# answer questions Chartmetric's snapshot can't: per-track popularity,
# audio features (danceability/energy/tempo), and YouTube content
# velocity. Every step is wrapped — a missing Spotify ID or rate-limited
# YouTube call must NOT break the dossier path.


def _resolve_spotify_artist_id(metadata: dict, artist_name: str) -> str | None:
    """Find a Spotify artist ID for this Chartmetric artist.

    Tries Chartmetric metadata first (in case a future API revision
    surfaces it), then falls back to a Spotify name search. Returns
    ``None`` if neither path produces an ID.
    """
    cm_stats = metadata.get("cm_statistics") or {}
    for key in ("sp_id", "spotify_id", "spotify_artist_id"):
        v = metadata.get(key) or cm_stats.get(key)
        if isinstance(v, str) and v:
            return v
    if not artist_name:
        return None
    try:
        from mcp_server.tools.spotify_search import search_spotify_artist
        result = search_spotify_artist(artist_name, limit=1)
        artists = result.get("artists") or []
        if artists:
            return artists[0].get("spotify_id")
    except Exception:
        return None
    return None


def _fetch_sp_top_tracks_and_features(spotify_id: str) -> tuple[list[dict], dict]:
    """Call Spotify top-tracks + audio-features, return (tracks, avg_features).

    Degrades silently — any error returns ``([], {})``.
    """
    try:
        from mcp_server.tools.spotify_search import (
            get_spotify_artist_top_tracks,
            get_spotify_audio_features,
        )
        top = get_spotify_artist_top_tracks(spotify_id, limit=5)
        tracks = top.get("tracks") or []
        track_ids = [t.get("id") for t in tracks if t.get("id")]
        if not track_ids:
            return tracks, {}
        feats = get_spotify_audio_features(track_ids)
        return tracks, feats.get("average") or {}
    except Exception:
        return [], {}


def _resolve_youtube_channel_info(artist_name: str) -> dict:
    """Resolve a channel_id + uploads_playlist_id for the artist.

    Two YouTube calls (search_youtube_channel, get_youtube_channel) —
    both have quota costs, so we only run this on a cold
    get_artist_data and bundle the result so downstream calls reuse
    the same channel_id.
    """
    out = {"channel_id": None, "uploads_playlist_id": None}
    if not artist_name:
        return out
    try:
        from mcp_server.tools.youtube_search import (
            search_youtube_channel,
            get_youtube_channel,
        )
        search = search_youtube_channel(artist_name, limit=1)
        channels = search.get("channels") or []
        if not channels:
            return out
        channel_id = channels[0].get("channel_id")
        if not channel_id:
            return out
        out["channel_id"] = channel_id
        details = get_youtube_channel(channel_id)
        out["uploads_playlist_id"] = details.get("uploads_playlist_id")
        return out
    except Exception:
        return out


def _fetch_yt_latest_videos(uploads_playlist_id: str) -> list[dict]:
    """Pull the channel's latest 3 videos. Returns ``[]`` on any error."""
    try:
        from mcp_server.tools.youtube_search import get_youtube_latest_videos
        result = get_youtube_latest_videos(uploads_playlist_id, limit=3)
        return result.get("videos") or []
    except Exception:
        return []


def _fetch_yt_top_videos(channel_id: str) -> list[dict]:
    """Pull the channel's top 3 videos by lifetime views. ``[]`` on error."""
    try:
        from mcp_server.tools.youtube_search import get_youtube_top_videos
        result = get_youtube_top_videos(channel_id, limit=3)
        return result.get("videos") or []
    except Exception:
        return []


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
    # Genre-search fallback for similar artists. Cached as a separate slot so
    # we don't re-issue the search every time get_artist_data is called.
    def _fetch_genre_search(_id):
        # Best-effort: extract primary genre from already-fetched metadata.
        genres = _extract_genres(metadata)
        primary = genres[0] if genres else ""
        listeners = _safe_int((cm_stats.get("latest") or {}).get("sp_monthly_listeners"))
        if not primary:
            return []
        return _search_similar_artists_by_genre(primary, listeners or None, exclude_cm_id=cm_artist_id)
    raw_genre_similars = _cached_fetch(cm_artist_id, "similar_genre", _fetch_genre_search, c)
    raw_albums = _cached_fetch(cm_artist_id, "albums", _fetch_albums, c)
    chart_data = _cached_fetch(cm_artist_id, "charts", _fetch_charts, c)
    raw_playlists = _cached_fetch(cm_artist_id, "playlists", _fetch_playlists, c)
    raw_tracks = _cached_fetch(cm_artist_id, "tracks", _fetch_tracks, c)
    wpl_data = _cached_fetch(cm_artist_id, "where_people_listen", _fetch_where_people_listen, c)
    raw_insights = _cached_fetch(cm_artist_id, "insights", _fetch_noteworthy_insights, c)
    yt_audience = _cached_fetch(cm_artist_id, "yt_audience", _fetch_youtube_audience, c)
    tt_audience = _cached_fetch(cm_artist_id, "tt_audience", _fetch_tiktok_audience, c)

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
        # `code2` is Chartmetric's ISO-3166-1 alpha-2 country field. Was
        # previously dropped on the floor here; downstream consumers
        # (composite_similar's country filter, the dossier's geographic
        # profile) need it.
        "country_code": (metadata.get("code2") or "").upper() or None,

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
        "neighboring_artists": _build_neighboring(
            _merge_similar_artists(raw_neighbors, raw_genre_similars, limit=15)
        ),

        # Engagement
        "ig_engagement_rate": _safe_float(ig_audience.get("engagement_rate")),

        # Metadata
        "data_fetched_at": datetime.now().isoformat(),
        "data_completeness": 0.0,
    }

    # ─── Step 7: native Spotify + YouTube enrichment (v0.5.0) ──────────
    #
    # Per-track popularity + audio features (Sound profile), plus
    # YouTube content velocity. Cached per data type — cold lookup only.
    # Every fetch wrapped in try/except so the dossier still ships when
    # an enrichment partner is rate-limited or unavailable.
    artist_name = profile.get("name") or ""

    def _fetch_sp_enrichment(_id):
        spid = _resolve_spotify_artist_id(metadata, artist_name)
        if not spid:
            return {"sp_artist_id": None, "top_tracks": [], "audio_features": {}}
        tracks, avg_feats = _fetch_sp_top_tracks_and_features(spid)
        return {"sp_artist_id": spid, "top_tracks": tracks, "audio_features": avg_feats}

    def _fetch_yt_enrichment(_id):
        info = _resolve_youtube_channel_info(artist_name)
        channel_id = info["channel_id"]
        playlist_id = info["uploads_playlist_id"]
        if not channel_id:
            return {"channel_id": None, "uploads_playlist_id": None, "videos": [], "top_videos": []}
        return {
            "channel_id": channel_id,
            "uploads_playlist_id": playlist_id,
            "videos": _fetch_yt_latest_videos(playlist_id) if playlist_id else [],
            "top_videos": _fetch_yt_top_videos(channel_id),
        }

    sp_enrich = _cached_fetch(cm_artist_id, "sp_enrichment_v1", _fetch_sp_enrichment, c)
    # Bump cache slot name to v2 — the v1 payload didn't include
    # top_videos or channel_id; existing caches would short-circuit
    # us out of the new fields. Treating v0.5.2 as a fresh cold lookup
    # for the YT slot ensures Step 2's fields populate.
    yt_enrich = _cached_fetch(cm_artist_id, "yt_enrichment_v2", _fetch_yt_enrichment, c)

    profile["sp_artist_id"] = sp_enrich.get("sp_artist_id")
    profile["sp_top_tracks"] = sp_enrich.get("top_tracks") or []
    profile["sp_audio_features"] = sp_enrich.get("audio_features") or {}
    profile["yt_latest_videos"] = yt_enrich.get("videos") or []
    profile["yt_top_videos"] = yt_enrich.get("top_videos") or []

    # Add per-platform audience geography (used by revenue model for proper
    # per-(platform, country) CPM application). Country codes are normalized
    # to uppercase to match the `where-people-listen` payload.
    for plat, payload in (
        ("instagram", ig_audience),
        ("youtube", yt_audience),
        ("tiktok", tt_audience),
    ):
        countries = payload.get("top_countries", []) if isinstance(payload, dict) else []
        if countries:
            profile["social_audience_countries"][plat] = [
                {
                    "country_code": (c.get("code", "") or "").upper(),
                    "percent": _safe_float(c.get("percent"), 0),
                }
                for c in countries
                if c.get("code")
            ]

    profile["data_completeness"] = _compute_completeness(profile)

    return profile
