"""Fit per-bucket Chartmetric -> total-stream multipliers.

Reads the training dataset from build_training_dataset.py and fits
median multipliers per (career_stage, career_trend) bucket per
platform. Sparse buckets fall back to a platform-level default.

Output: config/stream_multipliers.yaml — used by the production
revenue model in d3_revenue_potential.py.

Usage:
    source venv/bin/activate
    python scripts/fit_multipliers.py
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import median

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TRAINING_PATH = PROJECT_ROOT / "data" / "internal" / "training_dataset.json"
OUT_PATH = PROJECT_ROOT / "config" / "stream_multipliers.yaml"

MIN_BUCKET_SIZE = 3  # below this, fall back to platform default


def _bucket_key(stage: str | None, trend: str | None) -> str:
    """Coarsen the bucket — many trends/stages have only 1-2 examples."""
    s = (stage or "unknown").lower()
    t = (trend or "unknown").lower()
    # Coarsen trend
    if "decline" in t:
        t_coarse = "decline"
    elif t in ("growth", "explosive growth"):
        t_coarse = "growth"
    elif t == "steady":
        t_coarse = "steady"
    else:
        t_coarse = "unknown"
    return f"{s}__{t_coarse}"


def _multiplier_base(row: dict, platform: str) -> float | None:
    """Pick the base metric to compute the multiplier against."""
    if platform == "spotify":
        return row["sp_monthly_listeners"] or None
    if platform == "youtube":
        # Prefer subscribers as the base — it's what the production model
        # uses when yt_daily_views is unavailable. This makes the fitted
        # multiplier directly applicable.
        return row["yt_subscribers"] or None
    # Apple, Deezer, Facebook, Amazon: anchor on Spotify monthly listeners
    return row["sp_monthly_listeners"] or None


def main() -> int:
    if not TRAINING_PATH.exists():
        print(f"Missing {TRAINING_PATH}. Run build_training_dataset.py first.", file=sys.stderr)
        return 1
    rows = json.loads(TRAINING_PATH.read_text())
    print(f"Loaded {len(rows)} training rows")

    # Compute per-row implied multiplier
    enriched = []
    for r in rows:
        base = _multiplier_base(r, r["platform"])
        if not base:
            continue
        mult = r["estimated_total_streams_per_month"] / base
        enriched.append({**r, "bucket": _bucket_key(r["career_stage"], r["career_trend"]), "multiplier": mult})

    # Group by (bucket, platform)
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    plat_default: dict[str, list[float]] = defaultdict(list)
    for r in enriched:
        grouped[(r["bucket"], r["platform"])].append(r["multiplier"])
        plat_default[r["platform"]].append(r["multiplier"])

    # Compute defaults
    defaults = {}
    for plat, vals in plat_default.items():
        defaults[plat] = round(median(vals), 3)

    # Compute per-bucket
    multipliers: dict[str, dict[str, float]] = {}
    for (bucket, plat), vals in grouped.items():
        if len(vals) < MIN_BUCKET_SIZE:
            continue
        multipliers.setdefault(bucket, {})[plat] = round(median(vals), 3)

    # Output to a SEPARATE proposed file. The production YAML is written
    # by hand to preserve the lengthy provenance comments + the
    # last_calibrated / sample_size / realistic_prospect_mae_pct fields
    # consumed by the Streamlit footer. After eyeballing the proposal,
    # the operator selectively merges into config/stream_multipliers.yaml.
    proposed_path = OUT_PATH.parent / "stream_multipliers_proposed.yaml"
    yaml_text = (
        "# PROPOSED multipliers from scripts/fit_multipliers.py.\n"
        "# This is NOT the production YAML. Review before merging into\n"
        "# config/stream_multipliers.yaml — the production file carries\n"
        "# provenance comments and metadata fields that this auto-fit will\n"
        "# overwrite if pointed at the production path.\n\n"
    )
    yaml_text += "default:\n"
    for plat, val in sorted(defaults.items()):
        yaml_text += f"  {plat}: {val}\n"
    yaml_text += "\nbuckets:\n"
    for bucket in sorted(multipliers.keys()):
        yaml_text += f"  {bucket}:\n"
        for plat, val in sorted(multipliers[bucket].items()):
            yaml_text += f"    {plat}: {val}\n"
    proposed_path.write_text(yaml_text)
    print(f"Wrote PROPOSED multipliers to {proposed_path}")
    print("(Production YAML at config/stream_multipliers.yaml is untouched —")
    print(" review the proposal and selectively merge.)")

    # Summary
    print("\n=== Platform-level defaults (median across all buckets) ===")
    for plat, val in sorted(defaults.items()):
        n = len(plat_default[plat])
        print(f"  {plat:<14} multiplier={val:>8.3f}  (n={n})")

    print("\n=== Per-bucket multipliers (only buckets with sufficient samples) ===")
    bucket_counts: dict[str, int] = defaultdict(int)
    for r in enriched:
        bucket_counts[r["bucket"]] += 1
    print(f"\n{'bucket':<35}{'n_rows':>8}")
    for bucket, n in sorted(bucket_counts.items(), key=lambda x: -x[1]):
        print(f"  {bucket:<35}{n:>8}")

    print()
    for bucket in sorted(multipliers.keys()):
        plat_mults = multipliers[bucket]
        print(f"  {bucket}:")
        for plat, val in sorted(plat_mults.items()):
            print(f"    {plat:<14} {val:>8.3f}")

    print(f"\nTotal eligible rows: {len(enriched)}")
    print(f"Buckets meeting min size ({MIN_BUCKET_SIZE}): {len(multipliers)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
