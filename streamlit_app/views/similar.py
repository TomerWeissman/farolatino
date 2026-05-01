"""Similar tab — pick an artist, see comparable peers."""
from __future__ import annotations

import streamlit as st

from streamlit_app.views.evaluate import _evaluate, _search


def render() -> None:
    st.markdown("### Find similar artists")
    st.caption(
        "Returns 5-15 artists Chartmetric considers similar (clustering + a "
        "genre-search fallback). Useful for mapping a prospect's competitive landscape."
    )

    name = st.text_input("Seed artist", placeholder="e.g. Hitomi Flor")
    if not name.strip():
        return

    matches = _search(name)
    if not matches:
        st.warning(f"No match for {name!r}.")
        return
    chosen = matches[0]

    profile_name = st.session_state.get("scoring_profile", "default")
    with st.spinner(f"Pulling {chosen.get('name')} and similar artists..."):
        bundle = _evaluate(int(chosen["cm_id"]), profile_name)

    profile = bundle["profile"]
    similar = profile.get("neighboring_artists") or []

    if not similar:
        st.warning(
            "No comparable artists surfaced. Chartmetric's clustering came back empty "
            "and the genre-search fallback found no candidates in the same listener band. "
            "Try a different seed."
        )
        return

    st.markdown(f"#### Similar to **{chosen.get('name')}** — {len(similar)} candidates")

    rows = []
    for s in similar[:15]:
        rows.append({
            "Artist": s.get("name", "—"),
            "Country": s.get("country_code") or "—",
            "Monthly listeners": _fmt_int(s.get("sp_monthly_listeners")),
            "Spotify followers": _fmt_int(s.get("sp_followers")),
            "Stage": s.get("career_stage") or "—",
            "Source": s.get("_similarity_source") or s.get("source", "—"),
            "cm_id": s.get("cm_id"),
        })

    st.dataframe(
        rows,
        hide_index=True,
        use_container_width=True,
        column_config={
            "cm_id": st.column_config.NumberColumn(format="%d"),
            "Monthly listeners": st.column_config.TextColumn(width="medium"),
        },
    )

    st.caption(
        "Want to drill into one of these? Copy their name to the **Evaluate** tab "
        "for a full dossier with revenue projection."
    )


def _fmt_int(v) -> str:
    if v is None or v == 0:
        return "—"
    try:
        return f"{int(v):,}"
    except (TypeError, ValueError):
        return str(v)
