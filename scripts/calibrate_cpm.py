"""Empirical CPM calibration from FaroLatino's royalty data.

Scans `data/internal/TOP 10 E.csv` (the 24-month royalty statement) and
computes per-(platform, country) BRUTO/Streams and NETO/Streams ratios.
Outputs:

    config/cpm_rates_empirical.yaml  — real BRUTO CPMs by platform/country
    config/distribution_split.yaml   — per-(platform, country) NETO/BRUTO ratio
    data/internal/cpm_aggregations.json — raw aggregations for inspection

The revenue model can then use the empirical YAML directly (replace
config/cpm_rates.yaml) or apply a global multiplier (NETO/BRUTO) to
convert gross projections to FaroLatino NETO.

Usage:
    source venv/bin/activate
    python scripts/calibrate_cpm.py
"""
from __future__ import annotations

import csv
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = PROJECT_ROOT / "data" / "internal" / "TOP 10 E.csv"
OUT_EMPIRICAL_YAML = PROJECT_ROOT / "config" / "cpm_rates_empirical.yaml"
OUT_SPLIT_YAML = PROJECT_ROOT / "config" / "distribution_split.yaml"
OUT_AGG_JSON = PROJECT_ROOT / "data" / "internal" / "cpm_aggregations.json"

# Map raw CSV platform strings to canonical keys we use in YAML
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
    "Anghami": "anghami",
    "Trebel": "trebel",
}

# Don't emit a CPM unless we've seen enough streams to make it meaningful.
MIN_STREAMS_FOR_CPM = 100_000


def _clean(v: str | None) -> str:
    return v.strip().strip('"') if v else ""


def _to_int(v: str) -> int:
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return 0


def _to_float(v: str) -> float:
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


