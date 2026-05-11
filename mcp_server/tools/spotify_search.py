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


@mcp.tool()
def get_spotify_artist_top_tracks(
    spotify_id: str,
    market: str = "US",
    limit: int = 5,
) -> dict:
    """Get the artist's top tracks (per-track popularity + release date).

    Calls ``GET /v1/artists/{id}/top-tracks``. Spotify's "popularity"
    is a per-track 0-100 score that decays if a track stops being
    streamed, so it's a real "is this artist hot right now" signal —
    unlike the artist-level popularity which is much slower-moving.

    Args:
        spotify_id: Spotify artist ID.
        market: ISO 3166-1 alpha-2 country code (default ``"US"``).
                Spotify requires a market for /top-tracks.
        limit: Max tracks to return (capped at 10, Spotify's hard limit).
    """
    limit = max(1, min(int(limit), 10))
    data = api_get(f"/artists/{spotify_id}/top-tracks", params={"market": market})
    tracks_in = data.get("tracks") or []
    tracks_out = []
    for t in tracks_in[:limit]:
        album = t.get("album") or {}
        tracks_out.append({
            "id": t.get("id"),
            "name": t.get("name"),
            "popularity": t.get("popularity"),
            "release_date": album.get("release_date"),
            "duration_ms": t.get("duration_ms"),
        })
    return {"tracks": tracks_out}


@mcp.tool()
def get_spotify_audio_features(track_ids: list[str]) -> dict:
    """Fetch audio features (danceability, energy, tempo, …) for tracks.

    Calls ``GET /v1/audio-features?ids=...`` (batched up to 100 IDs per
    Spotify's hard limit). Aggregates the per-track values into an
    ``average`` block so the dossier can render a single "Sound profile"
    line without exposing per-track noise.

    Args:
        track_ids: Up to 100 Spotify track IDs.
    """
    if not track_ids:
        return {"audio_features": [], "average": {}}

    ids = [t for t in track_ids if t][:100]
    data = api_get("/audio-features", params={"ids": ",".join(ids)})
    features_in = data.get("audio_features") or []

    features_out: list[dict] = []
    for f in features_in:
        if not isinstance(f, dict):
            continue
        features_out.append({
            "id": f.get("id"),
            "danceability": f.get("danceability"),
            "energy": f.get("energy"),
            "tempo": f.get("tempo"),
        })

    average = _avg_features(features_out)
    return {"audio_features": features_out, "average": average}


def _avg_features(features: list[dict]) -> dict:
    """Mean of danceability/energy/tempo across a list of audio-feature dicts.

    Skips entries whose value is missing for the given metric — so the
    sample size differs per metric in the rare case Spotify returns a
    partial response.
    """
    if not features:
        return {}
    keys = ("danceability", "energy", "tempo")
    out: dict = {}
    counts = 0
    for k in keys:
        vals = [f.get(k) for f in features if isinstance(f.get(k), (int, float))]
        if vals:
            out[k] = sum(vals) / len(vals)
            counts = max(counts, len(vals))
    out["sample_size"] = counts
    return out
