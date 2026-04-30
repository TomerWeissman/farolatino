"""Compute per-artist catalog coverage by matching ISRCs.

For each FaroLatino artist with a cached Chartmetric profile, computes
what fraction of the artist's full Chartmetric-listed catalog is
distributed by FaroLatino. Uses the Isrc column from the royalty CSV
and the cached `/api/artist/:id/tracks` payload.

Output: data/internal/coverage_per_artist.json with per-artist
coverage metrics. This unlocks scaling FaroLatino's partial-catalog
streams to total-artist streams (Phase H).

Usage:
    source venv/bin/activate
    python scripts/compute_catalog_coverage.py
"""
from __future__ import annotations

import csv
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = PROJECT_ROOT / "data" / "internal" / "TOP 10 E.csv"
CACHE_DIR = PROJECT_ROOT / "data" / "cache"
OUT_PATH = PROJECT_ROOT / "data" / "internal" / "coverage_per_artist.json"
CM_IDS_PATH = PROJECT_ROOT / "data" / "internal" / "sample_50_cm_ids.json"


def _clean(v: str | None) -> str:
    return v.strip().strip('"') if v else ""


def _load_cm_ids() -> dict[str, int]:
    """Map artist query -> cm_id from the sample we already searched."""
    if not CM_IDS_PATH.exists():
        return {}
    rows = json.loads(CM_IDS_PATH.read_text())
    out: dict[str, int] = {}
    for r in rows:
        cm_id = r.get("cm_id")
        if cm_id:
            out[r["query"]] = int(cm_id)
    return out


def _load_chartmetric_isrcs(cm_id: int) -> set[str]:
    """Pull ISRCs from cached tracks.json for one artist."""
    path = CACHE_DIR / str(cm_id) / "tracks.json"
    if not path.exists():
        return set()
    payload = json.loads(path.read_text())
    items = payload.get("data") or []
    if not isinstance(items, list):
        return set()
    isrcs: set[str] = set()
    for t in items:
        if not isinstance(t, dict):
            continue
        isrc = t.get("isrc")
        if isinstance(isrc, str) and isrc:
            isrcs.add(isrc.strip().upper())
    return isrcs


def _scan_royalty_isrcs(target_artists: set[str]) -> dict[str, dict]:
    """Aggregate ISRCs and stream counts from the royalty CSV for the
    given artists. Returns {artist_name: {isrc: streams}}."""
    print(f"Scanning {CSV_PATH.name} for {len(target_artists)} artists...")
    start = time.time()
    per_artist: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    rows = 0
    matched = 0
    with CSV_PATH.open("r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows += 1
            artist = _clean(row.get("Artista"))
            if artist not in target_artists:
                continue
            isrc = _clean(row.get("Isrc")).upper()
            if not isrc:
                continue
            try:
                streams = int(float(_clean(row.get("Streams")) or 0))
            except (ValueError, TypeError):
                streams = 0
            if streams <= 0:
                continue
            per_artist[artist][isrc] += streams
            matched += 1
            if rows % 2_000_000 == 0:
                print(f"  ...{rows:,} rows scanned in {time.time()-start:.1f}s")
    print(f"Scan done in {time.time()-start:.1f}s. Matched {matched:,} rows for {len(per_artist)} artists.")
    return per_artist


def main() -> int:
    if not CSV_PATH.exists():
        print(f"Missing {CSV_PATH}", file=sys.stderr)
        return 1
    cm_ids = _load_cm_ids()
    if not cm_ids:
        print(f"Missing or empty {CM_IDS_PATH}", file=sys.stderr)
        return 1

    # Filter to artists where we actually have a cached tracks.json
    artists_with_tracks: dict[str, int] = {}
    for name, cm_id in cm_ids.items():
        if (CACHE_DIR / str(cm_id) / "tracks.json").exists():
            artists_with_tracks[name] = cm_id
    print(f"{len(artists_with_tracks)}/{len(cm_ids)} artists have cached Chartmetric tracks.")

    royalty_per_artist = _scan_royalty_isrcs(set(artists_with_tracks.keys()))

    coverage: dict[str, dict] = {}
    for name, cm_id in artists_with_tracks.items():
        cm_isrcs = _load_chartmetric_isrcs(cm_id)
        royalty = royalty_per_artist.get(name, {})
        royalty_isrcs = set(royalty.keys())
        matched_isrcs = cm_isrcs & royalty_isrcs

        n_cm = len(cm_isrcs)
        n_royalty = len(royalty_isrcs)
        n_matched = len(matched_isrcs)

        track_coverage = (n_matched / n_cm) if n_cm else 0.0
        royalty_streams_in_cm_catalog = sum(royalty[isrc] for isrc in matched_isrcs)
        royalty_streams_total = sum(royalty.values())
        royalty_outside_cm = royalty_streams_total - royalty_streams_in_cm_catalog

        coverage[name] = {
            "cm_id": cm_id,
            "n_chartmetric_tracks_with_isrc": n_cm,
            "n_royalty_isrcs": n_royalty,
            "n_matched": n_matched,
            "track_coverage": round(track_coverage, 4),
            "royalty_streams_total_24mo": royalty_streams_total,
            "royalty_streams_in_cm_catalog_24mo": royalty_streams_in_cm_catalog,
            "royalty_streams_outside_cm_24mo": royalty_outside_cm,
        }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(coverage, indent=2, default=str))
    print(f"\nWrote {OUT_PATH}")

    # Summary + spot checks
    sorted_by_cov = sorted(coverage.items(), key=lambda x: -x[1]["track_coverage"])
    print(f"\n{'Artist':<35}{'cm_tracks':>11}{'royalty_isrcs':>15}{'matched':>10}{'coverage':>11}")
    print("-" * 85)
    for name, c in sorted_by_cov:
        print(f"{name[:34]:<35}{c['n_chartmetric_tracks_with_isrc']:>11}{c['n_royalty_isrcs']:>15}{c['n_matched']:>10}{c['track_coverage']:>10.1%}")

    # Histogram
    bands = [(0.0, 0.1), (0.1, 0.3), (0.3, 0.5), (0.5, 0.8), (0.8, 1.01)]
    print("\nCoverage histogram:")
    for lo, hi in bands:
        n = sum(1 for c in coverage.values() if lo <= c["track_coverage"] < hi)
        print(f"  [{lo:.1f}, {hi:.1f}): {n} artists")

    return 0


if __name__ == "__main__":
    sys.exit(main())
