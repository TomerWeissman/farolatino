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
# IMPORTANT: every text-color rule has !important so Streamlit's
# OS-derived dark theme (when the user's system is in dark mode and
# the .streamlit/config.toml didn't ship in the snapshot) doesn't
# leak white text onto white backgrounds.
_CUSTOM_CSS = """
<style>
/* Force light theme regardless of OS preference */
:root { color-scheme: light !important; }

/* Remove Streamlit chrome */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header[data-testid="stHeader"] {display: none;}
[data-testid="stToolbar"] {display: none;}

/* Pure white canvas — every Streamlit container layer */
html, body,
.stApp,
[data-testid="stAppViewContainer"],
.main,
[data-testid="stMain"],
[data-testid="block-container"] {
    background: #ffffff !important;
    color: #0a0a0a !important;
}

/* Narrow centered column with breathing room */
.main .block-container {
    max-width: 640px;
    padding: 4rem 1.5rem 8rem 1.5rem;
}

/* Typography — Inter / system stack, tight, pinned dark */
html, body, [class*="css"], .stMarkdown, p, li, span, div {
    font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    color: #0a0a0a !important;
    -webkit-font-smoothing: antialiased;
}
html, body {
    letter-spacing: -0.01em;
}

/* Heading colors */
h1, h2, h3, h4, h5, h6 {
    color: #0a0a0a !important;
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
    background: transparent !important;
    border: none !important;
    padding: 0.6rem 0;
    gap: 0.75rem;
}
[data-testid="stChatMessage"] .stMarkdown,
[data-testid="stChatMessage"] .stMarkdown p {
    color: #0a0a0a !important;
    line-height: 1.65;
}

/* Hide avatars for cleaner look (we use alignment instead) */
[data-testid="stChatMessageAvatarUser"],
[data-testid="stChatMessageAvatarAssistant"] {
    display: none !important;
}

/* User message — flex right + tinted bubble.
   We can't use :has() reliably here because Streamlit's chat container
   doesn't bind a stable role attribute. Instead the chat view tags each
   user message with class chat-user-bubble via raw markdown. */
.chat-user-bubble {
    display: inline-block;
    background: #f4f4f4 !important;
    border-radius: 14px;
    padding: 10px 14px;
    max-width: 80%;
    color: #0a0a0a !important;
    margin-left: auto;
}
.chat-user-row {
    display: flex;
    justify-content: flex-end;
    margin: 0.6rem 0;
}

/* Status / "thinking" indicator */
.chat-status {
    color: #737373 !important;
    font-size: 14px;
    font-style: italic;
    padding: 0.5rem 0;
    display: flex;
    align-items: center;
    gap: 8px;
}
.chat-status .dot {
    width: 6px; height: 6px;
    border-radius: 50%;
    background: #737373;
    animation: pulse 1.2s ease-in-out infinite;
}
@keyframes pulse {
    0%, 100% { opacity: 0.3; transform: scale(1); }
    50%      { opacity: 1.0; transform: scale(1.3); }
}
.tool-use-line {
    color: #737373 !important;
    font-size: 13px;
    padding: 4px 0;
    border-left: 2px solid #ececec;
    padding-left: 10px;
    margin: 4px 0;
}
.tool-use-line code {
    background: transparent !important;
    color: #525252 !important;
    padding: 0 !important;
    font-size: 13px !important;
}

/* Reasoning panel — dimmed, italic, inside an st.expander.
   Renders the model's thinking blocks: visible only when the user opens the
   panel, so it doesn't compete with the answer for attention. */
.reasoning-panel {
    color: #525252 !important;
    font-size: 13.5px !important;
    line-height: 1.55;
    font-style: italic;
    padding: 4px 2px;
}
.reasoning-sep {
    border: none;
    border-top: 1px dashed #e5e5e5;
    margin: 10px 0;
}
[data-testid="stExpander"] summary {
    font-size: 12.5px !important;
    color: #737373 !important;
    font-weight: 500 !important;
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
