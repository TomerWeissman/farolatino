"""Compare tab — pick two artists, see them side-by-side."""
from __future__ import annotations

import streamlit as st

from streamlit_app.components import confidence_badge, tier_badge
from streamlit_app.views.evaluate import _evaluate, _search
from mcp_server.tools.dossier_renderer import _confidence_for, render_dossier


def _resolve(name: str, key: str) -> dict | None:
    if not name.strip():
        return None
    matches = _search(name)
    if not matches:
        st.warning(f"No match for {name!r}.")
        return None
    if len(matches) == 1:
        return matches[0]
    options = {
        f"{m.get('name')} — {(m.get('sp_monthly_listeners') or 0):,} listeners (cm_id {m.get('cm_id')})": m
        for m in matches[:3]
    }
    choice = st.radio(
        f"Multiple matches for {key}:", list(options.keys()), key=f"radio_{key}"
    )
    return options[choice]


def render() -> None:
    st.markdown("### Compare two artists")
    st.caption("Useful for ranking similar prospects against each other or sanity-checking a projection against a known reference.")

    col_a, col_b = st.columns(2)
    with col_a:
        name_a = st.text_input("Artist A", placeholder="e.g. Feid", key="compare_a")
    with col_b:
        name_b = st.text_input("Artist B", placeholder="e.g. Ryan Castro", key="compare_b")

    if not (name_a.strip() and name_b.strip()):
        return

    chosen_a = _resolve(name_a, "A")
    chosen_b = _resolve(name_b, "B")
    if not (chosen_a and chosen_b):
        return

    profile_name = st.session_state.get("scoring_profile", "default")

    with st.spinner("Pulling both artists..."):
        try:
            bundle_a = _evaluate(int(chosen_a["cm_id"]), profile_name)
            bundle_b = _evaluate(int(chosen_b["cm_id"]), profile_name)
        except Exception as exc:
            st.error(f"Pipeline failed: {exc}")
            return

    col_a, col_b = st.columns(2)
    for col, bundle, chosen in ((col_a, bundle_a, chosen_a), (col_b, bundle_b, chosen_b)):
        with col:
            profile = bundle["profile"]
            dossier = bundle["dossier"]
            score = (dossier.get("prospect_score") or {})
            tier = score.get("tier", "?")
            score_val = score.get("overall", 0)
            level, _, _, _ = _confidence_for(profile)
            revenue = (dossier.get("revenue_projection") or {})
            bruto = revenue.get("annual_projected", 0)

            st.markdown(f"#### {chosen.get('name')}")
            row1, row2 = st.columns(2)
            with row1:
                tier_badge(tier)
            with row2:
                confidence_badge(level)
            st.metric("Score", f"{score_val}/100")
            st.metric("Annual gross (BRUTO)", _money(bruto))
            st.metric("Distributor cut (~26%)", _money(bruto * 0.26))

            with st.expander("Full dossier"):
                st.markdown(render_dossier(dossier, profile))


def _money(v: float) -> str:
    if v >= 1_000_000:
        return f"${v/1_000_000:.2f}M"
    if v >= 1_000:
        return f"${v/1_000:.0f}K"
    return f"${v:,.0f}"
