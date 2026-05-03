"""FastAPI entry point — `uvicorn api.main:app`.

Single process serves:
- /api/*  → JSON + SSE endpoints
- /      → web/out/ (pre-built Next.js static export)

In dev mode, we bring up only the API; the Next.js dev server runs
separately on :3000 and proxies /api/* back to us via next.config rewrites.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# .env BEFORE importing anything that reads env vars (chartmetric, etc.).
load_dotenv(PROJECT_ROOT / ".env")

from api.routes import chat, health, persona, runs, skills  # noqa: E402

app = FastAPI(
    title="FaroAI",
    description="A&R assistant backend for FaroLatino — wraps the FaroLatino MCP server.",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)

# CORS for dev mode (Next.js on :3000 → FastAPI on :8000). In production
# the static frontend is served by us directly so same-origin applies and
# CORS is a no-op.
_DEV_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_DEV_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes — all mounted under /api so they don't collide with the
# static frontend at /.
app.include_router(health.router, prefix="/api", tags=["meta"])
app.include_router(skills.router, prefix="/api", tags=["chat"])
app.include_router(persona.router, prefix="/api", tags=["chat"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(runs.router, prefix="/api", tags=["runs"])


# Static SPA mount. Only attached if `web/out/` exists, so a fresh clone
# without a frontend build still boots (the API alone is usable).
_WEB_OUT = PROJECT_ROOT / "web" / "out"
if _WEB_OUT.is_dir():
    app.mount(
        "/",
        StaticFiles(directory=str(_WEB_OUT), html=True),
        name="spa",
    )
