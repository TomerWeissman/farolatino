"""Composite tool — `@similar` pipeline in one MCP call.

Resolves an artist by name/URL/cm_id and returns the seed's profile plus
its neighboring artists (Chartmetric clustering + genre-search fallback,
already populated by get_artist_data).

Like evaluate_artist, this exists so the model makes ONE tool call — no
Read/Bash/Agent cascade to extract neighbors from a giant artist_data
blob.
"""
from __future__ import annotations

from mcp_server.server import mcp
from mcp_server.tools.chartmetric_artist import get_artist_data
from mcp_server.tools.chartmetric_search import search_artist_by_url, search_artists
from mcp_server.tools.similar_filter import filter_neighbors_by_country

# Mirrors composite_evaluate's resolution logic. Inlined (rather than
# imported) because both modules are loaded by server.py at startup;
# importing across them would set up a circular path through `mcp`.
DOMINANCE_RATIO = 10


def _is_url(s: str) -> bool:
    return s.startswith(("http://", "https://"))


def _pick_unambiguous(search_result: dict) -> dict | None:
    artists = search_result.get("artists") or []
    if not artists:
        return None
    if len(artists) == 1:
        return artists[0]
    top, runner = artists[0], artists[1]
    top_f = top.get("sp_followers") or 0
    run_f = runner.get("sp_followers") or 0
    if top_f and (run_f == 0 or top_f >= run_f * DOMINANCE_RATIO):
        return top
    return None


# Country-cluster filtering moved to mcp_server/tools/similar_filter.py
# in v0.5.3 so dossier_generator (Evaluate page) can apply the same
# filter without re-implementing the Latin-market cluster constants.


def _tier_band(seed_listeners: int, peer_listeners: int) -> str:
    """Classify a peer relative to the seed's monthly-listener tier."""
    if not seed_listeners or not peer_listeners:
        return "unknown"
    ratio = peer_listeners / seed_listeners
    if ratio >= 3:
        return "larger"
    if ratio <= 1 / 3:
        return "smaller"
    return "tier-similar"


@mcp.tool()
def find_similar_artists(
    artist: str,
    cm_id: int | None = None,
    limit: int = 10,
) -> dict:
    """Find artists comparable to the given seed by genre / career stage / scale.

    Args:
        artist: Seed artist name OR a Spotify/Chartmetric/social URL.
        cm_id: Skip search if the caller already has the seed's Chartmetric ID.
        limit: Max neighbors to return (default 10, capped at 20).

    Returns:
        On success: `{"seed": {...}, "neighbors": [...], "summary": "..."}`
        On ambiguous search: `{"needs_disambiguation": [top 3 candidates]}`
        On error: `{"error": "..."}`
    """
    # Step 1 — resolve cm_id (mirrors evaluate_artist's logic)
    # Models on OpenAI's Responses API tend to fill optional int|None
    # params with 0; treat falsy as missing since Chartmetric IDs are
    # always positive.
    if not cm_id:
        cm_id = None
    if cm_id is None:
        if _is_url(artist):
            res = search_artist_by_url(artist)
            if "error" in res or not res.get("cm_id"):
                return {"error": res.get("error", "URL did not resolve to an artist")}
            cm_id = res["cm_id"]
        else:
            search = search_artists(artist, limit=3)
            chosen = _pick_unambiguous(search)
            if chosen is None:
                return {
                    "needs_disambiguation": search.get("artists", [])[:3],
                    "query": artist,
                }
            cm_id = chosen["cm_id"]

    # Step 2 — pull artist data (cache-aware; neighbors come included)
    artist_data = get_artist_data(cm_id, use_cache=True)
    if "error" in artist_data:
        return {"error": f"get_artist_data failed: {artist_data.get('error')}"}

    seed_listeners = int(artist_data.get("sp_monthly_listeners") or 0)
    seed_country = artist_data.get("country_code")

    # Step 3 — country-cluster post-filter to drop cross-genre noise.
    # Chartmetric's neighbor clustering is by audience overlap, so global
    # Latin superstars appear next to global pop stars (Bad Bunny -> Justin
    # Bieber, Trueno -> Brent Rivera) — useless for Latin A&R. Filter to
    # countries in the same music-market cluster as the seed.
    # Also drop the seed itself: Chartmetric's neighbor list often
    # includes the artist as their own first "neighbor".
    # Fallback: if filtering leaves zero matches, keep the full unfiltered
    # list (better noisy results than empty results).
    raw_neighbors = [
        n for n in (artist_data.get("neighboring_artists") or [])
        if n.get("cm_id") != cm_id  # exclude self
    ]
    candidate_pool, country_filter_applied = filter_neighbors_by_country(
        seed_country, raw_neighbors
    )

    # Step 3b — annotate with tier band so the model can summarize
    neighbors = []
    for n in candidate_pool[: min(limit, 20)]:
        peer_listeners = int(n.get("sp_monthly_listeners") or 0)
        neighbors.append({
            **n,
            "tier_band": _tier_band(seed_listeners, peer_listeners),
        })

    # Step 4 — quick rollup the model can use without extra reasoning
    bands = {"tier-similar": 0, "smaller": 0, "larger": 0, "unknown": 0}
    for n in neighbors:
        bands[n["tier_band"]] = bands.get(n["tier_band"], 0) + 1

    return {
        "seed": {
            "name": artist_data.get("name"),
            "cm_id": cm_id,
            "country_code": seed_country,
            "career_stage": artist_data.get("career_stage"),
            "genres": artist_data.get("genres", []),
            "sp_monthly_listeners": seed_listeners,
        },
        "neighbors": neighbors,
        "tier_distribution": bands,
        "country_filter_applied": country_filter_applied,
        "summary": (
            f"{bands['tier-similar']} tier-similar, "
            f"{bands['smaller']} smaller, "
            f"{bands['larger']} larger "
            f"(out of {len(neighbors)} neighbors)"
        ),
    }
