"""Custom Streamlit component: chat input with @-skill autocomplete.

Usage:
    from streamlit_app.components.skill_input import skill_input
    msg = skill_input(
        skills=[{"slug": "evaluate", "name": "Evaluate Artist",
                 "description": "..."}],
        placeholder="Type a message…",
        key="chat_input",
    )
    if msg:
        # User submitted a message; handle it.

The frontend is a self-contained HTML+JS page in ./frontend/. It posts the
final message string back via `Streamlit.setComponentValue` when the user
presses Enter (without Shift).

Drop-up popup (above the input) appears when the user types `@`.
Filters as they keep typing. Hover on a skill shows its description.
Arrow keys navigate, Enter selects, Esc dismisses.
"""
from __future__ import annotations

from pathlib import Path

import streamlit.components.v1 as components

_FRONTEND_DIR = Path(__file__).parent / "frontend"

# `path=...` mode serves the frontend as static files. No build step needed
# because the component is plain HTML/CSS/JS.
_component_func = components.declare_component(
    "skill_input",
    path=str(_FRONTEND_DIR),
)


def skill_input(
    skills: list[dict],
    placeholder: str = "Type a message…",
    key: str | None = None,
    height: int = 110,
) -> str | None:
    """Render the chat input. Returns the submitted message or None.

    `skills` is a list of dicts, each with `slug`, `name`, `description`.
    Returns the raw message string (including any `@<slug>` prefix) when
    the user presses Enter; returns None on every other rerun.
    """
    return _component_func(
        skills=skills,
        placeholder=placeholder,
        height=height,
        key=key,
        default=None,
    )
