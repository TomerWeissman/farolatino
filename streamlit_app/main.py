"""FaroLatino A&R Dashboard — Streamlit entry point.

Run with:
    source venv/bin/activate
    streamlit run streamlit_app/main.py

Single chat page, v0.dev-style minimal: pure white, narrow centered
column, sidebar hidden by default. Append `?debug=1` to the URL to
reveal the connection status + recent runs panel for diagnostics.
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


# v0.dev-style: pure white, single narrow column, almost no chrome.
_CUSTOM_CSS = """
<style>
/* Remove Streamlit chrome */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header[data-testid="stHeader"] {display: none;}
[data-testid="stToolbar"] {display: none;}

/* Pure white canvas */
html, body, .stApp, [data-testid="stAppViewContainer"], .main {
    background: #ffffff !important;
}

/* Narrow centered column with breathing room */
.main .block-container {
    max-width: 640px;
    padding: 4rem 1.5rem 8rem 1.5rem;
}

/* Typography — Inter / system stack, tight */
html, body, [class*="css"] {
    font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    color: #0a0a0a;
    -webkit-font-smoothing: antialiased;
}
html, body {
    letter-spacing: -0.01em;
}

/* Wordmark in the top-left corner only */
.wordmark {
    position: fixed;
    top: 1rem;
    left: 1.25rem;
    font-size: 12px;
    color: #737373;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    font-weight: 500;
    z-index: 100;
    user-select: none;
}

/* Empty state — vertically centered greeting */
.empty-state {
    text-align: center;
    padding: 3.5rem 0 1.5rem;
}
.empty-greet {
    font-size: 1.6rem;
    font-weight: 500;
    color: #0a0a0a;
    letter-spacing: -0.02em;
}
.empty-hint {
    color: #737373;
    font-size: 0.9rem;
    margin-top: 0.4rem;
}

/* Skill cheatsheet — quiet pills with native tooltips */
.skills-row {
    text-align: center;
    margin: 1.25rem 0 0;
    color: #a3a3a3;
    font-size: 0.85rem;
    line-height: 1.9;
}
.skill-pill {
    color: #525252;
    font-weight: 500;
    cursor: help;
    border-bottom: 1px dotted #d4d4d4;
}

/* Chat messages — assistant flush prose, user gets a tiny grey bubble */
[data-testid="stChatMessage"] {
    background: transparent;
    border: none;
    padding: 0.6rem 0;
    gap: 0.75rem;
}
[data-testid="stChatMessage"] .stMarkdown {
    line-height: 1.65;
}
/* User bubble */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) .stMarkdown > div {
    background: #f4f4f4;
    border-radius: 14px;
    padding: 10px 14px;
}
/* Hide both avatars for cleaner look — message direction implied by alignment */
[data-testid="stChatMessageAvatarUser"],
[data-testid="stChatMessageAvatarAssistant"] {
    display: none;
}
/* Right-align user content */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
    flex-direction: row-reverse;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) > div:last-child {
    max-width: 80%;
}

/* Chat input — refined, focus ring */
[data-testid="stChatInput"] textarea {
    border: 1px solid #e5e5e5 !important;
    border-radius: 14px !important;
    background: #ffffff !important;
    color: #0a0a0a !important;
    font-size: 15px !important;
    padding: 12px 16px !important;
    transition: border-color 0.15s, box-shadow 0.15s;
}
[data-testid="stChatInput"] textarea:focus {
    border-color: #0a0a0a !important;
    box-shadow: 0 0 0 2px rgba(0,0,0,0.06) !important;
}
[data-testid="stChatInput"] textarea::placeholder {
    color: #a3a3a3 !important;
}

/* Sidebar (only visible in ?debug=1 mode) — quiet */
section[data-testid="stSidebar"] {
    background: #fafafa !important;
    border-right: 1px solid #ececec;
}
section[data-testid="stSidebar"] .stMarkdown h3 {
    font-size: 0.78rem;
    color: #737373;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-weight: 600;
    margin-top: 1rem;
}

/* Soften misc Streamlit elements */
code {
    background: #f4f4f4;
    color: #262626;
    padding: 1px 5px;
    border-radius: 4px;
    font-size: 0.88em;
}
hr {
    border-color: #ececec !important;
}
</style>
"""


def _is_debug_mode() -> bool:
    """`?debug=1` in the URL toggles the diagnostic sidebar."""
    qp = st.query_params
    return qp.get("debug") in ("1", "true", "yes")


def main() -> None:
    debug = _is_debug_mode()
    st.set_page_config(
        page_title="FaroLatino",
        page_icon="•",
        layout="centered",
        # Sidebar collapsed in normal mode, expanded only in debug
        initial_sidebar_state="expanded" if debug else "collapsed",
    )

    st.markdown(_CUSTOM_CSS, unsafe_allow_html=True)
    st.markdown("<div class='wordmark'>FaroLatino</div>", unsafe_allow_html=True)

    # Sidebar populated only in debug mode (otherwise it's collapsed AND empty)
    if debug:
        with st.sidebar:
            st.markdown("### Connection")
            connection_status_badge()
            st.markdown("---")
            recent_runs_sidebar()

    chat.render()


if __name__ == "__main__":
    main()
