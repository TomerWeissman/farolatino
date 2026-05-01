"""Evaluate tab — type an artist name, see a full dossier."""
from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from mcp_server.tools.alert_router import route_alert
from mcp_server.tools.chartmetric_artist import get_artist_data
from mcp_server.tools.chartmetric_search import search_artists
from mcp_server.tools.dossier_generator import generate_dossier
from mcp_server.tools.dossier_renderer import _confidence_for, render_dossier
from mcp_server.tools.revenue_model import estimate_revenue
from mcp_server.tools.scoring.engine import compute_prospect_score
from streamlit_app.components import confidence_badge, tier_badge

# Same Insight-shape adapter as evaluate_artist.py
_WHITELIST = {"noteworthy_insights": {"text", "type", "date", "metric", "value"}}


def _adapt(p: dict) -> dict:
    a = dict(p)
    for k, allowed in _WHITELIST.items():
        items = a.get(k)
        if isinstance(items, list):
            a[k] = [
                {kk: vv for kk, vv in it.items() if kk in allowed}
                if isinstance(it, dict) else it
                for it in items
            ]
    return a


@st.cache_data(show_spinner=False, ttl=3600)
def _search(name: str) -> list[dict]:
    """Cached Chartmetric search."""
    if not name.strip():
        return []
    res = search_artists(name, limit=5)
    return res.get("artists", []) or []


@st.cache_data(show_spinner=False, ttl=3600)
def _evaluate(cm_id: int, profile_name: str) -> dict:
    """Cached full pipeline run for one artist."""
    profile = _adapt(get_artist_data(cm_id, use_cache=True))
    score = compute_prospect_score(profile, profile_name=profile_name)
    revenue = estimate_revenue(profile)
    dossier = generate_dossier(profile, score, revenue)
    alert_input = {
        "name": profile.get("name", "Unknown"),
        "prospect_score": score.get("prospect_score", 0),
        "shazam_count_diff_pct": profile.get("shazam_count_diff_pct"),
        "tiktok_followers_diff_pct": profile.get("tiktok_followers_diff_pct"),
        "sp_monthly_listeners_diff_pct": profile.get("sp_monthly_listeners_diff_pct"),
        "career_trend": profile.get("career_trend"),
    }
    alert = route_alert(alert_input)
    return {
        "profile": profile,
        "score": score,
        "revenue": revenue,
        "dossier": dossier,
        "alert": alert,
    }


def render() -> None:
    st.markdown("### Evaluate an artist")
    st.caption(
        "Search by name → pick from matches → see a full dossier with revenue projection, "
        "tier classification, and competitive context."
    )

    name = st.text_input("Artist name", placeholder="e.g. Feid, Hitomi Flor, Eugenia Quevedo")

    if not name.strip():
        return

    matches = _search(name)
    if not matches:
        st.warning(f"No Chartmetric match for {name!r}. Try a different spelling or a Spotify URL.")
        return

    if len(matches) == 1:
        chosen = matches[0]
    else:
        # Let the user pick from top results
        options = {
            f"{m.get('name')} — {m.get('code2', '?')} · "
            f"{(m.get('sp_monthly_listeners') or 0):,} monthly listeners "
            f"(cm_id {m.get('cm_id')})": m
            for m in matches
        }
        choice = st.radio(
            "Multiple matches — pick the right artist:",
            list(options.keys()),
            label_visibility="visible",
        )
        chosen = options[choice]

    cm_id = chosen.get("cm_id")
    if not cm_id:
        st.error("No cm_id in match.")
        return

    profile_name = st.session_state.get("scoring_profile", "default")

    with st.spinner(f"Pulling {chosen.get('name')} from Chartmetric (~{15 if not _is_cached(cm_id) else 1}s cold)..."):
        try:
            bundle = _evaluate(int(cm_id), profile_name)
        except Exception as exc:
            st.error(f"Pipeline failed: {exc}")
            with st.expander("Traceback"):
                import traceback
                st.code(traceback.format_exc())
            return

    profile = bundle["profile"]
    dossier = bundle["dossier"]

    # Header row: tier + confidence badges
    score_overall = (dossier.get("prospect_score") or {}).get("overall", 0)
    tier = (dossier.get("prospect_score") or {}).get("tier", "?")
    level, _, _, _ = _confidence_for(profile)

    col_t, col_c, col_score = st.columns([1, 1, 2])
    with col_t:
        tier_badge(tier)
    with col_c:
        confidence_badge(level)
    with col_score:
        st.metric(label="Prospect score", value=f"{score_overall}/100")

    st.divider()

    # Render the Markdown dossier
    md = render_dossier(dossier, profile)
    st.markdown(md)

    # Raw JSON for power users
    with st.expander("Show raw dossier JSON"):
        st.json(bundle["dossier"], expanded=False)
    with st.expander("Show alert routing"):
        st.json(bundle["alert"], expanded=False)


def _is_cached(cm_id: int) -> bool:
    """Quick heuristic: do we have a cached metadata.json for this artist?"""
    p = Path(__file__).resolve().parent.parent.parent / "data" / "cache" / str(cm_id) / "metadata.json"
    return p.exists()
