"""FaroLatino A&R Dashboard — Streamlit entry point.

Run with:
    source venv/bin/activate
    streamlit run streamlit_app/main.py

Three tabs:
  1. Evaluate — type an artist name, see a dossier
  2. Compare  — pick two artists, see them side-by-side
  3. Similar  — pick an artist, see comparable peers
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make sibling imports (mcp_server, etc.) work when running streamlit
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st  # noqa: E402

from streamlit_app.components import calibration_footer, page_header  # noqa: E402
from streamlit_app.views import compare, evaluate, similar  # noqa: E402


def main() -> None:
    st.set_page_config(
        page_title="FaroLatino A&R",
        page_icon="🎵",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    page_header()

    # Sidebar: profile selector + calibration footer
    with st.sidebar:
        st.markdown("### Scoring profile")
        profile = st.selectbox(
            "Profile",
            options=["default", "emerging_momentum", "revenue_focus", "latam_expansion"],
            index=0,
            label_visibility="collapsed",
        )
        st.session_state["scoring_profile"] = profile

        st.markdown("---")
        calibration_footer()

    # Tabs
    tab_eval, tab_cmp, tab_sim = st.tabs(["🔍 Evaluate", "⚖️  Compare", "🪞 Similar"])

    with tab_eval:
        evaluate.render()
    with tab_cmp:
        compare.render()
    with tab_sim:
        similar.render()


if __name__ == "__main__":
    main()
