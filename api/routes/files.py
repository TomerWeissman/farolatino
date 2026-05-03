"""GET / PUT /api/files/* — browse and edit calibration / cache / internal files.

Three categories the Files page surfaces:

- **calibration** — YAMLs in `config/` and `config/profiles/`. Editable.
  PUT validates the YAML parses cleanly before writing so a typo can't
  brick the MCP server.
- **cache** — per-artist Chartmetric cache under `data/cache/{cm_id}/`.
  Read-only; for diagnostic ("why did this artist score X?").
- **internal** — FaroLatino's private royalty data under `data/internal/`.
  Read-only.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
CACHE_DIR = PROJECT_ROOT / "data" / "cache"
INTERNAL_DIR = PROJECT_ROOT / "data" / "internal"

router = APIRouter()


# ─── Schemas (kept local — not reused outside this module) ───────────────


class CalibrationFile(BaseModel):
    name: str           # relative path within config/, e.g. "stream_multipliers.yaml" or "profiles/default.yaml"
    size: int
    mtime: float        # epoch seconds
    content: str        # raw YAML text


class CalibrationUpdate(BaseModel):
    content: str


class CacheArtistRow(BaseModel):
    cm_id: int
    name: str | None        # from cached metadata.json if present
    country_code: str | None
    n_endpoints: int        # how many cache files we have for this artist
    last_modified: float    # most-recent mtime across the cached files


class InternalFile(BaseModel):
    name: str
    size: int
    mtime: float


# ─── Path-traversal safety ───────────────────────────────────────────────


def _safe_join(base: Path, rel: str) -> Path:
    """Resolve `base / rel` and refuse if it escapes `base`. Caller can
    pass slashes for nested paths (e.g. profiles/default.yaml)."""
    candidate = (base / rel).resolve()
    base_resolved = base.resolve()
    try:
        candidate.relative_to(base_resolved)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="path escapes the allowed root") from exc
    return candidate


# ─── Calibration ─────────────────────────────────────────────────────────


@router.get("/files/calibration", response_model=list[CalibrationFile])
def list_calibration() -> list[CalibrationFile]:
    if not CONFIG_DIR.exists():
        return []
    out: list[CalibrationFile] = []
    # Top-level YAMLs.
    for p in sorted(CONFIG_DIR.glob("*.yaml")) + sorted(CONFIG_DIR.glob("*.yml")):
        out.append(_calibration_file_from_path(p, p.name))
    # profiles/*.yaml as nested entries (so the UI can show them grouped).
    profiles_dir = CONFIG_DIR / "profiles"
    if profiles_dir.is_dir():
        for p in sorted(profiles_dir.glob("*.yaml")) + sorted(profiles_dir.glob("*.yml")):
            out.append(_calibration_file_from_path(p, f"profiles/{p.name}"))
    return out


@router.put("/files/calibration/{name:path}", response_model=CalibrationFile)
def put_calibration(name: str, payload: CalibrationUpdate) -> CalibrationFile:
    target = _safe_join(CONFIG_DIR, name)
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"calibration file '{name}' not found")
    if target.suffix.lower() not in {".yaml", ".yml"}:
        raise HTTPException(status_code=400, detail="only YAML files are editable here")
    if len(payload.content) > 500_000:
        raise HTTPException(status_code=413, detail="file >500kB; refusing to write")
    # Validate YAML parses before we commit anything.
    try:
        yaml.safe_load(payload.content)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=400, detail=f"YAML parse error: {exc}") from exc
    target.write_text(payload.content, encoding="utf-8")
    return _calibration_file_from_path(target, name)


def _calibration_file_from_path(p: Path, rel_name: str) -> CalibrationFile:
    return CalibrationFile(
        name=rel_name,
        size=p.stat().st_size,
        mtime=p.stat().st_mtime,
        content=p.read_text(encoding="utf-8"),
    )


# ─── Cached artists ──────────────────────────────────────────────────────


@router.get("/files/cache", response_model=list[CacheArtistRow])
def list_cached_artists() -> list[CacheArtistRow]:
    """List all per-artist cache directories. Reads metadata.json (if
    present) for the friendly name + country."""
    if not CACHE_DIR.exists():
        return []
    rows: list[CacheArtistRow] = []
    for d in sorted(CACHE_DIR.iterdir()):
        if not d.is_dir() or not d.name.isdigit():
            continue
        cm_id = int(d.name)
        metadata = _read_metadata(d)
        endpoint_files = list(d.glob("*.json"))
        last_mod = max((f.stat().st_mtime for f in endpoint_files), default=0.0)
        rows.append(
            CacheArtistRow(
                cm_id=cm_id,
                name=(metadata or {}).get("name"),
                country_code=((metadata or {}).get("code2") or "").upper() or None,
                n_endpoints=len(endpoint_files),
                last_modified=last_mod,
            )
        )
    # newest cache first — most useful when diagnosing recent runs
    rows.sort(key=lambda r: r.last_modified, reverse=True)
    return rows


@router.get("/files/cache/{cm_id}")
def list_artist_endpoints(cm_id: int) -> list[dict]:
    """List the cached endpoints for one artist."""
    d = CACHE_DIR / str(cm_id)
    if not d.is_dir():
        raise HTTPException(status_code=404, detail=f"no cache for cm_id={cm_id}")
    return [
        {
            "endpoint": f.stem,
            "size": f.stat().st_size,
            "mtime": f.stat().st_mtime,
        }
        for f in sorted(d.glob("*.json"))
    ]


@router.get("/files/cache/{cm_id}/{endpoint}")
def get_cached_endpoint(cm_id: int, endpoint: str) -> dict:
    """Return raw cached JSON for one endpoint. Read-only — for the
    'why did this artist score X?' diagnostic flow."""
    d = CACHE_DIR / str(cm_id)
    safe = endpoint.replace("/", "").replace("..", "")  # no traversal
    f = d / f"{safe}.json"
    if not f.is_file():
        raise HTTPException(status_code=404, detail=f"no cached '{endpoint}' for cm_id={cm_id}")
    try:
        return {
            "cm_id": cm_id,
            "endpoint": safe,
            "mtime_iso": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).isoformat(),
            "data": json.loads(f.read_text(encoding="utf-8")),
        }
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"cached file is not valid JSON: {exc}") from exc


def _read_metadata(artist_dir: Path) -> dict | None:
    f = artist_dir / "metadata.json"
    if not f.is_file():
        return None
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
        # data_cache wraps cached payloads as {fetched_at: ..., data: {...}}.
        return d.get("data") or d
    except (json.JSONDecodeError, OSError):
        return None


# ─── Internal data ───────────────────────────────────────────────────────


@router.get("/files/internal", response_model=list[InternalFile])
def list_internal() -> list[InternalFile]:
    if not INTERNAL_DIR.exists():
        return []
    rows = []
    for p in sorted(INTERNAL_DIR.iterdir()):
        if p.is_file() and not p.name.startswith("."):
            rows.append(InternalFile(name=p.name, size=p.stat().st_size, mtime=p.stat().st_mtime))
    return rows


@router.get("/files/internal/{name}")
def get_internal_file(name: str) -> dict:
    """Read an internal file. Returns parsed JSON when the file is .json,
    otherwise raw text. Refuses files larger than 5MB to keep the
    browser responsive."""
    target = _safe_join(INTERNAL_DIR, name)
    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"internal file '{name}' not found")
    if target.stat().st_size > 5_000_000:
        raise HTTPException(
            status_code=413,
            detail=f"file too big ({target.stat().st_size} bytes) — open with a code editor instead",
        )
    text = target.read_text(encoding="utf-8")
    if target.suffix.lower() == ".json":
        try:
            return {"name": name, "kind": "json", "content": json.loads(text)}
        except json.JSONDecodeError:
            pass
    return {"name": name, "kind": "text", "content": text}
