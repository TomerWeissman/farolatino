"""POST /api/evaluate — run the @evaluate skill, return full dossier JSON.

Companion to the chat-side ``@evaluate`` flow but returns structured
data instead of Markdown so the dashboard at ``/evaluate`` can drive
its own visuals (cards, bars, country flags, etc.). The
``rendered_markdown`` field carries the same canonical Markdown the
chat would produce — used to seed a follow-up conversation when the
user clicks "Continue in chat" on the dashboard.

The actual evaluation logic is identical to the chat path: both reach
the same ``mcp__farolatino__evaluate_artist`` tool via
``core.llm.tool_dispatch.dispatch``. Same scoring, same revenue
projection, same Chartmetric calls, same cache hits.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.llm.tool_dispatch import dispatch as dispatch_tool

router = APIRouter()
log = logging.getLogger(__name__)


class EvaluateRequest(BaseModel):
    artist: str
    # Optional disambiguation pick — when the first pass returned
    # ``needs_disambiguation``, the frontend re-calls with the chosen
    # cm_id to skip the search step. 0 / None / missing all mean "no
    # specific id, do a fresh search".
    cm_id: int | None = None


@router.post("/evaluate")
def post_evaluate(req: EvaluateRequest) -> dict:
    """Run @evaluate, return JSON for the dashboard.

    Three response shapes:
      - ``{"dossier": ..., "alert": ..., "cm_id": ..., "rendered_markdown": ...}``
        on success
      - ``{"needs_disambiguation": [...candidates...], "query": ...}``
        when the artist name matches multiple candidates
      - ``{"error": "..."}`` on tool error

    All three return HTTP 200; the frontend distinguishes by which
    keys are present. Saves a round-trip vs. status-code branching.
    """
    artist = (req.artist or "").strip()
    if not artist:
        raise HTTPException(status_code=400, detail="artist is required")

    args: dict = {"artist": artist, "profile_name": "default"}
    if req.cm_id:
        # Mirrors composite_evaluate's "treat 0 / None as missing" guard
        # added in the May-6 cm_id=0 fix. The dispatcher already trims
        # falsy values for this tool, but explicit is safer.
        args["cm_id"] = req.cm_id

    result = dispatch_tool("mcp__farolatino__evaluate_artist", args)

    if "error" in result:
        return {"error": result["error"]}
    if "needs_disambiguation" in result:
        return {
            "needs_disambiguation": result["needs_disambiguation"],
            "query": result.get("query") or artist,
        }

    # Happy path — generate the canonical Markdown alongside the JSON
    # so "Continue in chat" can seed a conversation without a second
    # round-trip.
    rendered_markdown = ""
    cm_id = result.get("cm_id")
    if cm_id:
        try:
            artist_data = dispatch_tool(
                "mcp__farolatino__get_artist_data",
                {"cm_artist_id": cm_id, "use_cache": True},
            )
        except Exception:
            log.exception("get_artist_data failed during /api/evaluate render")
            artist_data = {}
        try:
            from mcp_server.tools.dossier_renderer import render_dossier
            rendered_markdown = render_dossier(result["dossier"], artist_data or {})
        except Exception:
            log.exception("render_dossier failed during /api/evaluate")
            rendered_markdown = ""

    return {
        "dossier": result["dossier"],
        "alert": result.get("alert"),
        "cm_id": cm_id,
        "rendered_markdown": rendered_markdown,
    }
