"""Shared Streamlit components: header, badges, status indicators, skill picker."""
from __future__ import annotations

import json
import os
from pathlib import Path

import streamlit as st
import yaml

from core.run_log import load_recent
from core.skill_registry import list_skills

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STREAM_MULTIPLIERS_PATH = PROJECT_ROOT / "config" / "stream_multipliers.yaml"


def skill_picker_sidebar() -> None:
    """Sidebar list of available skills with descriptions.

    Clicking a skill stages `@<slug> ` into the pending chat input via
    session state, so the chat view can pre-fill its textbox. Always
    visible; never hidden behind hover-only states (we use the `help`
    parameter for an inline tooltip in addition to the visible blurb).
    """
    skills = list_skills()
    if not skills:
        st.info("No skills found in `.claude/skills/`.")
        return

    st.markdown("### Skills")
    st.caption("Click a skill to stage it in the chat input below.")

    for skill in skills:
        if st.button(
            f"@{skill.slug}",
            key=f"skill_btn_{skill.slug}",
            help=skill.description or skill.name,
            use_container_width=True,
        ):
            st.session_state["pending_chat_prefix"] = f"@{skill.slug} "
            st.rerun()
        if skill.description:
            st.caption(skill.description)


def recent_runs_sidebar(limit: int = 10) -> None:
    """Sidebar expander showing the last N chat runs with status icons.

    Each run is clickable; clicking shows the prompt, response, tools
    invoked, MCP server status, and the full event trace. Aimed at the
    person testing the system, not at end-users.
    """
    st.markdown("### Recent runs")
    runs = load_recent(limit=limit)
    if not runs:
        st.caption("No chat runs yet.")
        return

    failures = [r for r in runs if r.status != "ok"]
    if failures:
        st.warning(f"{len(failures)}/{len(runs)} recent runs failed or returned no text.")

    for r in runs:
        with st.expander(r.summary(), expanded=False):
            cols = st.columns(3)
            cols[0].metric("Status", r.status.upper())
            cols[1].metric("Duration", f"{r.duration_s:.1f}s")
            cols[2].metric("Events", r.event_count)

            if r.cost_usd is not None:
                st.caption(f"Cost: ${r.cost_usd:.4f}")

            st.markdown("**Prompt:**")
            st.code(r.prompt, language="text")

            if r.tool_calls:
                st.markdown(f"**Tools called ({len(r.tool_calls)}):** " + ", ".join(f"`{t}`" for t in r.tool_calls))
            else:
                st.markdown("**Tools called:** _(none)_")

            if r.mcp_servers:
                bad = [s for s in r.mcp_servers if s.get("status") != "connected"]
                farolatino = next((s for s in r.mcp_servers if s.get("name") == "farolatino"), None)
                if farolatino:
                    icon = "✓" if farolatino.get("status") == "connected" else "✗"
                    st.markdown(f"**FaroLatino MCP:** {icon} {farolatino.get('status')}")
                else:
                    st.markdown("**FaroLatino MCP:** ⚠ not in server list")
                if bad:
                    st.caption(f"{len(bad)} MCP server(s) failed: " + ", ".join(s.get("name", "?") for s in bad))

            if r.error:
                st.markdown("**Error:**")
                st.error(r.error)

            st.markdown("**Response:**")
            st.markdown(r.response_text or "_(empty)_")

            blocks = getattr(r, "thinking_blocks", []) or []
            if blocks:
                with st.expander(f"💭 Reasoning ({len(blocks)} block{'s' if len(blocks) != 1 else ''})", expanded=False):
                    for i, block in enumerate(blocks):
                        if i > 0:
                            st.markdown("---")
                        st.markdown(block)

            with st.expander("Full event trace", expanded=False):
                st.code(json.dumps(r.events, indent=2, default=str), language="json")


