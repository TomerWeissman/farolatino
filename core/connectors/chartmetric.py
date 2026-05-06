"""Chartmetric connector.

Wraps the existing ``mcp_server/tools/chartmetric_*.py`` modules in
the V2 connector protocol. The actual API logic + token cache stays
where it is — this module is just registration glue + status probe.
"""
from __future__ import annotations

import os
from typing import Callable

from core.connectors import ConnectionStatusInfo, register


class ChartmetricConnector:
    name = "Chartmetric"
    slug = "chartmetric"
    env_vars = ["CHARTMETRIC_REFRESH_TOKEN"]
    docs_url = "https://chartmetric.com/api"

    def status(self) -> ConnectionStatusInfo:
        if not os.getenv("CHARTMETRIC_REFRESH_TOKEN"):
            return ConnectionStatusInfo(
                status="missing_creds",
                detail="CHARTMETRIC_REFRESH_TOKEN not set",
            )
        try:
            # Lazy import so module-load doesn't trigger network.
            from mcp_server.tools.chartmetric_auth import get_access_token
            token = get_access_token()
            if token:
                return ConnectionStatusInfo(status="ok", detail="Token refresh succeeded")
            return ConnectionStatusInfo(
                status="auth_failed",
                detail="Token endpoint returned empty",
            )
        except ConnectionError as exc:
            msg = str(exc)
            cls = "auth_failed" if "401" in msg or "auth" in msg.lower() else "network_error"
            return ConnectionStatusInfo(status=cls, detail=msg[:200])
        except Exception as exc:  # pragma: no cover — defensive
            return ConnectionStatusInfo(
                status="unknown",
                detail=f"{type(exc).__name__}: {str(exc)[:200]}",
            )

    def reset_cache(self) -> None:
        from mcp_server.tools import chartmetric_auth
        chartmetric_auth._access_token = None
        chartmetric_auth._token_expires_at = 0.0

    def tools(self) -> dict[str, Callable]:
        # Tools are still registered in core.llm.tool_dispatch._REGISTRY
        # for now (explicit list there is well-tested). Returning {}
        # here is fine — connector dispatch via this method is a
        # forward-compat hook for when we want to drop the static
        # registry in tool_dispatch.
        return {}


register(ChartmetricConnector())
