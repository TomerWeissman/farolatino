"""FaroLatino A&R Dashboard — Streamlit entry point.

Run with:
    source venv/bin/activate
    streamlit run streamlit_app/main.py

Single chat page that delegates skill execution to Claude Code via a
subprocess wrapper. Use the sidebar to browse skills and stage their
slugs into the chat input.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make sibling imports (mcp_server, etc.) work when running streamlit
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402

# Load .env BEFORE any module that reads env vars at import time
# (chartmetric_auth, the connection-status badge, etc.).
load_dotenv(PROJECT_ROOT / ".env")

import streamlit as st  # noqa: E402

from streamlit_app.components import (  # noqa: E402
    calibration_footer,
    connection_status_badge,
    page_header,
    skill_picker_sidebar,
)
from streamlit_app.views import chat  # noqa: E402


def main() -> None:
    st.set_page_config(
        page_title="FaroLatino A&R",
        page_icon="🎵",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    page_header()

    with st.sidebar:
        st.markdown("### Connection")
        connection_status_badge()

        st.markdown("---")
        st.markdown("### Scoring profile")
        profile = st.selectbox(
            "Profile",
            options=["default", "emerging_momentum", "revenue_focus", "latam_expansion"],
            index=0,
            label_visibility="collapsed",
        )
        st.session_state["scoring_profile"] = profile

        st.markdown("---")
        skill_picker_sidebar()

        st.markdown("---")
        calibration_footer()

    chat.render()


if __name__ == "__main__":
    main()
