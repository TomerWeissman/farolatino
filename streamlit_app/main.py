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
/* === Design tokens =====================================================
   Single source of truth for color, spacing, radius, type. Edit these to
   adjust the whole UI; downstream rules just reference var(...).
   Tuned to match the Claude.ai feel: pure white, generous whitespace,
   soft borders, gentle radius, dark text, muted secondaries. */
:root {
    color-scheme: light !important;
    --bg:           #ffffff;
    --bg-subtle:    #fafafa;
    --bg-bubble:    #f4f4f4;   /* user bubble + code bg */
    --bg-hover:     #f2f2f2;
    --text:         #0a0a0a;
    --text-muted:   #525252;
    --text-faint:   #737373;
    --text-soft:    #a3a3a3;
    --border:       #e5e5e5;
    --border-soft:  #ececec;
    --border-dash:  #d4d4d4;
    --radius-sm:    8px;
    --radius:       12px;
    --radius-lg:    16px;
    --radius-input: 16px;
    --space-1:      4px;
    --space-2:      8px;
    --space-3:      12px;
    --space-4:      16px;
    --space-5:      24px;
    --space-6:      32px;
    --font-sans:    Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    --font-size-md: 15px;
    --font-size-sm: 13px;
    --font-size-xs: 12px;
    --shadow-input-focus: 0 0 0 3px rgba(0,0,0,0.06);
}

/* Remove Streamlit chrome */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header[data-testid="stHeader"] {display: none;}
[data-testid="stToolbar"] {display: none;}

/* Hide the "RUNNING / STOP" status badge in the top-right. Streamlit
   re-runs the script on every UI interaction (expander toggle, link
   click, scroll within a managed component) — the badge would flash
   constantly and read as "always loading" to a non-technical user.
   We keep our own per-message status pill ("Thinking…" / "Searching
   Chartmetric…") which is more meaningful. */
[data-testid="stStatusWidget"] { display: none !important; }
[data-testid="stConnectionStatus"] { display: none !important; }
/* Also kill the top-of-page progress bar that flashes on each rerun */
[data-testid="stDecoration"] { display: none !important; }

/* === Canvas + layout ================================================== */
html, body,
.stApp,
[data-testid="stAppViewContainer"],
.main,
[data-testid="stMain"],
[data-testid="block-container"] {
    background: var(--bg) !important;
    color: var(--text) !important;
}

/* Centered narrow column. Bottom padding leaves room for the sticky chat
   input so the last message isn't covered. */
.main .block-container {
    max-width: 720px;
    padding: 4rem var(--space-5) 10rem var(--space-5);
}

/* Typography — Inter / system stack, tight, pinned dark */
html, body, [class*="css"], .stMarkdown, p, li, span, div {
    font-family: var(--font-sans);
    color: var(--text) !important;
    -webkit-font-smoothing: antialiased;
}
html, body { letter-spacing: -0.01em; }
h1, h2, h3, h4, h5, h6 { color: var(--text) !important; }

/* Wordmark in the top-left corner only */
.wordmark {
    position: fixed;
    top: var(--space-4);
    left: var(--space-5);
    font-size: var(--font-size-xs);
    color: var(--text-faint);
    letter-spacing: 0.05em;
    text-transform: uppercase;
    font-weight: 500;
    z-index: 100;
    user-select: none;
}

/* Empty state — vertically centered greeting */
.empty-state {
    text-align: center;
    padding: 3.5rem 0 var(--space-5);
}
.empty-greet {
    font-size: 1.6rem;
    font-weight: 500;
    color: var(--text);
    letter-spacing: -0.02em;
}
.empty-hint {
    color: var(--text-faint);
    font-size: 0.9rem;
    margin-top: var(--space-1);
}

/* Skill cheatsheet (empty state, hover-tooltip pills) */
.skills-row {
    text-align: center;
    margin: var(--space-5) 0 0;
    color: var(--text-soft);
    font-size: 0.85rem;
    line-height: 1.9;
}
.skill-pill {
    color: var(--text-muted);
    font-weight: 500;
    cursor: help;
    border-bottom: 1px dotted var(--border-dash);
}

/* === Skill picker row (above the input, always visible during chat) ==== */
/* st.button cells in the picker row — slim chips, no borders, hover lift. */
[data-testid="stHorizontalBlock"] [data-testid="stButton"] > button[kind="secondary"] {
    background: var(--bg) !important;
    border: 1px solid var(--border) !important;
    color: var(--text-muted) !important;
    border-radius: 999px !important;
    padding: 6px 12px !important;
    font-size: var(--font-size-sm) !important;
    font-weight: 500 !important;
    min-height: 0 !important;
    height: auto !important;
    transition: background-color 0.12s, border-color 0.12s, color 0.12s;
}
[data-testid="stHorizontalBlock"] [data-testid="stButton"] > button[kind="secondary"]:hover {
    background: var(--bg-hover) !important;
    border-color: var(--border-dash) !important;
    color: var(--text) !important;
}
.skill-queued {
    display: inline-block;
    background: var(--bg-bubble);
    color: var(--text-muted);
    font-size: var(--font-size-sm);
    padding: 4px 10px;
    border-radius: 999px;
    margin-bottom: var(--space-2);
}

