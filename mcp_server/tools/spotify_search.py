"""Spotify Web API search & artist tools.

Cross-validation layer for the Chartmetric data pipeline: when the model
needs fresher numbers than Chartmetric's daily snapshot (Spotify updates
follower counts in near-realtime), or genres / popularity in Spotify's
own taxonomy, these tools fill the gap.

Two MCP tools:
- search_spotify_artist(name) → top matches with Spotify ID + followers + popularity
- get_spotify_artist(spotify_id) → details for one artist (genres, followers, popularity, images)
"""
from __future__ import annotations

from mcp_server.server import mcp
from mcp_server.tools.spotify_auth import api_get


@mcp.tool()
def search_spotify_artist(query: str, limit: int = 5) -> dict:
    """Search Spotify for an artist by name. Returns top matches.

    Use this when you need a fresh Spotify ID, current follower count,
    or Spotify's own genre taxonomy for an artist (which differs from
    Chartmetric's). For most A&R queries Chartmetric is the right
    primary source — this is for cross-validation.

    Args:
        query: Artist name to search for.
        limit: Max number of results (default 5, capped at 10).
    """
    limit = max(1, min(int(limit), 10))
    data = api_get("/search", params={"q": query, "type": "artist", "limit": limit})
    artists = (data.get("artists") or {}).get("items") or []
    return {
        "query": query,
        "count": len(artists),
        "artists": [_format_artist(a) for a in artists],
    }


@mcp.tool()
def get_spotify_artist(spotify_id: str) -> dict:
    """Get full details for one Spotify artist (genres, followers, popularity).

    Args:
        spotify_id: Spotify's artist ID (e.g. '4q3ewBCX7sLwd24euuV69X' for Bad Bunny).
    """
    data = api_get(f"/artists/{spotify_id}")
    return _format_artist(data)


def _format_artist(a: dict) -> dict:
    images = a.get("images") or []
    return {
        "spotify_id": a.get("id"),
        "name": a.get("name"),
        "genres": a.get("genres") or [],
        "popularity": a.get("popularity"),  # 0-100, Spotify's own metric
        "followers": (a.get("followers") or {}).get("total"),
        "image_url": images[0].get("url") if images else None,
        "external_url": (a.get("external_urls") or {}).get("spotify"),
    }
