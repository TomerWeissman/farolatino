"""Composite tool — full @evaluate pipeline in one MCP call.

Replaces the prior multi-call flow (search → get_artist_data → score → revenue
→ dossier → route_alert) where the model burned tokens reasoning between
each step. Now all six steps run server-side; the model makes ONE tool call
and presents the dossier.

Disambiguation: if `search_artists` returns multiple plausible matches (i.e.
the top hit's Spotify followers aren't dominant), the tool short-circuits
and returns `{"needs_disambiguation": [...]}` so the model can ask the user
to pick. The model then re-invokes with `cm_id=<chosen>`.
"""
from __future__ import annotations

from mcp_server.server import mcp
from mcp_server.tools.alert_router import route_alert
from mcp_server.tools.chartmetric_artist import get_artist_data
from mcp_server.tools.chartmetric_search import search_artist_by_url, search_artists
from mcp_server.tools.dossier_generator import generate_dossier
from mcp_server.tools.revenue_model import estimate_revenue
from mcp_server.tools.scoring.engine import compute_prospect_score

# A search result is "dominant" if the top match has >10× the Spotify
# follower count of the runner-up. Below this we ask the user to pick.
DOMINANCE_RATIO = 10


def _is_url(s: str) -> bool:
    return s.startswith(("http://", "https://"))


def _pick_unambiguous(search_result: dict) -> dict | None:
    """Return the single artist if the top hit dominates, else None."""
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


@mcp.tool()
def evaluate_artist(
    artist: str,
    profile_name: str = "default",
    cm_id: int | None = None,
) -> dict:
    """Full A&R evaluation for one artist — single-call pipeline.

    Args:
        artist: Artist name OR a Spotify/Chartmetric/social URL.
        profile_name: Scoring profile (default, emerging_momentum, revenue_focus,
                      latam_expansion).
        cm_id: Skip search if the caller already has the Chartmetric ID
               (e.g. after a disambiguation round-trip).

    Returns:
        On success: `{"dossier": ..., "alert": ..., "cm_id": ...}`
        On ambiguous search: `{"needs_disambiguation": [top 3 candidates]}`
        On error: `{"error": "..."}`
    """
    # Step 1: Resolve cm_id
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

    # Step 2: Pull all 14 endpoints (cache-aware)
    artist_data = get_artist_data(cm_id, use_cache=True)
    if "error" in artist_data:
        return {"error": f"get_artist_data failed: {artist_data.get('error')}"}

    # Step 3: Score across 7 dimensions
    score_result = compute_prospect_score(artist_data, profile_name)
    if "error" in score_result:
        return {"error": f"compute_prospect_score failed: {score_result.get('error')}"}

    # Step 4: Project revenue
    revenue_result = estimate_revenue(artist_data)
    # estimate_revenue may surface non-fatal warnings; only short-circuit on
    # a real error sentinel.
    if isinstance(revenue_result, dict) and revenue_result.get("error"):
        revenue_result = None  # let the dossier note "Revenue model not run"

    # Step 5: Build dossier
    dossier = generate_dossier(artist_data, score_result, revenue_result)

    # Step 6: Tier classification + signal alerts. route_alert expects
    # `prospect_score` to be a number (not the full score dict).
    alert = route_alert({
        "name": artist_data.get("name", "Unknown"),
        "cm_id": cm_id,
        "prospect_score": score_result.get("prospect_score", 0),
    })

    return {
        "dossier": dossier,
        "alert": alert,
        "cm_id": cm_id,
    }
