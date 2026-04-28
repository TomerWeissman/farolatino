"""Verification harness for the FaroLatino data-collection layer.

Exercises `search_artists` and `get_artist_data` end-to-end against live
Chartmetric, dumps the full ArtistProfile, and prints a coverage summary
(which fields are populated vs. empty, plus `data_completeness`).

Usage:
    source venv/bin/activate
    python scripts/collect_artist.py "Feid"
    python scripts/collect_artist.py 206557          # direct Chartmetric ID
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from mcp_server.tools.chartmetric_artist import (  # noqa: E402
    _COMPLETENESS_FIELDS,
    _is_populated,
    get_artist_data,
)
from mcp_server.tools.chartmetric_search import search_artists  # noqa: E402

DUMP_DIR = PROJECT_ROOT / "data" / "cache"


def _resolve_artist(arg: str) -> int | None:
    """Return a Chartmetric artist ID, either parsed from arg or chosen
    interactively from search results."""
    if arg.isdigit():
        return int(arg)

    print(f"Searching Chartmetric for: {arg!r}")
    result = search_artists(arg, limit=10)
    artists = result.get("artists", [])
    if not artists:
        print(f"No artists matched {arg!r}")
        return None

    top = artists[:3]
    print(f"\nTop {len(top)} matches:")
    for i, a in enumerate(top, 1):
        listeners = a.get("sp_monthly_listeners") or 0
        followers = a.get("sp_followers") or 0
        print(
            f"  [{i}] {a.get('name')}  "
            f"(cm_id={a.get('cm_id')}, "
            f"sp_followers={followers:,}, "
            f"sp_monthly_listeners={listeners:,})"
        )

    choice = input("\nPick [1-3] (default 1): ").strip() or "1"
    try:
        idx = int(choice) - 1
        return top[idx]["cm_id"]
    except (ValueError, IndexError):
        print(f"Invalid choice: {choice}")
        return None


def _summarize_coverage(profile: dict) -> None:
    """Print which required fields are populated and list any zero/empty ones."""
    missing = []
    populated = []
    for key, kind in _COMPLETENESS_FIELDS:
        if _is_populated(profile.get(key), kind):
            populated.append(key)
        else:
            missing.append(key)

    print("\n=== Coverage summary ===")
    print(f"data_completeness: {profile.get('data_completeness')}")
    print(f"populated ({len(populated)}/{len(_COMPLETENESS_FIELDS)}): {', '.join(populated)}")
    if missing:
        print(f"missing/empty: {', '.join(missing)}")
    else:
        print("missing/empty: (none)")


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/collect_artist.py '<artist name or cm_id>'")
        return 2

    cm_id = _resolve_artist(sys.argv[1])
    if cm_id is None:
        return 1

    print(f"\nFetching artist data for cm_id={cm_id} (cache disabled)...")
    start = time.monotonic()
    try:
        profile = get_artist_data(cm_id, use_cache=False)
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    elapsed = time.monotonic() - start
    print(f"Done in {elapsed:.1f}s")

    DUMP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dump_path = DUMP_DIR / f"collect_{cm_id}_{stamp}.json"
    dump_path.write_text(json.dumps(profile, indent=2, default=str))
    print(f"Dumped profile to {dump_path}")

    print("\n=== ArtistProfile ===")
    print(json.dumps(profile, indent=2, default=str))

    _summarize_coverage(profile)
    return 0


if __name__ == "__main__":
    sys.exit(main())
