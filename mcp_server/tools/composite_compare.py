"""Composite tool — head-to-head comparison of two artists.

Calls ``evaluate_artist`` for each side in series (the per-side
result is cached so a follow-up request that touches one of the
artists is near-instant). Returns both dossiers plus a small
``comparison`` block of headline diffs the chat can render as a
pill — see ``ComparePill`` on the frontend.

Disambiguation: if EITHER side's search returns a non-dominant top
hit, we surface that side's candidates back to the model so it can
ask the user to pick. The other side may still be resolved cleanly;
in that case we include the resolved cm_id under
``cm_id_a`` / ``cm_id_b`` so the model can re-call with the chosen
side fixed.
"""
from __future__ import annotations

import logging

from mcp_server.server import mcp

log = logging.getLogger(__name__)


def _headline_diffs(d_a: dict, d_b: dict) -> dict:
    """Pick the small set of fields the chat pill / page summary will
    surface. Intentionally narrow — the full dossiers stay in the
    return payload for downstream rendering."""
    score_a = (d_a.get("prospect_score") or {})
    score_b = (d_b.get("prospect_score") or {})
    id_a = (d_a.get("identity") or {})
    id_b = (d_b.get("identity") or {})
    return {
        "tier_a": score_a.get("tier"),
        "tier_b": score_b.get("tier"),
        "score_a": score_a.get("overall"),
        "score_b": score_b.get("overall"),
        "name_a": id_a.get("name"),
        "name_b": id_b.get("name"),
        "image_a": id_a.get("image"),
        "image_b": id_b.get("image"),
    }


@mcp.tool()
def compare_artists(
    artist_a: str,
    artist_b: str,
    profile_name: str = "default",
) -> dict:
    """Head-to-head A&R comparison of two artists — single-call pipeline.

    Runs ``evaluate_artist`` for each side. Each side uses the v0.5.2
    dossier-result cache (1h TTL per cm_id+profile), so a fresh
    compare after a recent single evaluate is fast.

    Args:
        artist_a: Name or URL for side A. Required.
        artist_b: Name or URL for side B. Required.
        profile_name: Scoring profile applied to BOTH sides (default,
            emerging_momentum, revenue_focus, latam_expansion).

    Returns:
        On both sides resolved: ``{"a": {...}, "b": {...},
        "comparison": {...}, "cm_id_a": ..., "cm_id_b": ...}``.
        On either side ambiguous: ``{"needs_disambiguation_a": [...],
        "query_a": ..., "b": {...}, "cm_id_b": ...}`` (or the mirror
        for side B). The model should ask the user which artist they
        meant, then re-call with the chosen side fixed via cm_id.
        On either side errored: ``{"error": "..."}``.
    """
    if not (artist_a or "").strip() or not (artist_b or "").strip():
        return {
            "error": (
                "compare_artists needs both artist_a and artist_b. "
                "Pass both as names or URLs."
            )
        }

    # Lazy import so this module can be imported during mcp_server.server
    # initialisation (composite_evaluate registers with `mcp` at import
    # time; importing it from module top here would deadlock the load).
    from mcp_server.tools.composite_evaluate import evaluate_artist

    out: dict = {}

    a_result = evaluate_artist(artist=artist_a, profile_name=profile_name)
    if "error" in a_result:
        return {"error": f"side A failed: {a_result['error']}"}
    if "needs_disambiguation" in a_result:
        out["needs_disambiguation_a"] = a_result["needs_disambiguation"]
        out["query_a"] = a_result.get("query", artist_a)

    b_result = evaluate_artist(artist=artist_b, profile_name=profile_name)
    if "error" in b_result:
        return {"error": f"side B failed: {b_result['error']}"}
    if "needs_disambiguation" in b_result:
        out["needs_disambiguation_b"] = b_result["needs_disambiguation"]
        out["query_b"] = b_result.get("query", artist_b)

    # Either side ambiguous? Return the partial result so the model
    # can ask the user to pick. The fully-resolved side is included
    # so the next call doesn't re-search it.
    if "needs_disambiguation_a" in out or "needs_disambiguation_b" in out:
        if "needs_disambiguation_a" not in out:
            out["a"] = a_result
            out["cm_id_a"] = a_result.get("cm_id")
        if "needs_disambiguation_b" not in out:
            out["b"] = b_result
            out["cm_id_b"] = b_result.get("cm_id")
        return out

    # Both sides resolved.
    out["a"] = a_result
    out["b"] = b_result
    out["cm_id_a"] = a_result.get("cm_id")
    out["cm_id_b"] = b_result.get("cm_id")
    out["comparison"] = _headline_diffs(
        a_result.get("dossier") or {},
        b_result.get("dossier") or {},
    )
    log.info(
        "compare_artists ok a=%r (cm_id=%s) b=%r (cm_id=%s)",
        artist_a, out["cm_id_a"], artist_b, out["cm_id_b"],
    )
    return out
