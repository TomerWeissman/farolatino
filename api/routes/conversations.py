"""Conversation persistence — replaces browser-localStorage storage.

In v0.5.2 chat history lived in ``window.localStorage`` under the key
``faroai.conversations.v1``. The pywebview/WebKit data store wasn't
surviving py2app rebuilds across version bumps, so every update wiped
the user's history. v0.5.3 moves storage to a JSON file in the
per-user config dir (``core.storage``) accessed through these routes.

Endpoints:

    GET    /api/conversations           — list all (newest-first by updatedAt)
    PUT    /api/conversations/{id}      — upsert one
    DELETE /api/conversations/{id}      — remove one
    POST   /api/conversations/migrate   — one-time bulk import from localStorage
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core import storage

router = APIRouter()


class ConversationsResponse(BaseModel):
    conversations: list[dict[str, Any]]


class MigrateRequest(BaseModel):
    conversations: list[dict[str, Any]] = Field(default_factory=list)


class MigrateResponse(BaseModel):
    imported: int


@router.get("/conversations", response_model=ConversationsResponse)
def list_conversations() -> ConversationsResponse:
    convs = storage.load_conversations()
    # Newest-first by updatedAt (the frontend used to sort client-side;
    # doing it here keeps the surface area smaller and matches the old
    # ordering exactly).
    items = sorted(
        convs.values(),
        key=lambda c: c.get("updatedAt", 0),
        reverse=True,
    )
    return ConversationsResponse(conversations=items)


@router.put("/conversations/{cid}")
def upsert_conversation(cid: str, body: dict[str, Any]) -> dict[str, Any]:
    """Create or update a single conversation. Body IS the conversation."""
    if body.get("id") != cid:
        raise HTTPException(
            status_code=400,
            detail=f"path id {cid!r} does not match body.id {body.get('id')!r}",
        )
    try:
        storage.save_conversation(body)
    except (ValueError, OSError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return body


@router.delete("/conversations/{cid}")
def remove_conversation(cid: str) -> dict[str, bool]:
    existed = storage.delete_conversation(cid)
    return {"deleted": existed}


@router.post("/conversations/migrate", response_model=MigrateResponse)
def migrate_conversations(req: MigrateRequest) -> MigrateResponse:
    """Bulk-import from the browser's localStorage on first launch
    after the v0.5.3 upgrade. The frontend reads the legacy
    ``faroai.conversations.v1`` blob, POSTs it here once, and then
    clears localStorage. Safe to re-run — it overwrites whatever's
    on disk, but the frontend only calls it when the server-side
    store is empty AND localStorage has entries."""
    count = storage.replace_all_conversations(req.conversations)
    return MigrateResponse(imported=count)
