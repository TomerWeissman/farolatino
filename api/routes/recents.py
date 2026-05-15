"""Recent-evals + recent-compares persistence.

Companion to ``api/routes/conversations.py`` — same motivation (move
storage from browser localStorage to disk so updates don't wipe it).
The frontend's ``web/lib/recents.ts`` was the v0.5.2 source of truth;
v0.5.3 reads from these endpoints instead.

Two independent lists, each capped at 5:

    GET    /api/recents             — { evals: [...], compares: [...] }
    POST   /api/recents/eval        — push a new eval (dedup by cm_id)
    POST   /api/recents/compare     — push a new compare (dedup by pair)
    DELETE /api/recents/eval        — clear all evals
    DELETE /api/recents/compare     — clear all compares
    POST   /api/recents/migrate     — one-time bulk import from localStorage
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core import storage

router = APIRouter()


class RecentEval(BaseModel):
    name: str
    cm_id: int
    evaluated_at: int  # epoch ms (matches frontend Number)


class RecentCompare(BaseModel):
    artist_a: str
    cm_id_a: int
    artist_b: str
    cm_id_b: int
    compared_at: int


class RecentsResponse(BaseModel):
    evals: list[RecentEval]
    compares: list[RecentCompare]


class MigrateRequest(BaseModel):
    evals: list[RecentEval] = Field(default_factory=list)
    compares: list[RecentCompare] = Field(default_factory=list)


class MigrateResponse(BaseModel):
    imported_evals: int
    imported_compares: int


@router.get("/recents", response_model=RecentsResponse)
def get_recents() -> RecentsResponse:
    return RecentsResponse(
        evals=[RecentEval(**e) for e in storage.load_recent_evals()],
        compares=[RecentCompare(**c) for c in storage.load_recent_compares()],
    )


@router.post("/recents/eval", response_model=list[RecentEval])
def push_eval(item: RecentEval) -> list[RecentEval]:
    try:
        updated = storage.push_recent_eval(item.model_dump())
    except (ValueError, OSError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return [RecentEval(**e) for e in updated]


@router.post("/recents/compare", response_model=list[RecentCompare])
def push_compare(item: RecentCompare) -> list[RecentCompare]:
    try:
        updated = storage.push_recent_compare(item.model_dump())
    except (ValueError, OSError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return [RecentCompare(**c) for c in updated]


@router.delete("/recents/eval")
def clear_evals() -> dict[str, bool]:
    storage.clear_recent_evals()
    return {"cleared": True}


@router.delete("/recents/compare")
def clear_compares() -> dict[str, bool]:
    storage.clear_recent_compares()
    return {"cleared": True}


@router.post("/recents/migrate", response_model=MigrateResponse)
def migrate_recents(req: MigrateRequest) -> MigrateResponse:
    e, c = storage.replace_all_recents(
        [item.model_dump() for item in req.evals],
        [item.model_dump() for item in req.compares],
    )
    return MigrateResponse(imported_evals=e, imported_compares=c)
