"""Artist / FaroLatino revenue-share resolver.

Reads ``config/revenue_share.yaml`` and returns the configured split.
The Evaluate dossier embeds this so the UI doesn't have to hardcode
the 70/30 percentages — change the YAML, restart, and the dashboard
picks up the new split automatically.

Separate file (not folded into ``revenue_model.py``) so the share
config and the streaming-revenue model can evolve independently.
"""
from __future__ import annotations

import yaml

from core.paths import resource_path

_FALLBACK_ARTIST = 0.70
_FALLBACK_FARO = 0.30


def load_revenue_share() -> dict:
    """Return ``{"artist_pct": float, "faro_pct": float}``.

    Falls back to the 70/30 default if the config file is missing,
    malformed, or has shares that don't sum close enough to 1.0. We
    log nothing on the fallback path — a broken YAML shouldn't crash
    every evaluate request, and the dashboard renders the fallback
    just fine.
    """
    try:
        with open(resource_path("config/revenue_share.yaml")) as fh:
            data = yaml.safe_load(fh) or {}
        artist = float(data.get("artist_pct", _FALLBACK_ARTIST))
        faro = float(data.get("faro_pct", _FALLBACK_FARO))
        # Tolerate small rounding errors but reject sums that are
        # clearly wrong (e.g. someone typed 0.7 / 0.7 instead of 0.7 / 0.3).
        if not 0.95 <= (artist + faro) <= 1.05:
            return {"artist_pct": _FALLBACK_ARTIST, "faro_pct": _FALLBACK_FARO}
        return {"artist_pct": artist, "faro_pct": faro}
    except (OSError, yaml.YAMLError, ValueError, TypeError):
        return {"artist_pct": _FALLBACK_ARTIST, "faro_pct": _FALLBACK_FARO}
