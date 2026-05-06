"""GET / PUT /api/persona — read/write the FaroAI persona.

V2 overlay: GET resolves through user/persona.md → code/FAROAI.md →
bundled FAROAI.md. PUT always writes to user/persona.md so the user's
edits survive code-only updates. POST /persona/reset drops the user
layer copy and falls back to whatever default is underneath.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.schemas import PersonaPayload
from core import overlay
from core.overlay import Source

router = APIRouter()


@router.get("/persona", response_model=PersonaPayload)
def get_persona() -> PersonaPayload:
    found = overlay.resolve_file("persona")
    if found is None:
        return PersonaPayload(content="")
    return PersonaPayload(content=found.path.read_text(encoding="utf-8"))


@router.put("/persona", response_model=PersonaPayload)
def put_persona(payload: PersonaPayload) -> PersonaPayload:
    # Refuse pathological writes (someone PUT-ing megabytes by accident).
    if len(payload.content) > 200_000:
        raise HTTPException(status_code=413, detail="persona content >200kB; refusing to write")
    target = overlay.user_path("persona", "persona.md")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(payload.content, encoding="utf-8")
    return payload


@router.post("/persona/reset", response_model=PersonaPayload)
def reset_persona() -> PersonaPayload:
    """Drop the user-layer persona so the bundled / update default
    takes over again."""
    overlay.reset_to_default("persona", "persona.md")
    found = overlay.resolve_file("persona")
    if found is None:
        return PersonaPayload(content="")
    return PersonaPayload(content=found.path.read_text(encoding="utf-8"))
