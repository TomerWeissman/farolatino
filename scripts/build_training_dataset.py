"""Build the reverse-engineered total-streams training dataset.

For each artist with track_coverage >= 0.3 (high-confidence subset),
scale FaroLatino's per-(artist, platform) streams up to estimate the
artist's TOTAL per-platform streaming activity:

    estimated_total_streams_per_month
        = (FaroLatino streams over 24 months) / 24 / track_coverage

Pair with each artist's Chartmetric features so Phase I can fit
multipliers (Chartmetric features -> total streams per platform).

Usage:
    source venv/bin/activate
    python scripts/build_training_dataset.py
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
COVERAGE_PATH = PROJECT_ROOT / "data" / "internal" / "coverage_per_artist.json"
PROFILES_PATH = PROJECT_ROOT / "data" / "internal" / "sample_45_profiles.json"
OUT_PATH = PROJECT_ROOT / "data" / "internal" / "training_dataset.json"

PLATFORM_NORMALIZE = {
    "Spotify": "spotify",
    "YouTube Audio": "youtube",
    "YouTube Music": "youtube",
    "YouTube": "youtube",
    "iTunes": "apple_music",
    "Apple Music": "apple_music",
    "Deezer": "deezer",
    "TikTok": "tiktok",
    "Amazon": "amazon",
    "Facebook Audio": "facebook",
    "Facebook Revenue Share Video": "facebook",
}

MIN_COVERAGE = 0.30


def _clean(v: str | None) -> str:
    return v.strip().strip('"') if v else ""


def main() -> int:
    if not COVERAGE_PATH.exists():
        print(f"Missing {COVERAGE_PATH}. Run scripts/compute_catalog_coverage.py first.", file=sys.stderr)
        return 1
    if not PROFILES_PATH.exists():
        print(f"Missing {PROFILES_PATH}.", file=sys.stderr)
        return 1

    coverage = json.loads(COVERAGE_PATH.read_text())
    profiles = json.loads(PROFILES_PATH.read_text())

    eligible = {name: c for name, c in coverage.items() if c["track_coverage"] >= MIN_COVERAGE}
    print(f"Eligible artists (coverage >= {MIN_COVERAGE}): {len(eligible)}/{len(coverage)}")
    if not eligible:
        print("No eligible artists.", file=sys.stderr)
        return 1

    # Aggregate per-(artist, platform) streams from CSV
    print(f"Scanning {CSV_PATH.name} for per-(artist, platform) streams...")
    start = time.time()
    streams: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    with CSV_PATH.open("r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            artist = _clean(row.get("Artista"))
            if artist not in eligible:
                continue
            platform = PLATFORM_NORMALIZE.get(_clean(row.get("Plataforma")))
            if not platform:
                continue
            try:
                s = int(float(_clean(row.get("Streams")) or 0))
            except (ValueError, TypeError):
                s = 0
            if s <= 0:
                continue
            streams[artist][platform] += s
    print(f"Done in {time.time()-start:.1f}s.")

    rows: list[dict] = []
    for name, c in eligible.items():
        prof = profiles.get(name)
        if not prof:
            continue  # no Chartmetric profile cached
        cov = c["track_coverage"]
        sp_listeners = prof.get("sp_monthly_listeners") or 0
        sp_followers = prof.get("sp_followers") or 0
        yt_subs = prof.get("yt_subscribers") or 0
        listener_to_follower = (sp_listeners / sp_followers) if sp_followers else None
        for platform, total_24mo in streams[name].items():
            actual_pm = total_24mo / 24
            scaled_pm = actual_pm / cov  # estimate of total artist streams per month
            rows.append({
                "artist": name,
                "cm_id": prof["cm_id"],
                "platform": platform,
                "career_stage": prof.get("career_stage"),
                "career_trend": prof.get("career_trend"),
                "sp_monthly_listeners": sp_listeners,
                "sp_followers": sp_followers,
                "yt_subscribers": yt_subs,
                "listener_to_follower": listener_to_follower,
                "recent_release_count_6m": prof.get("recent_release_count_6m", 0),
                "track_coverage": cov,
                "actual_streams_per_month": round(actual_pm, 1),
                "estimated_total_streams_per_month": round(scaled_pm, 1),
            })

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(rows, indent=2, default=str))
    print(f"\nWrote {len(rows)} training rows to {OUT_PATH}")

    # Verification: full-catalog artists should have actual ≈ scaled
    print("\nFull-catalog spot-check (coverage >= 0.7):")
    full_catalog = [r for r in rows if r["track_coverage"] >= 0.7 and r["platform"] == "spotify"]
    for r in sorted(full_catalog, key=lambda x: -x["estimated_total_streams_per_month"])[:10]:
        ratio = r["estimated_total_streams_per_month"] / r["actual_streams_per_month"] if r["actual_streams_per_month"] else 0
        sp_l = r["sp_monthly_listeners"]
        implied_mult = (r["estimated_total_streams_per_month"] / sp_l) if sp_l else 0
        print(f"  {r['artist'][:30]:<31} cov={r['track_coverage']:.0%}  actual_pm={r['actual_streams_per_month']:>11,.0f}  scaled_pm={r['estimated_total_streams_per_month']:>11,.0f}  implied_mult={implied_mult:.2f}")

    print("\nSample of training rows by platform:")
    for plat in ("spotify", "youtube", "apple_music", "facebook", "amazon"):
        plat_rows = [r for r in rows if r["platform"] == plat]
        print(f"  {plat}: {len(plat_rows)} rows")

    return 0


if __name__ == "__main__":
    sys.exit(main())
