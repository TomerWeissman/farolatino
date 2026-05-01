"""Data cache — JSON file cache for artist data, keyed by artist ID + data type."""

import json
from datetime import datetime, timedelta
from pathlib import Path

from mcp_server.server import mcp

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "cache"

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
}


def _cache_path(artist_id: int, data_type: str) -> Path:
    return CACHE_DIR / str(artist_id) / f"{data_type}.json"


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
    artist_dir = CACHE_DIR / str(artist_id)
    if not artist_dir.exists():
        return {"cleared": False, "reason": "No cache found"}

    count = 0
    for f in artist_dir.glob("*.json"):
        f.unlink()
        count += 1
    if not any(artist_dir.iterdir()):
        artist_dir.rmdir()

    return {"cleared": True, "files_removed": count}