/* === Chat messages ===================================================== */
[data-testid="stChatMessage"] {
    background: transparent !important;
    border: none !important;
    padding: var(--space-2) 0;
    gap: var(--space-3);
}
[data-testid="stChatMessage"] .stMarkdown,
[data-testid="stChatMessage"] .stMarkdown p {
    color: var(--text) !important;
    line-height: 1.65;
}
[data-testid="stChatMessageAvatarUser"],
[data-testid="stChatMessageAvatarAssistant"] {
    display: none !important;
}

/* User message — right-aligned tinted bubble. */
.chat-user-bubble {
    display: inline-block;
    background: var(--bg-bubble) !important;
    border-radius: var(--radius-lg);
    padding: 10px 16px;
    max-width: 80%;
    color: var(--text) !important;
    margin-left: auto;
    line-height: 1.5;
}
.chat-user-row {
    display: flex;
    justify-content: flex-end;
    margin: var(--space-3) 0;
}

/* Assistant prose — flush, looser line-height for readability */
[data-testid="stChatMessage"]:not(:has(.chat-user-bubble)) .stMarkdown {
    line-height: 1.7;
}
.stMarkdown table {
    border-collapse: collapse;
    margin: var(--space-3) 0;
    font-size: var(--font-size-sm);
}
.stMarkdown table th, .stMarkdown table td {
    border-top: 1px solid var(--border-soft) !important;
    border-bottom: 1px solid var(--border-soft) !important;
    border-left: none !important;
    border-right: none !important;
    padding: 8px 12px;
}
.stMarkdown table th {
    background: var(--bg-subtle) !important;
    font-weight: 600;
    text-align: left;
}

/* Status / "thinking" indicator */
.chat-status {
    color: var(--text-faint) !important;
    font-size: 14px;
    font-style: italic;
    padding: var(--space-2) 0;
    display: flex;
    align-items: center;
    gap: var(--space-2);
}
.chat-status .dot {
    width: 6px; height: 6px;
    border-radius: 50%;
    background: var(--text-faint);
    animation: pulse 1.2s ease-in-out infinite;
}
@keyframes pulse {
    0%, 100% { opacity: 0.3; transform: scale(1); }
    50%      { opacity: 1.0; transform: scale(1.3); }
}
.tool-use-line {
    color: var(--text-faint) !important;
    font-size: var(--font-size-sm);
    padding: var(--space-1) 0;
    border-left: 2px solid var(--border-soft);
    padding-left: 10px;
    margin: var(--space-1) 0;
}
.tool-use-line code {
    background: transparent !important;
    color: var(--text-muted) !important;
    padding: 0 !important;
    font-size: var(--font-size-sm) !important;
}

/* Reasoning panel (collapsible thinking blocks) */
.reasoning-panel {
    color: var(--text-muted) !important;
    font-size: 13.5px !important;
    line-height: 1.55;
    font-style: italic;
    padding: var(--space-1) 2px;
}
.reasoning-sep {
    border: none;
    border-top: 1px dashed var(--border);
    margin: 10px 0;
}
[data-testid="stExpander"] {
    border: none !important;
    background: transparent !important;
}
[data-testid="stExpander"] summary {
    font-size: var(--font-size-xs) !important;
    color: var(--text-faint) !important;
    font-weight: 500 !important;
}

/* === Chat input — sticky at the viewport bottom (Claude-style) ========== */
/* Streamlit normally puts the input inline below the script; we float it
   to the bottom so the last message is always visible above it. The bottom
   container also gets a fade-out backdrop so content doesn't bleed through. */
[data-testid="stBottom"] {
    background: linear-gradient(to bottom,
        rgba(255,255,255,0) 0%,
        rgba(255,255,255,0.95) 25%,
        var(--bg) 100%) !important;
    padding-bottom: var(--space-5) !important;
}
[data-testid="stChatInput"] {
    max-width: 720px !important;
    margin: 0 auto !important;
}
[data-testid="stChatInput"] > div {
    background: var(--bg) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-input) !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    transition: border-color 0.15s, box-shadow 0.15s;
}
[data-testid="stChatInput"] > div:focus-within {
    border-color: var(--text) !important;
    box-shadow: var(--shadow-input-focus);
}
[data-testid="stChatInput"] textarea {
    border: none !important;
    background: transparent !important;
    color: var(--text) !important;
    font-size: var(--font-size-md) !important;
    padding: 14px 16px !important;
    min-height: 56px !important;
}
[data-testid="stChatInput"] textarea::placeholder {
    color: var(--text-soft) !important;
}

/* Sidebar (only visible in ?debug=1 mode) — quiet */
section[data-testid="stSidebar"] {
    background: var(--bg-subtle) !important;
    border-right: 1px solid var(--border-soft);
}
section[data-testid="stSidebar"] .stMarkdown h3 {
    font-size: 0.78rem;
    color: var(--text-faint);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-weight: 600;
    margin-top: var(--space-4);
}

/* Soften misc Streamlit elements */
code {
    background: var(--bg-bubble);
    color: var(--text);
    padding: 1px 5px;
    border-radius: var(--radius-sm);
    font-size: 0.88em;
}
hr {
    border-color: var(--border-soft) !important;
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
