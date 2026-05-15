"""JSON-file-backed stores for chat conversations + recent eval/compare lists.

Replaces v0.5.2's browser-localStorage persistence with disk storage
under the per-user config dir. Motivation: pywebview's WebKit data
store wasn't surviving py2app rebuilds across version bumps — every
"Check for updates" → restart wiped the user's chat history and recent
evaluations even though the modal promised it wouldn't. Disk-side
storage takes that whole class of failure off the table.

Layout (mac shown; Win/Linux equivalent under app_config_dir()):

    ~/Library/Application Support/FaroAI/data/
        conversations.json   # { conversations: { id: Conversation, ... } }
        recents.json         # { evals: [...], compares: [...] }

Both files are written atomically (tmp → os.replace) so a crash mid-
write can't corrupt the live blob. Read-then-write is the only mode —
no diffing, no incremental updates. At the scale of one user with a
few dozen conversations of a few dozen turns each, this is a few KB
to a few hundred KB; rewriting on each save is fine.

Concurrency: a process-local threading.Lock guards each store so the
FastAPI thread pool can't race writers. There's no inter-process lock
because FaroAI runs as a single uvicorn process per user.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from core.paths import app_config_dir


_RECENT_LIMIT = 5  # matches the v0.5.2 frontend cap

# v0.5.3 — FIFO cap on conversations. Above this, the oldest by
# updatedAt is dropped on each save. The just-saved conversation
# always has the freshest updatedAt (the frontend sets it to Date.now()
# on every save), so it's structurally safe — eviction can only ever
# touch older entries. A user wanting to keep an old chat just needs
# to open it and send one more message to refresh its timestamp.
_MAX_CONVERSATIONS = 50


def _data_dir() -> Path:
    """Per-user data directory. Created on first use."""
    d = app_config_dir() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def conversations_path() -> Path:
    return _data_dir() / "conversations.json"


def recents_path() -> Path:
    return _data_dir() / "recents.json"


# ─── Generic atomic JSON I/O ────────────────────────────────────────────


def _read_json(path: Path, default: Any) -> Any:
    """Read a JSON file or return ``default``.

    Tolerant of: missing file, empty file, malformed JSON. In every
    failure mode we hand back ``default`` rather than crashing — the
    UI's "I have zero conversations" empty state is the right
    behavior when storage is corrupt, not a 500.
    """
    if not path.is_file():
        return default
    try:
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            return default
        return json.loads(text)
    except (OSError, json.JSONDecodeError):
        return default


def _write_json_atomic(path: Path, payload: Any) -> None:
    """Write JSON via tmp-file-then-rename so a crash can't corrupt the blob."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


# ─── Conversations ──────────────────────────────────────────────────────

_conv_lock = threading.Lock()


def load_conversations() -> dict[str, dict]:
    """Return the conversation map ``{id: conversation_dict}``."""
    blob = _read_json(conversations_path(), {"conversations": {}})
    if not isinstance(blob, dict):
        return {}
    convs = blob.get("conversations")
    if not isinstance(convs, dict):
        return {}
    # Sanity-filter entries that don't look like Conversation objects.
    return {k: v for k, v in convs.items() if isinstance(v, dict) and "id" in v}


def save_conversation(conversation: dict) -> None:
    """Insert or update a single conversation. Trims to _MAX_CONVERSATIONS."""
    cid = conversation.get("id")
    if not isinstance(cid, str) or not cid:
        raise ValueError("conversation.id must be a non-empty string")
    with _conv_lock:
        convs = load_conversations()
        convs[cid] = conversation
        convs = _enforce_cap(convs)
        _write_json_atomic(conversations_path(), {"conversations": convs})


def _enforce_cap(convs: dict[str, dict]) -> dict[str, dict]:
    """Keep at most _MAX_CONVERSATIONS, dropping oldest by updatedAt.

    Entries missing updatedAt sort as 0 (oldest), so a malformed record
    is the first to be evicted — defensive default that matches what
    the frontend's groupByRecency does for the same field.
    """
    if len(convs) <= _MAX_CONVERSATIONS:
        return convs
    ordered = sorted(
        convs.items(),
        key=lambda item: item[1].get("updatedAt", 0),
        reverse=True,
    )
    return dict(ordered[:_MAX_CONVERSATIONS])


