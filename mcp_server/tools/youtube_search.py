"""YouTube Data API v3 — channel search & details tools.

Two MCP tools:
- search_youtube_channel(name) → top matching channels
- get_youtube_channel(channel_id) → subscribers, view count, recent uploads

YouTube view counts and subscriber counts update in near-realtime
(unlike Chartmetric's daily snapshot), so these are useful for
last-mile validation when the model needs the freshest numbers.
"""
from __future__ import annotations

from mcp_server.server import mcp
from mcp_server.tools.youtube_auth import api_get


@mcp.tool()
def search_youtube_channel(query: str, limit: int = 5) -> dict:
    """Search YouTube for a channel by name. Returns top matches.

    Args:
        query: Channel/artist name to search for.
        limit: Max number of results (default 5, capped at 10).
    """
    limit = max(1, min(int(limit), 10))
    data = api_get("/search", params={
        "part": "snippet",
        "q": query,
        "type": "channel",
        "maxResults": limit,
    })
    items = data.get("items") or []
    channels = []
    for item in items:
        snip = item.get("snippet") or {}
        channels.append({
            "channel_id": (item.get("id") or {}).get("channelId"),
            "title": snip.get("channelTitle") or snip.get("title"),
            "description": snip.get("description"),
            "image_url": ((snip.get("thumbnails") or {}).get("default") or {}).get("url"),
            "published_at": snip.get("publishedAt"),
        })
    return {"query": query, "count": len(channels), "channels": channels}


@mcp.tool()
def get_youtube_channel(channel_id: str) -> dict:
    """Get subscriber count + total views + video count for a YouTube channel.

    Args:
        channel_id: YouTube channel ID (starts with 'UC...').
    """
    data = api_get("/channels", params={
        "part": "snippet,statistics,contentDetails",
        "id": channel_id,
    })
    items = data.get("items") or []
    if not items:
        return {"error": f"Channel {channel_id} not found"}
    item = items[0]
    snip = item.get("snippet") or {}
    stats = item.get("statistics") or {}
    return {
        "channel_id": channel_id,
        "title": snip.get("title"),
        "description": snip.get("description"),
        "country": snip.get("country"),
        "image_url": ((snip.get("thumbnails") or {}).get("default") or {}).get("url"),
        "subscribers": _safe_int(stats.get("subscriberCount")),
        "view_count": _safe_int(stats.get("viewCount")),
        "video_count": _safe_int(stats.get("videoCount")),
        "uploads_playlist_id": (
            (item.get("contentDetails") or {}).get("relatedPlaylists") or {}
        ).get("uploads"),
    }


def _safe_int(v) -> int | None:
    try:
        return int(v) if v is not None else None
    except (ValueError, TypeError):
        return None
