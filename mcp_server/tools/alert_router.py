"""Alert router — classifies score tier and detects signal-based alerts."""

from mcp_server.server import mcp
from mcp_server.tools.config_manager import _load_yaml


@mcp.tool()
def route_alert(scored_artist: dict) -> dict:
    """Determine alert tier and delivery channels for a scored artist.

    Args:
        scored_artist: Dict containing at minimum 'prospect_score' and 'name'.
                       May also contain metric diff fields for signal detection.
    """
    config = _load_yaml("alerts")
    score = scored_artist.get("prospect_score", 0)
    artist_name = scored_artist.get("name", "Unknown")

    # Score-based tier classification
    tier_name = "pass"
    tier_config = config["tiers"]["pass"]
    for name, tc in config["tiers"].items():
        if score >= tc["score_min"]:
            tier_name = name
            tier_config = tc
            break

    actions = {
        "artist": artist_name,
        "score": score,
        "tier": tier_name.upper(),
        "action": tier_config.get("action", "none"),
        "channels": tier_config.get("channels", []),
        "priority": tier_config.get("priority", "none"),
        "signal_alerts": [],
    }

    # Signal-based alerts (fire regardless of tier)
    for signal in config.get("signal_alerts", []):
        triggered = False

        if signal.get("type") == "field":
            field_name = signal.get("field", "")
            threshold = signal.get("threshold", 0)
            value = scored_artist.get(field_name)
            if value is not None and value > threshold:
                triggered = True
                actions["signal_alerts"].append({
                    "name": signal["name"],
                    "field": field_name,
                    "value": value,
                    "threshold": threshold,
                    "channels": signal.get("channels", []),
                })

        elif signal.get("type") == "event":
            condition = signal.get("condition", "")
            if condition == "new_editorial_playlist":
                editorial_count = scored_artist.get("new_editorial_playlists", 0)
                if editorial_count > 0:
                    triggered = True
            elif condition == "career_trend_explosive_growth":
                if scored_artist.get("career_trend") == "explosive growth":
                    triggered = True

            if triggered:
                actions["signal_alerts"].append({
                    "name": signal["name"],
                    "condition": condition,
                    "channels": signal.get("channels", []),
                })

    # Merge all unique channels from tier + signals
    all_channels = set(actions["channels"])
    for sa in actions["signal_alerts"]:
        all_channels.update(sa.get("channels", []))
    actions["all_channels"] = sorted(all_channels)

    return actions