def delete_conversation(cid: str) -> bool:
    """Remove a conversation. Returns True if it existed."""
    with _conv_lock:
        convs = load_conversations()
        if cid not in convs:
            return False
        del convs[cid]
        _write_json_atomic(conversations_path(), {"conversations": convs})
        return True


def replace_all_conversations(items: list[dict]) -> int:
    """Bulk-import (used by the one-time localStorage → server migration).

    Replaces the entire conversation set. Returns the count imported
    AFTER the _MAX_CONVERSATIONS cap is applied — a user migrating in
    from a localStorage blob with 100 chats will see only the 50 most
    recently updated on the server side; the rest are dropped silently
    (which matches the rule going forward).

    Skipped items: entries missing an ``id``, or where the same ``id``
    appears twice in the input (last-write-wins).
    """
    with _conv_lock:
        out: dict[str, dict] = {}
        for c in items:
            if isinstance(c, dict) and isinstance(c.get("id"), str):
                out[c["id"]] = c
        out = _enforce_cap(out)
        _write_json_atomic(conversations_path(), {"conversations": out})
        return len(out)


# ─── Recents (evals + compares) ─────────────────────────────────────────

_recents_lock = threading.Lock()


def _load_recents_blob() -> dict[str, list]:
    blob = _read_json(recents_path(), {"evals": [], "compares": []})
    if not isinstance(blob, dict):
        return {"evals": [], "compares": []}
    evals = blob.get("evals") if isinstance(blob.get("evals"), list) else []
    compares = blob.get("compares") if isinstance(blob.get("compares"), list) else []
    return {"evals": evals, "compares": compares}


def load_recent_evals() -> list[dict]:
    return _load_recents_blob()["evals"][:_RECENT_LIMIT]


def load_recent_compares() -> list[dict]:
    return _load_recents_blob()["compares"][:_RECENT_LIMIT]


def push_recent_eval(item: dict) -> list[dict]:
    """Prepend an eval, dedupe by ``cm_id``, cap at the recent limit."""
    cm_id = item.get("cm_id")
    if cm_id is None:
        raise ValueError("recent eval missing cm_id")
    with _recents_lock:
        blob = _load_recents_blob()
        filtered = [r for r in blob["evals"] if r.get("cm_id") != cm_id]
        blob["evals"] = ([item] + filtered)[:_RECENT_LIMIT]
        _write_json_atomic(recents_path(), blob)
        return blob["evals"]


def push_recent_compare(item: dict) -> list[dict]:
    """Prepend a compare, dedupe by ordered (cm_id_a, cm_id_b) pair."""
    a = item.get("cm_id_a")
    b = item.get("cm_id_b")
    if a is None or b is None:
        raise ValueError("recent compare missing cm_id_a/cm_id_b")
    with _recents_lock:
        blob = _load_recents_blob()
        filtered = [
            r for r in blob["compares"]
            if not (r.get("cm_id_a") == a and r.get("cm_id_b") == b)
        ]
        blob["compares"] = ([item] + filtered)[:_RECENT_LIMIT]
        _write_json_atomic(recents_path(), blob)
        return blob["compares"]


def clear_recent_evals() -> None:
    with _recents_lock:
        blob = _load_recents_blob()
        blob["evals"] = []
        _write_json_atomic(recents_path(), blob)


def clear_recent_compares() -> None:
    with _recents_lock:
        blob = _load_recents_blob()
        blob["compares"] = []
        _write_json_atomic(recents_path(), blob)


def replace_all_recents(evals: list[dict], compares: list[dict]) -> tuple[int, int]:
    """Bulk-import for the localStorage migration."""
    with _recents_lock:
        e = [item for item in evals if isinstance(item, dict) and "cm_id" in item][:_RECENT_LIMIT]
        c = [
            item for item in compares
            if isinstance(item, dict) and "cm_id_a" in item and "cm_id_b" in item
        ][:_RECENT_LIMIT]
        _write_json_atomic(recents_path(), {"evals": e, "compares": c})
        return len(e), len(c)
