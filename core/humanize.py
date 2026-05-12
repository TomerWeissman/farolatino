"""Map raw tool names to friendly status labels.

Used by api/routes/chat.py to attach human-readable labels to SSE
tool_use events the frontend renders as status pills.
"""
from __future__ import annotations

_FAROLATINO_LABELS: dict[str, str] = {
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
}

_GENERIC_LABELS: dict[str, str] = {
    "ToolSearch": "Looking up tool details",
    "Read": "Reading file",
    "Glob": "Searching files",
    "Grep": "Searching content",
    "Bash": "Running shell command",
    "Agent": "Delegating to a subagent",
    "web_search": "Searching the web",
}


def humanize_tool(name: str) -> str:
    """Return a user-friendly label for an MCP / Claude Code tool name.

    Unknown mcp__farolatino__ tools fall back to a deslugified version
    ('mcp__farolatino__some_thing' → 'Some thing') so future tools surface
    sensibly without a code change.
    """
    if not name:
        return "tool"
    if name.startswith("mcp__farolatino__"):
        if name in _FAROLATINO_LABELS:
            return _FAROLATINO_LABELS[name]
        return name.removeprefix("mcp__farolatino__").replace("_", " ").capitalize()
    return _GENERIC_LABELS.get(name, name)
