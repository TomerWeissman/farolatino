"""Spotify connector. Wraps mcp_server/tools/spotify_* in the V2 protocol."""
from __future__ import annotations

import os
from typing import Callable

from core.connectors import ConnectionStatusInfo, register


class SpotifyConnector:
    name = "Spotify"
    slug = "spotify"
    env_vars = ["SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"]
    docs_url = "https://developer.spotify.com/dashboard"

    def status(self) -> ConnectionStatusInfo:
        if not os.getenv("SPOTIFY_CLIENT_ID") or not os.getenv("SPOTIFY_CLIENT_SECRET"):
            return ConnectionStatusInfo(
                status="missing_creds",
                detail="SPOTIFY_CLIENT_ID and/or SPOTIFY_CLIENT_SECRET not set",
            )
        try:
            from mcp_server.tools.spotify_auth import api_get, get_access_token
            get_access_token()
            # Spotify's Nov 2024 policy gates most reads behind Premium
            # on the app owner's account, so a token grant alone isn't
            # proof of usability. Exercise an actual read.
            api_get("/search", params={"q": "test", "type": "artist", "limit": 1})
            return ConnectionStatusInfo(
                status="ok",
                detail="Client Credentials flow + read OK",
            )
        except ConnectionError as exc:
            msg = str(exc)
            if "premium" in msg.lower() or "Active premium" in msg:
                return ConnectionStatusInfo(
                    status="quota_required",
                    detail=(
                        "Spotify requires the app owner to have Premium "
                        "(Nov 2024+ policy). Upgrade the developer account "
                        "that owns this app."
                    ),
                )
            cls = "auth_failed" if "401" in msg or "403" in msg else "network_error"
            return ConnectionStatusInfo(status=cls, detail=msg[:240])
        except Exception as exc:  # pragma: no cover
            return ConnectionStatusInfo(
                status="unknown",
                detail=f"{type(exc).__name__}: {str(exc)[:200]}",
            )

    def reset_cache(self) -> None:
        from mcp_server.tools import spotify_auth
        spotify_auth._access_token = None
        spotify_auth._token_expires_at = 0.0

    def tools(self) -> dict[str, Callable]:
        return {}


register(SpotifyConnector())
