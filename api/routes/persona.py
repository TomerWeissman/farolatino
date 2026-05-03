"""GET / PUT /api/persona — read/write FAROAI.md (the system-prompt memory).

Editable from the UI's debug panel so the team can tweak FaroAI's voice
without dropping into a code editor.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from api.schemas import PersonaPayload

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PERSONA_PATH = PROJECT_ROOT / "FAROAI.md"

router = APIRouter()


@router.get("/persona", response_model=PersonaPayload)
def get_persona() -> PersonaPayload:
    if not PERSONA_PATH.exists():
        return PersonaPayload(content="")
    return PersonaPayload(content=PERSONA_PATH.read_text(encoding="utf-8"))


@router.put("/persona", response_model=PersonaPayload)
def put_persona(payload: PersonaPayload) -> PersonaPayload:
    # Refuse pathological writes (someone PUT-ing megabytes by accident).
    if len(payload.content) > 200_000:
        raise HTTPException(status_code=413, detail="persona content >200kB; refusing to write")
    PERSONA_PATH.write_text(payload.content, encoding="utf-8")
    return payload