@st.cache_data(show_spinner=False, ttl=300)
def _ping_chartmetric() -> tuple[str, str]:
    """Try to mint a Chartmetric access token and report status.

    Returns (status, message): status in {ok, auth_failed, network_error, no_token}.
    Cached 5 min so we don't burn the per-second rate limit on every rerun.
    """
    token = os.getenv("CHARTMETRIC_REFRESH_TOKEN")
    if not token:
        return ("no_token", "No CHARTMETRIC_REFRESH_TOKEN in .env")
    try:
        # Lazy import so module-load doesn't trigger network calls
        from mcp_server.tools.chartmetric_auth import get_access_token
        access = get_access_token()
        if access:
            return ("ok", "Chartmetric connected")
        return ("auth_failed", "Chartmetric returned an empty token")
    except ConnectionError as exc:
        msg = str(exc)
        if "401" in msg or "auth" in msg.lower():
            return ("auth_failed", "Chartmetric rejected the refresh token")
        return ("network_error", f"Cannot reach Chartmetric: {msg[:80]}")
    except Exception as exc:
        return ("network_error", f"Unexpected error: {str(exc)[:80]}")


def connection_status_badge() -> None:
    """Sidebar badge showing live Chartmetric API connection state."""
    status, message = _ping_chartmetric()
    color, icon, label = {
        "ok":           ("#22c55e", "✓", "Chartmetric connected"),
        "auth_failed":  ("#ef4444", "✗", "Token rejected"),
        "network_error":("#eab308", "⚠", "Connection issue"),
        "no_token":     ("#94a3b8", "—", "No token configured"),
    }[status]

    st.markdown(
        f"<div style='background:{color}; color:white; padding:8px 12px; "
        f"border-radius:6px; font-weight:600; margin-bottom:8px;'>"
        f"{icon} {label}</div>",
        unsafe_allow_html=True,
    )
    if status != "ok":
        st.caption(message)


def page_header() -> None:
    """Page-wide header. FaroLatino branding + tagline."""
    col_logo, col_text = st.columns([1, 6])
    with col_logo:
        st.markdown("# 🎵")
    with col_text:
        st.markdown("# FaroLatino A&R Dashboard")
        st.caption(
            "Total artist revenue projection · prospect ranking · competitive landscape"
        )
    st.divider()


def calibration_footer() -> None:
    """Sidebar footer showing model freshness + accuracy."""
    st.markdown("### Model status")
    if not STREAM_MULTIPLIERS_PATH.exists():
        st.warning("`stream_multipliers.yaml` not found.")
        return
    cfg = yaml.safe_load(STREAM_MULTIPLIERS_PATH.read_text()) or {}
    last_cal = cfg.get("last_calibrated", "—")
    sample = cfg.get("calibration_sample_size", "—")
    mae = cfg.get("realistic_prospect_mae_pct", "—")

    st.markdown(
        f"""
**Last calibrated:** `{last_cal}`
**Sample size:** `{sample}` artists
**Realistic-prospect MAE:** `{mae}%`
        """
    )
    st.caption(
        "Run `/calibrate` (or `scripts/expand_calibration_sample.py`) to refresh."
    )


def confidence_badge(level: str) -> None:
    """Inline badge for High/Medium/Low confidence."""
    color = {"High": "#22c55e", "Medium": "#eab308", "Low": "#ef4444"}.get(level, "#94a3b8")
    st.markdown(
        f"<span style='background:{color}; color:white; padding:4px 10px; "
        f"border-radius:6px; font-weight:600; font-size:14px;'>"
        f"Confidence: {level}</span>",
        unsafe_allow_html=True,
    )


def tier_badge(tier: str) -> None:
    """HOT / WARM / WATCH / PASS pill."""
    color = {
        "HOT": "#ef4444",
        "WARM": "#f97316",
        "WATCH": "#eab308",
        "PASS": "#94a3b8",
    }.get(tier, "#94a3b8")
    st.markdown(
        f"<span style='background:{color}; color:white; padding:6px 14px; "
        f"border-radius:8px; font-weight:700; font-size:18px;'>{tier}</span>",
        unsafe_allow_html=True,
    )
