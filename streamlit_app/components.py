"""Shared Streamlit components: header, badges, calibration status footer."""
from __future__ import annotations

import os
from pathlib import Path

import streamlit as st
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STREAM_MULTIPLIERS_PATH = PROJECT_ROOT / "config" / "stream_multipliers.yaml"


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
