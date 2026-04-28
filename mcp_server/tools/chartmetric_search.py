"""Chartmetric search — find artists by name or URL.

Used for Mode 2 (on-demand evaluation): the A&R team member
types an artist name, this tool resolves it to a Chartmetric ID.
"""

from mcp_server.server import mcp
from mcp_server.tools.chartmetric_auth import api_get


@mcp.tool()
def search_artists(query: str, limit: int = 10) -> dict:
    """Search Chartmetric for artists by name.

    Returns a list of matching artists with their Chartmetric IDs,
    Spotify followers, monthly listeners, and country — enough info
    for the user to pick the right one if there are multiple matches.

    Args:
        query: Artist name to search for (e.g., "Bad Bunny")
        limit: Max number of results (default 10)
    """
    data = api_get("/api/search", params={"q": query, "type": "artists", "limit": limit})

    artists = data.get("obj", {}).get("artists", [])

    results = []
    for artist in artists[:limit]:
        results.append({
            "cm_id": artist.get("id"),
            "name": artist.get("name"),
            "code2": artist.get("code2"),
            "sp_followers": artist.get("sp_followers"),
            "sp_monthly_listeners": artist.get("sp_monthly_listeners"),
            "image_url": artist.get("image_url"),
            "genres": artist.get("genres"),
            "record_label": artist.get("record_label"),
            "signed": artist.get("signed"),
        })

    return {
        "query": query,
        "count": len(results),
        "artists": results,
    }


@mcp.tool()
def search_artist_by_url(url: str) -> dict:
    """Resolve an artist from a Spotify, YouTube, Instagram, or TikTok URL.

    Useful when someone shares a link instead of a name.

    Args:
        url: A social/streaming platform URL for the artist
    """
    data = api_get("/api/search/social", params={"url": url})
    obj = data.get("obj", {})

    if not obj:
        return {"error": f"No artist found for URL: {url}"}

    return {
        "cm_id": obj.get("id"),
        "name": obj.get("name"),
        "code2": obj.get("code2"),
        "platform": obj.get("platform"),
        "url": url,
    }
