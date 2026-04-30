"""Expand the calibration sample by fetching more book artists from Chartmetric.

Picks the next N highest-NETO artists from FaroLatino's book that
haven't yet been searched/fetched on Chartmetric, then searches and
fetches each one. Outputs an updated sample_50_cm_ids.json.

Usage:
    source venv/bin/activate
    python scripts/expand_calibration_sample.py --add 60
    python scripts/expand_calibration_sample.py --add 100 --min-neto 5000

This script handles the only piece of the calibration pipeline that
isn't covered by an existing script. Run it before calibrate.md's
later steps (compute_catalog_coverage.py, build_training_dataset.py,
fit_multipliers.py, validate_total_revenue.py).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from mcp_server.tools.chartmetric_artist import get_artist_data  # noqa: E402
from mcp_server.tools.chartmetric_search import search_artists  # noqa: E402

CSV_PATH = PROJECT_ROOT / "data" / "internal" / "TOP 10 E.csv"
SAMPLE_PATH = PROJECT_ROOT / "data" / "internal" / "sample_50_cm_ids.json"
PROFILES_PATH = PROJECT_ROOT / "data" / "internal" / "sample_45_profiles.json"


def _clean(v: str | None) -> str:
    return v.strip().strip('"') if v else ""


def _scan_neto_per_artist() -> dict[str, float]:
    """Aggregate total NETO per artist over the 24-month window."""
    print(f"Scanning {CSV_PATH.name}...")
    start = time.time()
    neto: dict[str, float] = defaultdict(float)
    with CSV_PATH.open("r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            artist = _clean(row.get("Artista"))
            if not artist:
                continue
            try:
                n = float(_clean(row.get("NETO")) or 0)
            except (ValueError, TypeError):
                n = 0
            if n > 0:
                neto[artist] += n
    print(f"  Scanned in {time.time()-start:.0f}s. {len(neto)} artists with NETO > 0.")
    return neto


def _primary_name(artist: str) -> str:
    """Strip collaboration suffixes for cleaner search queries."""
    return artist.split(",")[0].split(" & ")[0].split(" feat")[0].strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--add", type=int, default=60, help="Number of new artists to add")
    parser.add_argument("--min-neto", type=float, default=1000.0,
                        help="Minimum 24-month NETO threshold to consider")
    args = parser.parse_args()

    # Load existing sample so we don't re-search
    existing: dict[str, dict] = {}
    if SAMPLE_PATH.exists():
        for r in json.loads(SAMPLE_PATH.read_text()):
            existing[r["query"]] = r
    print(f"Existing sample: {len(existing)} artists")

    # Aggregate book NETO
    neto_per_artist = _scan_neto_per_artist()

    # Pick candidates: not already sampled, NETO above threshold, sorted desc
    candidates = [
        (name, n) for name, n in neto_per_artist.items()
        if name not in existing and n >= args.min_neto
    ]
    candidates.sort(key=lambda x: -x[1])
    target = candidates[: args.add]
    print(f"Selected {len(target)} new candidates (NETO range: "
          f"${target[0][1]:,.0f} → ${target[-1][1]:,.0f})" if target else "No candidates.")

    if not target:
        return 0

    # Search Chartmetric for each (1 req/s throttled in api_get)
    new_results: list[dict] = []
    start = time.time()
    for i, (name, n) in enumerate(target, 1):
        primary = _primary_name(name)
        print(f"  [{i}/{len(target)}] searching {name!r} (NETO ${n:,.0f})...", flush=True)
        try:
            r = search_artists(primary, limit=1)
            artists = r.get("artists", [])
            if artists:
                top = artists[0]
                new_results.append({
                    "query": name,
                    "searched": primary,
                    "cm_id": top["cm_id"],
                    "cm_name": top.get("name"),
                    "sp_followers": top.get("sp_followers"),
                    "sp_monthly_listeners": top.get("sp_monthly_listeners"),
                    "neto_24mo": n,
                })
            else:
                new_results.append({"query": name, "searched": primary, "cm_id": None, "neto_24mo": n})
        except Exception as e:
            print(f"    ERROR: {e}")
            new_results.append({"query": name, "cm_id": None, "error": str(e), "neto_24mo": n})

    resolved = [r for r in new_results if r.get("cm_id")]
    print(f"\nSearch phase: {len(resolved)}/{len(new_results)} resolved in {time.time()-start:.0f}s")

    # Fetch full profiles for resolved (warms cache + populates sample_45_profiles.json)
    profiles: dict = {}
    if PROFILES_PATH.exists():
        profiles = json.loads(PROFILES_PATH.read_text())
    print(f"\nFetching profiles for {len(resolved)} new artists (cached & throttled)...")
    fetch_start = time.time()
    for i, r in enumerate(resolved, 1):
        cm_id = r["cm_id"]
        if r["query"] in profiles:
            continue
        try:
            p = get_artist_data(cm_id, use_cache=True)
            profiles[r["query"]] = {
                "cm_id": cm_id,
                "cm_name": p.get("name"),
                "career_stage": p.get("career_stage"),
                "career_trend": p.get("career_trend"),
                "sp_monthly_listeners": p.get("sp_monthly_listeners"),
                "sp_followers": p.get("sp_followers"),
                "yt_subscribers": p.get("yt_subscribers"),
                "tiktok_followers": p.get("tiktok_followers"),
                "ig_followers": p.get("ig_followers"),
                "recent_release_count_6m": p.get("recent_release_count_6m"),
                "recent_release_count_12m": p.get("recent_release_count_12m"),
                "genres": p.get("genres", [])[:3],
            }
            if i % 5 == 0:
                print(f"  ...{i}/{len(resolved)} ({time.time()-fetch_start:.0f}s elapsed)", flush=True)
        except Exception as e:
            print(f"  {r['query']}: fetch failed: {e}")
    print(f"Fetched {len(profiles)} total profiles in {time.time()-fetch_start:.0f}s")

    # Persist
    merged_sample = list(existing.values()) + new_results
    SAMPLE_PATH.write_text(json.dumps(merged_sample, indent=2))
    PROFILES_PATH.write_text(json.dumps(profiles, indent=2, default=str))
    print(f"\nWrote {SAMPLE_PATH} ({len(merged_sample)} artists)")
    print(f"Wrote {PROFILES_PATH} ({len(profiles)} profiles)")
    print(f"\nNext: run scripts/compute_catalog_coverage.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
