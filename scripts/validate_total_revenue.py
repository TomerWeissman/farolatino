"""Validate the total-artist-revenue predictor against the right ground truth.

For each artist with sufficient track_coverage, the proper ground truth
for the prospect-revenue use case is:

    total_artist_NETO_per_year ≈ FaroLatino_NETO_per_year / track_coverage

This script reports MAE on the high-coverage subset and, separately, on
prospect-shaped artists.

Usage:
    source venv/bin/activate
    python scripts/validate_total_revenue.py
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from mcp_server.tools.chartmetric_artist import get_artist_data  # noqa: E402
from mcp_server.tools.revenue_model import estimate_revenue  # noqa: E402
from mcp_server.tools.scoring.d3_revenue_potential import _is_legacy_catalog  # noqa: E402
from mcp_server.models import build_artist  # noqa: E402

CSV_PATH = PROJECT_ROOT / "data" / "internal" / "TOP 10 E.csv"
COVERAGE_PATH = PROJECT_ROOT / "data" / "internal" / "coverage_per_artist.json"
SAMPLE_IDS_PATH = PROJECT_ROOT / "data" / "internal" / "sample_50_cm_ids.json"


_WHITELIST = {"noteworthy_insights": {"text", "type", "date", "metric", "value"}}


def _adapt(p: dict) -> dict:
    """Strip unknown keys from list-of-dict fields so build_artist
    doesn't choke on shape mismatches surfaced in Phase A."""
    a = dict(p)
    for k, allowed in _WHITELIST.items():
        items = a.get(k)
        if isinstance(items, list):
            a[k] = [
                {kk: vv for kk, vv in it.items() if kk in allowed}
                if isinstance(it, dict) else it
                for it in items
            ]
    return a


def _clean(v: str | None) -> str:
    return v.strip().strip('"') if v else ""


def _scan_neto_per_artist(target_artists: set[str]) -> dict[str, float]:
    """Total NETO over 24 months per artist."""
    neto: dict[str, float] = defaultdict(float)
    with CSV_PATH.open("r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            artist = _clean(row.get("Artista"))
            if artist not in target_artists:
                continue
            try:
                n = float(_clean(row.get("NETO")) or 0)
            except (ValueError, TypeError):
                n = 0
            if n > 0:
                neto[artist] += n
    return neto


def main() -> int:
    coverage = json.loads(COVERAGE_PATH.read_text())
    sample = json.loads(SAMPLE_IDS_PATH.read_text())
    cm_ids = {r["query"]: r["cm_id"] for r in sample if r.get("cm_id")}

    eligible = {
        name: c for name, c in coverage.items()
        if c["track_coverage"] >= 0.30 and name in cm_ids
    }
    print(f"Validating on {len(eligible)} artists (coverage >= 30%)...")

    print("\nLoading actual NETO from royalty CSV...")
    actual_neto_24mo = _scan_neto_per_artist(set(eligible.keys()))

    rows = []
    for name, c in eligible.items():
        cov = c["track_coverage"]
        actual_partial_yr = actual_neto_24mo.get(name, 0) / 2
        if actual_partial_yr <= 0:
            continue
        # Scale up to total artist NETO (the real ground truth for prospect eval)
        actual_total_yr = actual_partial_yr / cov

        # Get our prediction
        cm_id = cm_ids[name]
        try:
            profile = _adapt(get_artist_data(cm_id, use_cache=True))
        except Exception as e:
            print(f"  {name}: get_artist_data failed: {e}")
            continue
        rev = estimate_revenue(profile)
        pred_bruto_yr = rev.get("annual_projected", 0)
        pred_neto_yr = pred_bruto_yr * 0.74

        artist_obj = build_artist(profile)
        is_leg = _is_legacy_catalog(artist_obj)

        # Errors against partial vs total ground truth
        err_partial = (pred_neto_yr / actual_partial_yr - 1) * 100
        err_total = (pred_neto_yr / actual_total_yr - 1) * 100

        rows.append({
            "artist": name,
            "coverage": cov,
            "career_stage": profile.get("career_stage"),
            "career_trend": profile.get("career_trend"),
            "is_legacy": is_leg,
            "actual_partial_yr": actual_partial_yr,
            "actual_total_yr": actual_total_yr,
            "pred_neto_yr": pred_neto_yr,
            "err_vs_partial_pct": err_partial,
            "err_vs_total_pct": err_total,
        })

    print(f"\n{'Artist':<35}{'Cov':>5}{'Stage':<13}{'ActualPartial':>14}{'ActualTotal':>13}{'PredNETO':>11}{'vsPartial':>11}{'vsTotal':>10}")
    print("-" * 115)
    for r in sorted(rows, key=lambda x: -x["actual_total_yr"]):
        print(
            f"{r['artist'][:34]:<35}{r['coverage']:>5.0%}"
            f"{(r['career_stage'] or '')[:12]:<13}"
            f"${r['actual_partial_yr']:>12,.0f}"
            f"${r['actual_total_yr']:>11,.0f}"
            f"${r['pred_neto_yr']:>9,.0f}"
            f"{r['err_vs_partial_pct']:>+10.0f}%"
            f"{r['err_vs_total_pct']:>+9.0f}%"
        )

    if not rows:
        print("No rows.")
        return 1

    def _stats(errs):
        abs_errs = [abs(e) for e in errs]
        return {
            "n": len(abs_errs),
            "mae": sum(abs_errs) / len(abs_errs),
            "median": sorted(abs_errs)[len(abs_errs) // 2],
            "within_50": sum(1 for e in abs_errs if e <= 50),
            "within_100": sum(1 for e in abs_errs if e <= 100),
        }

    all_total = _stats([r["err_vs_total_pct"] for r in rows])
    all_partial = _stats([r["err_vs_partial_pct"] for r in rows])
    active = _stats([r["err_vs_total_pct"] for r in rows if not r["is_legacy"]])

    print(f"\n{'Subset':<30}{'n':>5}{'MAE':>9}{'Median':>9}{'Within50%':>12}{'Within100%':>12}")
    print("-" * 80)
    print(f"{'All vs PARTIAL ground truth':<30}{all_partial['n']:>5}{all_partial['mae']:>8.0f}%{all_partial['median']:>8.0f}%{all_partial['within_50']:>10}/{all_partial['n']:<2}{all_partial['within_100']:>10}/{all_partial['n']:<2}")
    print(f"{'All vs TOTAL ground truth':<30}{all_total['n']:>5}{all_total['mae']:>8.0f}%{all_total['median']:>8.0f}%{all_total['within_50']:>10}/{all_total['n']:<2}{all_total['within_100']:>10}/{all_total['n']:<2}")
    print(f"{'Active (excl. legacy) vs TOTAL':<30}{active['n']:>5}{active['mae']:>8.0f}%{active['median']:>8.0f}%{active['within_50']:>10}/{active['n']:<2}{active['within_100']:>10}/{active['n']:<2}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
