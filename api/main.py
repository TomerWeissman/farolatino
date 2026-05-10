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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# V2: credentials live under ~/Library/Application Support/FaroAI/
# (mac), %APPDATA%\FaroAI\ (win), or ~/.config/faroai/ (linux). On
# first boot we migrate any V1 project-root .env into the new home so
# existing local installs aren't broken. See core/paths.py for the
# rationale (bundled apps need a writable, persistent user-data dir).
from core.paths import load_credentials, resource_path  # noqa: E402

load_credentials()

from api.routes import chat, connections, env, evaluate, files, health, onboarding, persona, preferences, runs, skills, updates  # noqa: E402

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
app.include_router(files.router, prefix="/api", tags=["files"])
app.include_router(connections.router, prefix="/api", tags=["meta"])
app.include_router(env.router, prefix="/api", tags=["meta"])
app.include_router(updates.router, prefix="/api", tags=["meta"])
app.include_router(onboarding.router, prefix="/api", tags=["meta"])
app.include_router(evaluate.router, prefix="/api", tags=["chat"])
app.include_router(preferences.router, prefix="/api", tags=["meta"])


# Static SPA mount. Only attached if `web/out/` exists, so a fresh clone
# without a frontend build still boots (the API alone is usable).
#
# Cache strategy: HTML must be re-fetched every load (the hashed JS/CSS
# references inside change with each build); static asset files have
# content-hashed names so they're safe to cache forever. Without this, a
# user who upgraded the repo would see their browser serve a stale
# index.html that points at JS bundles that no longer exist on disk —
# the chat would silently fail to mount and look like the page is hung.
class _CachingStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        # `path` is the relative URL within the mount: "" for "/", else
        # things like "index.html" or "_next/static/.../foo.css".
        # When html=True and the request hits a directory (like "/"),
        # Starlette serves the inner index.html but get_response is still
        # called with the raw "" path — so we check the resolved
        # content-type rather than the URL path.
        ctype = resp.headers.get("content-type", "")
        if "html" in ctype:
            # HTML must always be re-fetched: it references hashed JS/CSS
            # assets that change on each frontend rebuild. A stale cached
            # index.html points at JS bundles that no longer exist.
            resp.headers["cache-control"] = "no-store, must-revalidate"
        elif path.startswith("_next/static/") or path.startswith("/_next/static/"):
            # Hashed asset filenames are content-addressed → safe forever.
            resp.headers["cache-control"] = "public, max-age=31536000, immutable"
        return resp


def _resolve_web_out() -> Path:
    """Pick the active web/out directory.

    Prefers the user code overlay (``~/Library/.../FaroAI/code/web/out``)
    so a code-only update can ship a new frontend without a full
    reinstall. Falls back to the bundled web/out when no overlay is
    active or when the overlay is missing the build output. Defensive
    against any error — the bundled path is always a safe fallback.
    """
    try:
        from core.paths import app_config_dir
        overlay = app_config_dir() / "code" / "web" / "out"
        if (overlay / "index.html").is_file():
            return overlay
    except Exception:
        pass
    return resource_path("web/out")


_WEB_OUT = _resolve_web_out()
if _WEB_OUT.is_dir():
    app.mount(
        "/",
        _CachingStaticFiles(directory=str(_WEB_OUT), html=True),
        name="spa",
    )
