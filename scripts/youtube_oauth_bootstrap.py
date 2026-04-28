"""One-time YouTube OAuth bootstrap.

Opens a browser, runs the installed-app OAuth flow against the client JSON,
and writes the resulting credentials (including the refresh token) to
`config/youtube_oauth_token.json`. After this runs once, the app can refresh
access tokens non-interactively.

Usage:
    source venv/bin/activate
    python scripts/youtube_oauth_bootstrap.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLIENT_SECRETS = PROJECT_ROOT / "config" / "youtube_oauth_client.json"
TOKEN_FILE = PROJECT_ROOT / "config" / "youtube_oauth_token.json"


def main() -> int:
    if not CLIENT_SECRETS.exists():
        print(f"Missing {CLIENT_SECRETS}", file=sys.stderr)
        return 1

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS), SCOPES)
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

    TOKEN_FILE.write_text(creds.to_json())
    print(f"Saved credentials to {TOKEN_FILE}")

    # Sanity check: hit a lightweight endpoint to confirm the token works.
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    resp = youtube.channels().list(part="snippet", mine=True).execute()
    items = resp.get("items", [])
    if items:
        ch = items[0]["snippet"]
        print(f"Authorized channel: {ch.get('title')} ({items[0]['id']})")
    else:
        print("Token works, but this Google account has no YouTube channel attached.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
