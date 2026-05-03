"""Chat view — single-page interface (v0.dev-style minimal).

Uses our custom `skill_input` component for the textbox so the user gets
@-autocomplete on skill names (with arrow-key navigation, Enter-to-pick,
hover descriptions). The component returns `{"message": ..., "nonce": ...}`
and we dedup by nonce so re-renders don't double-process a submission.

Streaming UX:
- Before the first text chunk arrives: show a pulsing "Thinking…"
  placeholder so the user knows the request is in flight.
- During tool use: render a quiet status line per tool invocation
  ("Searching Chartmetric…" rather than "_using ToolSearch..._").
- Streaming text is throttled to ~10 fps so long dossier responses
  don't re-render on every chunk.
"""
from __future__ import annotations

import re
import time

import streamlit as st

from streamlit_app.claude_runner import (
    THINKING_PREFIX,
    ClaudeRunnerError,
    run_claude_streaming,
)
from streamlit_app.components.skill_input import skill_input
from streamlit_app.run_log import RunLogger
from streamlit_app.skill_registry import list_skills


def _ensure_history() -> list[dict]:
    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []
    return st.session_state["chat_history"]


def _skill_cheatsheet() -> None:
    skills = list_skills()
    if not skills:
        return
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


def _humanize_tool(name: str) -> str:
    """Map raw tool names to friendly status labels."""
    if name.startswith("mcp__farolatino__"):
        return {
            "mcp__farolatino__evaluate_artist": "Evaluating artist (full pipeline)",
            "mcp__farolatino__find_similar_artists": "Finding similar artists",
            "mcp__farolatino__search_artists": "Searching Chartmetric",
            "mcp__farolatino__search_artist_by_url": "Looking up artist",
            "mcp__farolatino__get_artist_data": "Pulling artist data (14 endpoints)",
            "mcp__farolatino__compute_prospect_score": "Scoring across 7 dimensions",
            "mcp__farolatino__estimate_revenue": "Projecting revenue",
            "mcp__farolatino__generate_dossier": "Building dossier",
            "mcp__farolatino__route_alert": "Classifying alert tier",
            "mcp__farolatino__discover_artists": "Discovering prospects",
            "mcp__farolatino__discover_artists_multi_country": "Discovering across markets",
            "mcp__farolatino__list_profiles": "Loading scoring profiles",
            "mcp__farolatino__get_profile": "Loading scoring profile",
            "mcp__farolatino__load_config": "Loading config",
            "mcp__farolatino__cache_get": "Reading cache",
            "mcp__farolatino__cache_set": "Writing cache",
            "mcp__farolatino__cache_clear": "Clearing cache",
        }.get(name, name.removeprefix("mcp__farolatino__").replace("_", " ").capitalize())
    return {
        "ToolSearch": "Looking up tool details",
        "Read": "Reading file",
        "Glob": "Searching files",
        "Grep": "Searching content",
        "Bash": "Running shell command",
        "Agent": "Delegating to a subagent",
    }.get(name, name)


def _render_user_bubble(text: str) -> None:
    """Right-aligned user bubble. We can't rely on st.chat_message's user
    role styling because Streamlit's CSS hooks aren't reliable across
    versions, so render directly with our own class."""
    safe = (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>")
    )
    st.markdown(
        f"<div class='chat-user-row'><div class='chat-user-bubble'>{safe}</div></div>",
        unsafe_allow_html=True,
    )


