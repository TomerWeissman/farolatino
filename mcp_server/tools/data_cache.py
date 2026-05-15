"""Data cache — JSON file cache for artist data, keyed by artist ID + data type."""

import json
from datetime import datetime, timedelta
from pathlib import Path

from core.paths import cache_dir
from mcp_server.server import mcp


def _cache_dir() -> Path:
    """V2: cache lives under ~/Library/Application Support/FaroAI/cache/
    (or whatever ``cache_dir()`` resolves to per platform / FAROAI_CACHE_DIR
    override). Wrapped in a function so tests setting FAROAI_CACHE_DIR
    mid-run see the change without a module reload."""
    return cache_dir()


# Back-compat: V1 callers (scripts/compute_catalog_coverage.py, etc.) read
# ``CACHE_DIR`` directly. Resolved at import time, which is fine since
# the override env var typically isn't toggled mid-process.
CACHE_DIR = cache_dir()

# TTL per data type
CACHE_TTL = {
    "metadata": timedelta(days=1),
    "cmstats": timedelta(days=1),
    "career": timedelta(weeks=1),
    "cpp": timedelta(weeks=1),
    "spotify_stats": timedelta(days=1),
    "ig_audience": timedelta(weeks=1),
    "where_people_listen": timedelta(weeks=1),
    "social_audience": timedelta(weeks=1),
    "tracks": timedelta(weeks=2),
    "albums": timedelta(weeks=2),
    "playlists": timedelta(days=3),
    "charts": timedelta(weeks=1),
    "milestones": timedelta(weeks=1),
    "insights": timedelta(days=1),
    "neighboring": timedelta(weeks=2),
    "yt_audience": timedelta(weeks=1),
    "tt_audience": timedelta(weeks=1),
    "similar_genre": timedelta(weeks=2),
    "urls": timedelta(weeks=4),
    "score": timedelta(days=1),
    # Full @evaluate dossier (composite output). Short TTL because
    # tier / score can move on fresh Chartmetric daily snapshots and
    # the user wants the chat to feel current — but long enough that
    # follow-up turns ("What's her TikTok number?") within the same
    # conversation reuse the dossier instead of re-running the whole
    # pipeline. Profile-aware: key is `dossier_<profile_name>`.
    "dossier_default": timedelta(hours=1),
    "dossier_emerging_momentum": timedelta(hours=1),
    "dossier_revenue_focus": timedelta(hours=1),
    "dossier_latam_expansion": timedelta(hours=1),
}


def _cache_path(artist_id: int, data_type: str) -> Path:
    return _cache_dir() / str(artist_id) / f"{data_type}.json"


# --- Plain functions for internal use (importable by other modules) ---

def raw_cache_get(artist_id: int, data_type: str):
    """Check cache and return data if fresh, or None if expired/missing."""
    path = _cache_path(artist_id, data_type)
    if not path.exists():
        return None

    cached = json.loads(path.read_text())
    fetched_at = datetime.fromisoformat(cached["_fetched_at"])
    ttl = CACHE_TTL.get(data_type, timedelta(days=1))

    if datetime.now() - fetched_at > ttl:
        return None

    return cached["data"]


def raw_cache_set(artist_id: int, data_type: str, data) -> None:
    """Store any JSON-serializable data in cache."""
    path = _cache_path(artist_id, data_type)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "_fetched_at": datetime.now().isoformat(),
        "_data_type": data_type,
        "data": data,
    }
    path.write_text(json.dumps(payload, indent=2, default=str))


# --- MCP tools (for Claude to manage cache explicitly) ---

@mcp.tool()
def cache_get(artist_id: int, data_type: str) -> dict | None:
    """Retrieve cached data for an artist. Returns None if expired or missing.

    Args:
        artist_id: Chartmetric artist ID
        data_type: Type of data (e.g. 'metadata', 'cmstats', 'career', 'tracks')
    """
    path = _cache_path(artist_id, data_type)
    if not path.exists():
        return None

    cached = json.loads(path.read_text())
    fetched_at = datetime.fromisoformat(cached["_fetched_at"])
    ttl = CACHE_TTL.get(data_type, timedelta(days=1))

    if datetime.now() - fetched_at > ttl:
        return None  # expired

    return cached["data"]


@mcp.tool()
def cache_set(artist_id: int, data_type: str, data: dict) -> dict:
    """Store data in cache for an artist.

    Args:
        artist_id: Chartmetric artist ID
        data_type: Type of data (e.g. 'metadata', 'cmstats', 'career', 'tracks')
        data: The data to cache
    """
    path = _cache_path(artist_id, data_type)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "_fetched_at": datetime.now().isoformat(),
        "_data_type": data_type,
        "data": data,
    }
    path.write_text(json.dumps(payload, indent=2, default=str))
    return {"cached": True, "artist_id": artist_id, "data_type": data_type}


@mcp.tool()
def cache_clear(artist_id: int) -> dict:
    """Clear all cached data for an artist.

    Args:
        artist_id: Chartmetric artist ID
    """
    artist_dir = _cache_dir() / str(artist_id)
    if not artist_dir.exists():
        return {"cleared": False, "reason": "No cache found"}

    count = 0
    for f in artist_dir.glob("*.json"):
        f.unlink()
        count += 1
    if not any(artist_dir.iterdir()):
        artist_dir.rmdir()

    return {"cleared": True, "files_removed": count}


def sweep_old_cache(max_age_days: int = 3) -> dict:
    """Retire cache files older than ``max_age_days``, regardless of TTL.

    Wakes up on app launch (api/main.py startup) and prunes any cached
    response — metadata, tracks, dossier, neighbors, whatever — that was
    fetched more than ``max_age_days`` ago. Intentionally simpler than
    a per-class "2× TTL" sweeper: one rule, easy to reason about, keeps
    the on-disk footprint tightly bounded. The trade-off is that
    re-evaluating an artist last seen 4+ days ago re-hits Chartmetric
    for everything (~15 calls, ~15s at the 1.05 req/s ceiling).

    Uses file mtime as the freshness proxy — accurate enough, faster
    than parsing every JSON to read ``_fetched_at``. If a sweep empties
    an artist's directory, the dir is removed too. Failures on
    individual files are swallowed (best-effort cleanup; we don't want
    a permission-denied file to abort the whole pass).

    Returns ``{"files_removed": int, "dirs_removed": int}`` for logging.
    """
    cache_root = _cache_dir()
    if not cache_root.exists():
        return {"files_removed": 0, "dirs_removed": 0}

    cutoff = datetime.now() - timedelta(days=max_age_days)
    files_removed = 0
    dirs_removed = 0

    for artist_dir in cache_root.iterdir():
        if not artist_dir.is_dir():
            continue
        for f in artist_dir.glob("*.json"):
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                if mtime < cutoff:
                    f.unlink()
                    files_removed += 1
            except OSError:
                continue
        try:
            if not any(artist_dir.iterdir()):
                artist_dir.rmdir()
                dirs_removed += 1
        except OSError:
            pass

    return {"files_removed": files_removed, "dirs_removed": dirs_removed}
