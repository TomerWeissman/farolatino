"""Chat view — single-page interface with @-skill autocomplete.

Uses the custom `skill_input` component for the input box. Each submit
spawns a fresh `claude --print` subprocess; the response streams into a
chat bubble. Multi-turn context is NOT passed to Claude in v1.
"""
from __future__ import annotations

import streamlit as st

from streamlit_app.claude_runner import ClaudeRunnerError, run_claude_streaming
from streamlit_app.components.skill_input import skill_input
from streamlit_app.run_log import RunLogger
from streamlit_app.skill_registry import list_skills


def _ensure_history() -> list[dict]:
    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []
    return st.session_state["chat_history"]


def render() -> None:
    history = _ensure_history()

    # Replay history
    for turn in history:
        with st.chat_message(turn["role"]):
            st.markdown(turn["content"])

    # Empty-state hint
    if not history:
        st.markdown(
            "<div style='color:#a3a3a3;text-align:center;padding:3rem 0;'>"
            "<div style='font-size:1.4rem;font-weight:500;color:#525252;margin-bottom:0.5rem;'>"
            "How can I help?"
            "</div>"
            "<div style='font-size:0.9rem;'>"
            "Type <code style='background:#f5f5f5;padding:1px 5px;border-radius:4px;'>@</code> "
            "to invoke a skill, or just ask a question."
            "</div>"
            "</div>",
            unsafe_allow_html=True,
        )

    # Skill list for the autocomplete component
    skills_payload = [
        {"slug": s.slug, "name": s.name, "description": s.description}
        for s in list_skills()
    ]

    user_msg = skill_input(
        skills=skills_payload,
        placeholder="Type a message…",
        key="chat_input_v2",
    )

    if not user_msg:
        return

    # Append user turn
    history.append({"role": "user", "content": user_msg})
    with st.chat_message("user"):
        st.markdown(user_msg)

    # Stream assistant response
    logger = RunLogger(prompt=user_msg)
    with st.chat_message("assistant"):
        placeholder = st.empty()
        accumulated: list[str] = []
        error_text: str | None = None
        try:
            for chunk in run_claude_streaming(user_msg, on_event=logger.record_event):
                accumulated.append(chunk)
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

    # Force a rerun so the empty input box is rendered fresh below the new bubble.
    st.rerun()
