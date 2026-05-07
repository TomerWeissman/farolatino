"""GET / PUT /api/preferences — language toggle (and any future per-user toggles).

The UI's i18n provider hits ``GET`` on mount to know which language
to render the static text in, and ``PUT`` whenever the user flips
the toggle on the Settings page. The same value is read by:

- ``api/routes/chat.py`` to choose between ``FAROAI.md`` (English) and
  ``FAROAI.es.md`` (Spanish) when seeding the LLM's system prompt.
- ``api/routes/evaluate.py`` + composite skills to pick the right
  language for the server-rendered dossier Markdown.

Storage shape and atomic writes live in ``core/preferences.py``.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from core.preferences import (
    SUPPORTED_LANGUAGES,
    get_language,
    load_preferences,
    save_preferences,
)

router = APIRouter()


class Preferences(BaseModel):
    # Currently the only field. Modeled with a fixed enum so a stale
    # frontend can't write garbage that ``load_preferences`` would
    # then sanitize away silently.
    language: str

    @field_validator("language")
    @classmethod
    def _check_lang(cls, v: str) -> str:
        if v not in SUPPORTED_LANGUAGES:
            raise ValueError(
                f"language must be one of {SUPPORTED_LANGUAGES}, got {v!r}"
            )
        return v


@router.get("/preferences", response_model=Preferences)
def get_preferences() -> Preferences:
    """Return the current preferences, defaulting to ``en`` if the
    file is missing."""
    return Preferences(language=get_language())


@router.put("/preferences", response_model=Preferences)
def put_preferences(prefs: Preferences) -> Preferences:
    """Persist the new preferences and echo back the saved state."""
    current = load_preferences()
    current["language"] = prefs.language
    try:
        save_preferences(current)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"failed to save preferences: {e}") from e
    return prefs
