"""Release/upload cadence math — pure functions, no I/O.

Used by both the Spotify catalog enrichment (album release dates) and
the YouTube content-velocity enrichment (video upload dates). Takes a
flat list of ISO date strings and computes:

- latest_date           — most recent release/upload
- days_since_latest     — how stale the catalog/channel is
- cadence_days_6m       — average gap between releases in the last 6 months
- cadence_days_12m      — average gap between releases in the last 12 months
- trend                 — "accelerating" / "steady" / "decelerating"
                          (compares 6m cadence to 12m cadence)

Trend logic mirrors A&R intuition: an artist whose 6-month gap is at
least 20% shorter than their 12-month gap is releasing more often, so
they're "accelerating"; 20% longer = "decelerating"; in between = "steady".
"""
from __future__ import annotations

from datetime import date, datetime, timedelta


def _parse_date(s: str) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _avg_gap_days(sorted_dates: list[date]) -> int | None:
    """Average gap (in days) between consecutive sorted dates. None if <2."""
    if len(sorted_dates) < 2:
        return None
    total = (sorted_dates[-1] - sorted_dates[0]).days
    if total <= 0:
        return None
    return round(total / (len(sorted_dates) - 1))


def compute_release_cadence(
    release_dates: list[str],
    today: date | None = None,
) -> dict:
    """Roll a list of release/upload dates into cadence + trend signals.

    Returns a dict shaped like::

        {
          "latest_date": "2026-04-18",        # or None
          "days_since_latest": 23,            # or None
          "cadence_days_6m": 14,              # or None
          "cadence_days_12m": 21,             # or None
          "trend": "accelerating",            # or "steady" / "decelerating"
        }

    All numeric fields are ``None`` when the input is too thin to be
    meaningful (no dates, or only one in the window).
    """
    today = today or date.today()

    parsed = sorted({d for d in (_parse_date(s) for s in release_dates) if d})
    if not parsed:
        return {
            "latest_date": None,
            "days_since_latest": None,
            "cadence_days_6m": None,
            "cadence_days_12m": None,
            "trend": "steady",
        }

    latest = parsed[-1]
    days_since = (today - latest).days

    # Approximate windows with day arithmetic — calendar-accurate "6
    # months ago" needs no edge-case handling around year/month boundaries.
    cutoff_6m = today - timedelta(days=183)
    cutoff_12m = today - timedelta(days=365)
    in_6m = [d for d in parsed if d >= cutoff_6m]
    in_12m = [d for d in parsed if d >= cutoff_12m]

    cadence_6m = _avg_gap_days(in_6m)
    cadence_12m = _avg_gap_days(in_12m)

    # Trend: compare windows when both are present.
    if cadence_6m is not None and cadence_12m is not None and cadence_12m > 0:
        ratio = cadence_6m / cadence_12m
        if ratio <= 0.8:
            trend = "accelerating"
        elif ratio >= 1.2:
            trend = "decelerating"
        else:
            trend = "steady"
    else:
        trend = "steady"

    return {
        "latest_date": latest.isoformat(),
        "days_since_latest": days_since,
        "cadence_days_6m": cadence_6m,
        "cadence_days_12m": cadence_12m,
        "trend": trend,
    }