def main() -> int:
    if not CSV_PATH.exists():
        print(f"Missing {CSV_PATH}", file=sys.stderr)
        return 1

    # Aggregator: (platform, country) -> {"streams": int, "bruto": float, "neto": float}
    pc_agg: dict[tuple[str, str], dict[str, float]] = defaultdict(
        lambda: {"streams": 0, "bruto": 0.0, "neto": 0.0}
    )
    plat_agg: dict[str, dict[str, float]] = defaultdict(
        lambda: {"streams": 0, "bruto": 0.0, "neto": 0.0}
    )
    raw_platforms: set[str] = set()

    print(f"Scanning {CSV_PATH.name}...")
    start = time.time()
    rows = 0
    with CSV_PATH.open("r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows += 1
            raw_platform = _clean(row.get("Plataforma"))
            raw_platforms.add(raw_platform)
            platform = PLATFORM_NORMALIZE.get(raw_platform)
            if not platform:
                continue  # skip unmapped platforms
            country = _clean(row.get("Codigo Pais")).upper()
            if not country or country == "NULL":
                country = "default"
            streams = _to_int(_clean(row.get("Streams")))
            bruto = _to_float(_clean(row.get("BRUTO")))
            neto = _to_float(_clean(row.get("NETO")))
            if streams <= 0:
                continue

            pc_agg[(platform, country)]["streams"] += streams
            pc_agg[(platform, country)]["bruto"] += bruto
            pc_agg[(platform, country)]["neto"] += neto
            plat_agg[platform]["streams"] += streams
            plat_agg[platform]["bruto"] += bruto
            plat_agg[platform]["neto"] += neto

            if rows % 2_000_000 == 0:
                print(f"  ...{rows:,} rows in {time.time()-start:.1f}s")

    print(f"Done scanning ({rows:,} rows in {time.time()-start:.1f}s)\n")

    # --- Compute CPMs (per 1000 streams) ---
    cpm_bruto: dict[str, dict[str, float]] = {}
    cpm_neto: dict[str, dict[str, float]] = {}
    split_ratio: dict[str, dict[str, float]] = {}

    for (platform, country), agg in pc_agg.items():
        if agg["streams"] < MIN_STREAMS_FOR_CPM:
            continue
        bruto_cpm = agg["bruto"] / agg["streams"] * 1000
        neto_cpm = agg["neto"] / agg["streams"] * 1000
        cpm_bruto.setdefault(platform, {})[country] = round(bruto_cpm, 4)
        cpm_neto.setdefault(platform, {})[country] = round(neto_cpm, 4)
        if agg["bruto"] > 0:
            split_ratio.setdefault(platform, {})[country] = round(agg["neto"] / agg["bruto"], 4)

    # Add platform-level defaults from the platform-wide aggregation
    for platform, agg in plat_agg.items():
        if agg["streams"] < MIN_STREAMS_FOR_CPM:
            continue
        cpm_bruto.setdefault(platform, {})["default"] = round(agg["bruto"] / agg["streams"] * 1000, 4)
        cpm_neto.setdefault(platform, {})["default"] = round(agg["neto"] / agg["streams"] * 1000, 4)
        if agg["bruto"] > 0:
            split_ratio.setdefault(platform, {})["default"] = round(agg["neto"] / agg["bruto"], 4)

    # --- Write outputs ---
    OUT_AGG_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_AGG_JSON.write_text(json.dumps({
        "by_platform_country": {
            f"{p}|{c}": v for (p, c), v in pc_agg.items()
        },
        "by_platform": dict(plat_agg),
        "raw_platforms_seen": sorted(raw_platforms),
        "rows_scanned": rows,
    }, indent=2, default=str))
    print(f"Wrote {OUT_AGG_JSON}")

    bruto_yaml = (
        "# Empirical BRUTO CPM rates (gross revenue per 1,000 streams, USD)\n"
        "# Derived from FaroLatino's royalty data: TOP 10 E.csv (Mar 2024 - Mar 2026)\n"
        "# Generated by scripts/calibrate_cpm.py\n"
        "# Structure: platform -> country -> rate. Use 'default' as fallback.\n\n"
        + yaml.safe_dump(cpm_bruto, sort_keys=True, default_flow_style=False)
    )
    OUT_EMPIRICAL_YAML.write_text(bruto_yaml)
    print(f"Wrote {OUT_EMPIRICAL_YAML}")

    split_yaml = (
        "# Distribution split: FaroLatino's NETO as a fraction of BRUTO\n"
        "# Derived from royalty data; multiply gross projections by these to get NETO.\n"
        "# Generated by scripts/calibrate_cpm.py\n\n"
        + yaml.safe_dump(split_ratio, sort_keys=True, default_flow_style=False)
    )
    OUT_SPLIT_YAML.write_text(split_yaml)
    print(f"Wrote {OUT_SPLIT_YAML}")

    # --- Summary ---
    print("\n=== Empirical platform-level summary (BRUTO/Streams) ===")
    print(f"{'platform':<12} {'streams':>15}{'BRUTO total':>16}{'NETO total':>14}{'CPM bruto':>12}{'CPM neto':>11}{'NETO/BRUTO':>12}")
    for plat, agg in sorted(plat_agg.items(), key=lambda kv: -kv[1]["streams"]):
        streams = agg["streams"]
        if streams < MIN_STREAMS_FOR_CPM:
            continue
        cpm_b = agg["bruto"] / streams * 1000
        cpm_n = agg["neto"] / streams * 1000
        ratio = (agg["neto"] / agg["bruto"]) if agg["bruto"] else 0
        print(
            f"{plat:<12} {streams:>15,}"
            f" ${agg['bruto']:>13,.0f}"
            f" ${agg['neto']:>11,.0f}"
            f"  ${cpm_b:>9.4f}"
            f"  ${cpm_n:>8.4f}"
            f"   {ratio*100:>8.1f}%"
        )

    if raw_platforms:
        unmapped = sorted(p for p in raw_platforms if p not in PLATFORM_NORMALIZE)
        if unmapped:
            print(f"\nUnmapped platforms (skipped): {unmapped}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