def render() -> None:
    history = _ensure_history()

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
        for turn in history:
            if turn["role"] == "user":
                _render_user_bubble(turn["content"])
            else:
                blocks = turn.get("thinking") or []
                if blocks:
                    with st.expander("💭 Reasoning", expanded=False):
                        st.markdown(
                            "<div class='reasoning-panel'>"
                            + "<hr class='reasoning-sep'>".join(
                                b.replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
                                for b in blocks
                            )
                            + "</div>",
                            unsafe_allow_html=True,
                        )
                st.markdown(turn["content"])

    # Skill registry → list of {slug, name, description} for the autocomplete
    skills_for_input = [
        {"slug": s.slug, "name": s.name or s.slug, "description": s.description or ""}
        for s in list_skills()
    ]
    submission = skill_input(
        skills=skills_for_input,
        placeholder="Type a message, or @ for skills",
        key="chat_input",
    )
    # Dedup by nonce: Streamlit equality-checks component values, so a re-render
    # would otherwise re-process the same submission on every interaction.
    user_msg: str | None = None
    if isinstance(submission, dict):
        nonce = submission.get("nonce")
        last_nonce = st.session_state.get("last_chat_nonce", 0)
        if nonce and nonce > last_nonce:
            st.session_state["last_chat_nonce"] = nonce
            user_msg = (submission.get("message") or "").strip() or None
    if not user_msg:
        return

    history.append({"role": "user", "content": user_msg})
    _render_user_bubble(user_msg)

    # Thinking indicator (replaced when first chunk arrives)
    status = st.empty()
    status.markdown(
        "<div class='chat-status'><span class='dot'></span>Thinking…</div>",
        unsafe_allow_html=True,
    )

    logger = RunLogger(prompt=user_msg)
    # Reasoning panel placeholder is reserved ABOVE the response so it appears
    # in natural reading order. We populate it the moment the first thinking
    # block arrives; it stays empty (and invisible) on prompts where the model
    # doesn't think.
    thinking_slot = st.empty()
    placeholder = st.empty()
    accumulated: list[str] = []
    thinking_blocks: list[str] = []
    last_render = 0.0
    error_text: str | None = None
    has_text = False

    def _on_event(event: dict) -> None:
        logger.record_event(event)
        # Whenever we see a tool_use, update the status indicator.
        if event.get("type") == "assistant":
            for b in (event.get("message") or {}).get("content") or []:
                if b.get("type") == "tool_use":
                    label = _humanize_tool(b.get("name", "tool"))
                    status.markdown(
                        f"<div class='chat-status'><span class='dot'></span>{label}…</div>",
                        unsafe_allow_html=True,
                    )

    def _render_thinking() -> None:
        if not thinking_blocks:
            return
        with thinking_slot.container():
            with st.expander("💭 Reasoning", expanded=False):
                st.markdown(
                    "<div class='reasoning-panel'>"
                    + "<hr class='reasoning-sep'>".join(
                        block.replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
                        for block in thinking_blocks
                    )
                    + "</div>",
                    unsafe_allow_html=True,
                )

    try:
        for chunk in run_claude_streaming(user_msg, on_event=_on_event):
            # Route thinking deltas to the Reasoning panel; everything else is
            # response text.
            if chunk.startswith(THINKING_PREFIX):
                thinking_blocks.append(chunk[len(THINKING_PREFIX):])
                _render_thinking()
                continue
            # Strip the auto-generated `_using <tool>..._` lines from the
            # text stream — we already render them via the status indicator.
            cleaned = re.sub(r"\n*_using `[^`]+`\.\.\._\n*", "", chunk)
            if cleaned.strip():
                if not has_text:
                    has_text = True
                    status.empty()  # remove "Thinking…" once real text arrives
                accumulated.append(cleaned)
                now = time.monotonic()
                if now - last_render > 0.10:
                    placeholder.markdown("".join(accumulated))
                    last_render = now
        placeholder.markdown("".join(accumulated))
    except ClaudeRunnerError as exc:
        error_text = str(exc)
        status.empty()
        placeholder.error(f"⚠️ {exc}")
    except Exception as exc:
        error_text = f"Unexpected error: {exc}"
        status.empty()
        placeholder.error(error_text)
    finally:
        # If we never received text and never errored, leave a small note
        if not has_text and not error_text:
            status.empty()
            placeholder.markdown("_(no response)_")

    final_text = "".join(accumulated).strip() or "_(no response)_"
    if error_text:
        history.append({"role": "assistant", "content": f"⚠️ {error_text}"})
    else:
        history.append({
            "role": "assistant",
            "content": final_text,
            "thinking": list(thinking_blocks),
        })

    logger.finalize(
        response_text="".join(accumulated),
        error=error_text,
        thinking_blocks=thinking_blocks,
    )
