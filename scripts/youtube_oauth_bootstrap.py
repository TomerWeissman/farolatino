"""One-time YouTube OAuth bootstrap.

Reads YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET from .env, opens a browser
for the installed-app OAuth flow, and prints the resulting refresh token.
Paste that token into .env as YOUTUBE_REFRESH_TOKEN; afterwards the app can
mint access tokens non-interactively (same pattern as Chartmetric).

Usage:
    source venv/bin/activate
    python scripts/youtube_oauth_bootstrap.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]


def main() -> int:
    client_id = os.getenv("YOUTUBE_CLIENT_ID")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
    if not client_id or not client_secret:
        print(
            "YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET must be set in .env",
            file=sys.stderr,
        )
        return 1

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(
        port=0,
        prompt="consent",
        authorization_prompt_message=(
            "Opening your browser to authorize YouTube access.\n"
            "Sign in as dsp.farolatino@gmail.com and approve the scopes.\n"
            "URL: {url}"
        ),
        success_message="Authorization complete — you can close this tab.",
    )

    if not creds.refresh_token:
        print("OAuth completed but no refresh token returned.", file=sys.stderr)
        return 1

    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    resp = youtube.channels().list(part="snippet", mine=True).execute()
    items = resp.get("items", [])
    if items:
        ch = items[0]["snippet"]
        print(f"\nAuthorized channel: {ch.get('title')} ({items[0]['id']})")
    else:
        print("\nToken works, but this Google account has no YouTube channel attached.")

    print("\nAdd the following line to .env:\n")
    print(f"YOUTUBE_REFRESH_TOKEN={creds.refresh_token}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
