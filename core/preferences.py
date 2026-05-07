"""User preferences (language, future toggles).

Lives in the per-user config dir alongside ``credentials.env`` so it
survives bundle upgrades. Currently holds a single field — the UI
language — but the file shape leaves room for future toggles.

Schema:
    {"language": "en" | "es"}

Defaults to ``"en"`` when the file is missing or malformed. Read by:
- ``api/routes/preferences.py``  — exposes GET/PUT for the frontend
- ``api/routes/chat.py``         — picks ``FAROAI.md`` vs ``FAROAI.es.md``
- ``api/routes/evaluate.py``     — passes lang to the dossier renderer
- ``mcp_server/tools/composite_*`` — same, for chat-side ``@evaluate``
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Literal

from core.paths import app_config_dir

log = logging.getLogger(__name__)

Language = Literal["en", "es"]
SUPPORTED_LANGUAGES: tuple[Language, ...] = ("en", "es")
DEFAULT_LANGUAGE: Language = "en"


def preferences_path() -> Path:
    """Where the preferences JSON lives. Survives bundle upgrades."""
    return app_config_dir() / "preferences.json"


def load_preferences() -> dict:
    """Read the preferences file. Returns an empty dict if missing or
    malformed — callers decide what defaults to apply via accessors
    like ``get_language()`` so we never throw at boot.
    """
    path = preferences_path()
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        return data
    except (OSError, json.JSONDecodeError):
        log.warning("preferences.json unreadable; falling back to defaults", exc_info=True)
        return {}


def save_preferences(prefs: dict) -> None:
    """Atomically write the preferences file. Only the keys we know
    about get persisted — defends against a bad PUT injecting garbage.
    """
    sanitized: dict = {}
    if "language" in prefs:
        lang = prefs["language"]
        if lang in SUPPORTED_LANGUAGES:
            sanitized["language"] = lang

    path = preferences_path()
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(sanitized, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def get_language() -> Language:
    """Resolve the active UI/LLM language. Used everywhere a renderer
    or persona loader needs to know which strings to emit.
    """
    lang = load_preferences().get("language")
    if lang in SUPPORTED_LANGUAGES:
        return lang  # type: ignore[return-value]
    return DEFAULT_LANGUAGE
