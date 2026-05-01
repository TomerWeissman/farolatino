"""Chat view — the single page in the FaroLatino dashboard.

User types into a chat box (with `@<skill>` prefix to invoke a skill).
Each submit spawns a fresh `claude --print` subprocess; the response
streams into a chat bubble.

Multi-turn context isn't passed to Claude in v1 — every message is a
self-contained query. The UI keeps history visually so the user can
see prior turns.
"""
from __future__ import annotations

import streamlit as st

from streamlit_app.claude_runner import ClaudeRunnerError, run_claude_streaming
from streamlit_app.run_log import RunLogger


def _ensure_history() -> list[dict]:
    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []
    return st.session_state["chat_history"]


def render() -> None:
    history = _ensure_history()

    # Header row: clear chat + small caption
    col_left, col_right = st.columns([6, 1])
    with col_left:
        st.markdown(
            "Type your message below. Use `@<skill>` (e.g. `@evaluate Bad Bunny`) "
            "to invoke a skill — see the sidebar for the full list."
        )
    with col_right:
        if st.button("Clear", help="Clear the chat history"):
            st.session_state["chat_history"] = []
            st.rerun()

    # Replay history
    for turn in history:
        with st.chat_message(turn["role"]):
            st.markdown(turn["content"])

    # If a sidebar skill was clicked, stage it as a default value for the
    # chat input. We can't directly inject into st.chat_input (no value
    # parameter), so we show a visible "staged prefix" badge and the user
    # types the rest.
    pending_prefix = st.session_state.pop("pending_chat_prefix", None)
    if pending_prefix:
        st.session_state["staged_prefix"] = pending_prefix

    staged = st.session_state.get("staged_prefix", "")
    if staged:
        st.info(
            f"Staged: `{staged.strip()}` — type your context below "
            "(e.g. an artist name) and press Enter."
        )

    user_msg = st.chat_input(
        placeholder="Type a message, or @<skill> to invoke a skill",
    )
    if not user_msg:
        return

    full_prompt = (staged + user_msg).strip() if staged else user_msg.strip()
    st.session_state.pop("staged_prefix", None)

    # Render user turn immediately
    history.append({"role": "user", "content": full_prompt})
    with st.chat_message("user"):
        st.markdown(full_prompt)

    # Stream assistant response with telemetry capture
    logger = RunLogger(prompt=full_prompt)
    with st.chat_message("assistant"):
        placeholder = st.empty()
        accumulated: list[str] = []
        error_text: str | None = None
        try:
            for chunk in run_claude_streaming(full_prompt, on_event=logger.record_event):
                accumulated.append(chunk)
                placeholder.markdown("".join(accumulated))
        except ClaudeRunnerError as exc:
            error_text = str(exc)
            placeholder.error(f"⚠️ {exc}")
        except Exception as exc:  # pragma: no cover — defensive
            error_text = f"Unexpected error: {exc}"
            placeholder.error(error_text)

    final_text = "".join(accumulated).strip() or "_(no response)_"
    if error_text:
        history.append({"role": "assistant", "content": f"⚠️ {error_text}"})
    else:
        history.append({"role": "assistant", "content": final_text})

    logger.finalize(response_text="".join(accumulated), error=error_text)
