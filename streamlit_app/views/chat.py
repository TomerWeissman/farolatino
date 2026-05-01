"""Chat view — single-page interface (v0.dev-style minimal).

Uses Streamlit's built-in `st.chat_input` for the textbox (proven to
work end-to-end with our run logger). A small skills cheatsheet sits
quietly at the top so the user knows the `@<skill>` syntax. The custom
autocomplete component is on the back-burner until its IPC is fixed —
the user-facing flow doesn't need it to be functional.

Streaming is throttled to ~10 fps so long dossier responses don't
re-render the markdown blob on every text chunk.
"""
from __future__ import annotations

import time

import streamlit as st

from streamlit_app.claude_runner import ClaudeRunnerError, run_claude_streaming
from streamlit_app.run_log import RunLogger
from streamlit_app.skill_registry import list_skills


def _ensure_history() -> list[dict]:
    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []
    return st.session_state["chat_history"]


def _skill_cheatsheet() -> None:
    """Quiet inline list of skills above the chat. Hover for descriptions."""
    skills = list_skills()
    if not skills:
        return
    # Render as plain text with abbr tags for native browser tooltips
    parts = []
    for s in skills:
        desc = (s.description or s.name or s.slug).replace('"', "&quot;")
        parts.append(
            f'<span class="skill-pill" title="{desc}">@{s.slug}</span>'
        )
    st.markdown(
        "<div class='skills-row'>" + " · ".join(parts) + "</div>",
        unsafe_allow_html=True,
    )


def render() -> None:
    history = _ensure_history()

    # Empty state — show skill cheatsheet only when no chat yet
    if not history:
        st.markdown(
            "<div class='empty-state'>"
            "<div class='empty-greet'>How can I help?</div>"
            "<div class='empty-hint'>Type a message, or start with one of the skills below.</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        _skill_cheatsheet()
    else:
        # Replay history
        for turn in history:
            with st.chat_message(turn["role"]):
                st.markdown(turn["content"])

    # The input — stock Streamlit chat_input (works end-to-end)
    user_msg = st.chat_input(
        placeholder="Type a message, or @<skill> to invoke a skill",
    )
    if not user_msg:
        return

    # Append user turn
    history.append({"role": "user", "content": user_msg})
    with st.chat_message("user"):
        st.markdown(user_msg)

    # Stream assistant response with telemetry + chunk buffering
    logger = RunLogger(prompt=user_msg)
    with st.chat_message("assistant"):
        placeholder = st.empty()
        accumulated: list[str] = []
        last_render = 0.0
        error_text: str | None = None
        try:
            for chunk in run_claude_streaming(user_msg, on_event=logger.record_event):
                accumulated.append(chunk)
                # Throttle markdown re-renders to ~10 fps. Streamlit re-parses
                # the full string each call, so calling once per token causes
                # visible jank on long responses.
                now = time.monotonic()
                if now - last_render > 0.10:
                    placeholder.markdown("".join(accumulated))
                    last_render = now
            # Final flush so the last chunk renders even if it landed inside
            # the throttle window.
            placeholder.markdown("".join(accumulated))
        except ClaudeRunnerError as exc:
            error_text = str(exc)
            placeholder.error(f"⚠️ {exc}")
        except Exception as exc:  # defensive
            error_text = f"Unexpected error: {exc}"
            placeholder.error(error_text)

    final_text = "".join(accumulated).strip() or "_(no response)_"
    if error_text:
        history.append({"role": "assistant", "content": f"⚠️ {error_text}"})
    else:
        history.append({"role": "assistant", "content": final_text})

    logger.finalize(response_text="".join(accumulated), error=error_text)
