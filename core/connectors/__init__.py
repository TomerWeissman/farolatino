"""Connector plugin pattern.

A "connector" is a self-contained data source FaroAI can talk to:
Chartmetric, Spotify, YouTube, and (later) Apple Music, TikTok, your
own internal CRM. Each connector lives in its own module under this
package and registers itself at import time.

Adding a new connector becomes one file: drop ``my_provider.py`` in
this directory, define a class that implements the ``Connector``
protocol, instantiate it. The connections page picks it up
automatically. No edits to ``api/routes/connections.py``,
``api/routes/env.py``, or any other central registry — those modules
walk this package's registry instead of hardcoding each provider.

The LLM provider (Anthropic / OpenAI / Gemini) is intentionally NOT
a connector — it's a different concept (the brain, not a data source)
and lives under ``core/llm/`` with its own provider abstraction.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Protocol, runtime_checkable

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConnectionStatusInfo:
    """What a connector reports when asked how it's doing.

    Mirrors ``api.routes.connections.ConnectionStatus`` but lives at
    the core layer so connector code doesn't have to import from
    ``api/`` (would create a circular dep).

    ``status`` is one of:
      - ``"ok"``                : authenticated + reachable
      - ``"missing_creds"``     : env vars not set
      - ``"auth_failed"``       : creds set but rejected
      - ``"quota_required"``    : creds work but provider needs paid tier
      - ``"network_error"``     : transient — retry helps
      - ``"unknown"``           : caught an exception we didn't classify
    """

    status: str
    detail: str | None = None


@runtime_checkable
class Connector(Protocol):
    """The shape every connector must implement."""

    name: str  # display name shown in Connections page (e.g. "Spotify")
    slug: str  # url-safe id (e.g. "spotify")
    env_vars: list[str]  # all env vars the user might need to set
    docs_url: str | None  # link surfaced on the Connections row

    def status(self) -> ConnectionStatusInfo:
        """Probe the provider; return a status enum + human-readable detail."""
        ...

    def reset_cache(self) -> None:
        """Drop any in-memory token cache. Called when env changes."""
        ...

    def tools(self) -> dict[str, Callable]:
        """Tool name → callable. Empty dict if the connector doesn't
        directly expose tools to the LLM (e.g. an auth-only module).
        """
        ...


@dataclass
class _Registry:
    """Process-global connector registry. Populated by import side
    effects when each module under ``core/connectors/`` is loaded.
    """

    by_slug: dict[str, Connector] = field(default_factory=dict)


_REGISTRY = _Registry()


def register(connector: Connector) -> None:
    """Add a connector to the global registry. Called by each
    connector module at import time. Idempotent on slug — re-registering
    replaces the previous entry, useful for hot-reload during dev.
    """
    if connector.slug in _REGISTRY.by_slug:
        log.debug("re-registering connector %s", connector.slug)
    _REGISTRY.by_slug[connector.slug] = connector


def list_connectors() -> list[Connector]:
    """All registered connectors, in insertion order so the Connections
    page row order is stable across reloads."""
    return list(_REGISTRY.by_slug.values())


def get_connector(slug: str) -> Connector | None:
    return _REGISTRY.by_slug.get(slug)


def all_env_vars() -> list[str]:
    """Union of every connector's env vars, deduplicated, in order."""
    seen: set[str] = set()
    out: list[str] = []
    for c in list_connectors():
        for v in c.env_vars:
            if v not in seen:
                seen.add(v)
                out.append(v)
    return out


def reset_all_caches() -> None:
    """Drop every connector's in-memory token cache. Called from
    ``api/routes/env._invalidate_caches`` after a PUT /api/env so a key
    swap takes effect on the next call.
    """
    for c in list_connectors():
        try:
            c.reset_cache()
        except Exception:
            log.exception("connector %s reset_cache() raised", c.slug)


# Side-effect imports: each connector module's top level calls
# ``register(...)``. Importing the package triggers those registrations.
# Listed explicitly (not auto-discovered via pkgutil) so Phase 6's
# py2app build sees them via static analysis.
from core.connectors import chartmetric as _chartmetric  # noqa: E402, F401
from core.connectors import spotify as _spotify  # noqa: E402, F401
from core.connectors import youtube as _youtube  # noqa: E402, F401
