"""FaroLatino A&R Dashboard — Streamlit entry point.

Run with:
    source venv/bin/activate
    streamlit run streamlit_app/main.py

Single chat page with a Claude-like minimal layout. Skills accessible
via @ autocomplete in the input box. Sidebar is intentionally quiet —
connection status only, plus a collapsible diagnostic panel for runs.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402

# Load .env BEFORE any module that reads env vars at import time.
load_dotenv(PROJECT_ROOT / ".env")

import streamlit as st  # noqa: E402

from streamlit_app.components import (  # noqa: E402
    connection_status_badge,
    recent_runs_sidebar,
)
from streamlit_app.views import chat  # noqa: E402


# Keep CSS in a constant so it's easy to tweak later
_CUSTOM_CSS = """
<style>
/* Hide Streamlit default chrome */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header[data-testid="stHeader"] {background: transparent;}

/* Center main chat column with breathing room — Claude-style */
.main .block-container {
    max-width: 760px;
    padding-top: 2rem;
    padding-bottom: 6rem;
}

/* Quiet typography */
html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    color: #1a1a1a;
}

h1, h2, h3, h4, h5, h6 {
    font-weight: 500;
    color: #1a1a1a;
    letter-spacing: -0.01em;
}

/* Chat bubbles — neutral greys */
[data-testid="stChatMessage"] {
    background: transparent;
    border: none;
    padding: 0.75rem 0;
}

[data-testid="stChatMessage"] .stMarkdown {
    line-height: 1.6;
}

/* Subtle divider between turns */
[data-testid="stChatMessage"] + [data-testid="stChatMessage"] {
    border-top: 1px solid #ececec;
}

/* User vs assistant avatar tint */
[data-testid="stChatMessageAvatarUser"] {
    background: #525252 !important;
}
[data-testid="stChatMessageAvatarAssistant"] {
    background: #a3a3a3 !important;
}

/* Sidebar — quieter */
section[data-testid="stSidebar"] {
    background: #fafafa;
    border-right: 1px solid #ececec;
}
section[data-testid="stSidebar"] .stMarkdown h3 {
    font-size: 0.85rem;
    color: #737373;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    font-weight: 600;
    margin-top: 1rem;
}
section[data-testid="stSidebar"] .stMarkdown p,
section[data-testid="stSidebar"] .stCaption {
    font-size: 0.8rem;
    color: #525252;
}

/* Soften default Streamlit buttons (just nicer chrome) */
.stButton > button {
    border-radius: 8px;
    border: 1px solid #d4d4d4;
    background: #ffffff;
    color: #262626;
    font-weight: 400;
    transition: border-color 0.15s, background 0.15s;
}
.stButton > button:hover {
    border-color: #737373;
    background: #fafafa;
}

/* Code/metrics — subtle */
code {
    background: #f5f5f5;
    color: #262626;
    padding: 1px 5px;
    border-radius: 4px;
    font-size: 0.88em;
}
</style>
"""


def main() -> None:
    st.set_page_config(
        page_title="FaroLatino",
        page_icon="•",
        layout="centered",
        initial_sidebar_state="collapsed",
    )

    st.markdown(_CUSTOM_CSS, unsafe_allow_html=True)

    # Minimal header
    st.markdown(
        "<div style='color:#737373;font-size:0.85rem;letter-spacing:0.04em;"
        "text-transform:uppercase;font-weight:600;margin-bottom:0.5rem;'>"
        "FaroLatino · A&R</div>",
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.markdown("### Connection")
        connection_status_badge()
        st.markdown("---")
        recent_runs_sidebar()

    chat.render()


if __name__ == "__main__":
    main()
