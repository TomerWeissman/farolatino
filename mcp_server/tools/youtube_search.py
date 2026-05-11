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


@mcp.tool()
def get_youtube_latest_videos(uploads_playlist_id: str, limit: int = 3) -> dict:
    """Fetch the channel's latest N videos with view/like/comment counts.

    Two API calls: first ``GET /playlistItems`` to list the most recent
    video IDs from the channel's uploads playlist (the well-known ``UU…``
    playlist YouTube auto-maintains for every channel), then
    ``GET /videos?ids=...&part=snippet,statistics`` to pull titles +
    counts in one batch.

    Returns ``{"videos": [{"id", "title", "published_at", "view_count",
    "like_count", "comment_count", "like_ratio"}, ...]}`` — sorted newest
    first. ``like_ratio`` is ``like_count / view_count * 100``
    (sentiment proxy; typical music video range is 1-8%).

    Args:
        uploads_playlist_id: The channel's uploads playlist ID
            (from ``get_youtube_channel(...).uploads_playlist_id``).
        limit: Max videos to return (default 3, capped at 10).
    """
    limit = max(1, min(int(limit), 10))
    items_data = api_get("/playlistItems", params={
        "part": "snippet,contentDetails",
        "playlistId": uploads_playlist_id,
        "maxResults": limit,
    })
    items = items_data.get("items") or []
    video_ids = [
        (it.get("contentDetails") or {}).get("videoId")
        for it in items
        if (it.get("contentDetails") or {}).get("videoId")
    ]
    if not video_ids:
        return {"videos": []}

    videos_data = api_get("/videos", params={
        "part": "snippet,statistics",
        "id": ",".join(video_ids),
    })
    raw_videos = videos_data.get("items") or []

    by_id = {v.get("id"): v for v in raw_videos}
    out = [_format_video(vid, by_id[vid]) for vid in video_ids if vid in by_id]
    return {"videos": out}


@mcp.tool()
def get_youtube_top_videos(channel_id: str, limit: int = 3) -> dict:
    """Fetch a channel's top N videos by lifetime view count.

    Two API calls: first ``GET /search?channelId=...&order=viewCount&type=video``
    to list the highest-viewed videos (YouTube search costs ~100 quota units;
    /videos is 1 unit). Then ``GET /videos?ids=...&part=snippet,statistics``
    for full counts in one batch.

    Answers the A&R question "what's their biggest hit on YouTube right
    now" — distinct from the latest-uploads view, which can be skewed by
    a recent flop. Mirrors the latest-videos shape so the dashboard can
    render them with identical row styling.

    Args:
        channel_id: YouTube channel ID (starts with ``UC...``).
        limit: Max videos to return (default 3, capped at 10).
    """
    limit = max(1, min(int(limit), 10))
    search_data = api_get("/search", params={
        "part": "snippet",
        "channelId": channel_id,
        "order": "viewCount",
        "type": "video",
        "maxResults": limit,
    })
    items = search_data.get("items") or []
    video_ids = [
        (it.get("id") or {}).get("videoId")
        for it in items
        if (it.get("id") or {}).get("videoId")
    ]
    if not video_ids:
        return {"videos": []}

    videos_data = api_get("/videos", params={
        "part": "snippet,statistics",
        "id": ",".join(video_ids),
    })
    raw_videos = videos_data.get("items") or []

    by_id = {v.get("id"): v for v in raw_videos}
    # Preserve the search-order ranking (highest views first) rather than
    # the dict-iteration order of /videos's response.
    out = [_format_video(vid, by_id[vid]) for vid in video_ids if vid in by_id]
    return {"videos": out}


def _format_video(vid: str, v: dict) -> dict:
    """Normalize a YouTube /videos item into the shape both
    get_youtube_latest_videos + get_youtube_top_videos return.

    Returns the canonical 8-field shape including ``thumbnail_url``
    (medium-size thumbnail from the snippet) which the dashboard's
    TopVideos block renders next to the title.
    """
    snip = v.get("snippet") or {}
    stats = v.get("statistics") or {}
    view_count = _safe_int(stats.get("viewCount")) or 0
    like_count = _safe_int(stats.get("likeCount")) or 0
    like_ratio = (like_count / view_count * 100) if view_count > 0 else None
    thumbs = snip.get("thumbnails") or {}
    # Prefer medium (320×180); fall back gracefully.
    thumb_url = (
        (thumbs.get("medium") or {}).get("url")
        or (thumbs.get("default") or {}).get("url")
    )
    return {
        "id": vid,
        "title": snip.get("title"),
        "published_at": snip.get("publishedAt"),
        "view_count": view_count,
        "like_count": like_count,
        "comment_count": _safe_int(stats.get("commentCount")) or 0,
        "like_ratio": like_ratio,
        "thumbnail_url": thumb_url,
    }
