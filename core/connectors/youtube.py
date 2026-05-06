"""YouTube connector. Wraps mcp_server/tools/youtube_* in the V2 protocol."""
from __future__ import annotations

import os
from typing import Callable

from core.connectors import ConnectionStatusInfo, register


class YouTubeConnector:
    name = "YouTube"
    slug = "youtube"
    # Two valid auth modes: API key (read-only public data) OR the OAuth
    # triple. We surface all four env vars so the user can pick whichever
    # is convenient — the inline editor in Connections shows them all.
    env_vars = [
        "YOUTUBE_API_KEY",
        "YOUTUBE_CLIENT_ID",
        "YOUTUBE_CLIENT_SECRET",
        "YOUTUBE_REFRESH_TOKEN",
    ]
    docs_url = "https://console.cloud.google.com/apis/library/youtube.googleapis.com"

    def status(self) -> ConnectionStatusInfo:
        has_oauth = all(
            os.getenv(k)
            for k in ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN")
        )
        has_api_key = bool(os.getenv("YOUTUBE_API_KEY"))
        if not has_oauth and not has_api_key:
            return ConnectionStatusInfo(
                status="missing_creds",
                detail=(
                    "Set YOUTUBE_API_KEY for read-only access, or the OAuth "
                    "triple (CLIENT_ID/CLIENT_SECRET/REFRESH_TOKEN) for "
                    "authenticated access."
                ),
            )
        try:
            from mcp_server.tools.youtube_auth import api_get
            api_get(
                "/search",
                params={"part": "snippet", "q": "test", "type": "channel", "maxResults": 1},
            )
            return ConnectionStatusInfo(
                status="ok",
                detail="OAuth + read OK" if has_oauth else "API key + read OK",
            )
        except ConnectionError as exc:
            return ConnectionStatusInfo(
                status="network_error",
                detail=str(exc)[:240],
            )
        except Exception as exc:
            msg = str(exc)
            if "expired or revoked" in msg or "invalid_grant" in msg:
                return ConnectionStatusInfo(
                    status="auth_failed",
                    detail=(
                        "Refresh token expired or revoked — re-run the OAuth "
                        "consent flow to mint a new refresh token."
                    ),
                )
            return ConnectionStatusInfo(
                status="unknown",
                detail=f"{type(exc).__name__}: {msg[:200]}",
            )

    def reset_cache(self) -> None:
        from mcp_server.tools import youtube_auth
        youtube_auth._access_token = None
        youtube_auth._token_expires_at = 0.0

    def tools(self) -> dict[str, Callable]:
        return {}


register(YouTubeConnector())
