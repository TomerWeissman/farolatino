"""Mode 2 end-to-end evaluator for the FaroLatino A&R pipeline.

Runs the full chain on a real artist:
    profile -> compute_prospect_score -> estimate_revenue
            -> generate_dossier -> route_alert

Two input modes:
    python scripts/evaluate_artist.py "Feid"
    python scripts/evaluate_artist.py 152776
    python scripts/evaluate_artist.py --from-cache data/cache/collect_152776_*.json
    python scripts/evaluate_artist.py "Feid" --profile emerging_momentum

Phase A purpose: see how the scorer/revenue/dossier/alert layers behave
against real Chartmetric data for the first time. Failures and weirdness
get logged to docs/phase_a_findings.md, not silently fixed.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from mcp_server.tools.alert_router import route_alert  # noqa: E402
from mcp_server.tools.chartmetric_artist import get_artist_data  # noqa: E402
from mcp_server.tools.chartmetric_search import search_artists  # noqa: E402
from mcp_server.tools.dossier_generator import generate_dossier  # noqa: E402
from mcp_server.tools.revenue_model import estimate_revenue  # noqa: E402
from mcp_server.tools.scoring.engine import compute_prospect_score  # noqa: E402

DUMP_DIR = PROJECT_ROOT / "data" / "cache"

# Profile fields the alert router reads for signal_alerts (see config/alerts.yaml).
ALERT_SIGNAL_FIELDS = (
    "shazam_count_diff_pct",
    "tiktok_followers_diff_pct",
    "sp_monthly_listeners_diff_pct",
    "career_trend",
    "new_editorial_playlists",
)

# Phase A adapters — strip fields not in the dataclass models.
# Each entry maps a profile list field to the set of keys its dataclass accepts.
# Found via TypeError on build_artist; documented in docs/phase_a_findings.md.
_DATACLASS_FIELD_WHITELIST = {
    "noteworthy_insights": {"text", "type", "date", "metric", "value"},
}


def _adapt_profile_for_models(profile: dict) -> dict:
    """Drop unknown keys from list-of-dict fields so build_artist() doesn't choke.

    Preserves the original profile dict; returns a shallow-copied version with
    sanitized lists. Phase A only — Phase C should reconcile builders/models.
    """
    adapted = dict(profile)
    for key, allowed in _DATACLASS_FIELD_WHITELIST.items():
        items = adapted.get(key)
        if not isinstance(items, list):
            continue
        adapted[key] = [
            {k: v for k, v in item.items() if k in allowed}
            if isinstance(item, dict) else item
            for item in items
        ]
    return adapted


def _resolve_artist(arg: str) -> int | None:
    """Search by name or accept a literal cm_id."""
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
        return top[int(choice) - 1]["cm_id"]
    except (ValueError, IndexError):
        print(f"Invalid choice: {choice}")
        return None


def _load_from_cache(path: Path) -> dict:
    payload = json.loads(path.read_text())
    # collect_artist.py dumps the profile dict directly; older dumps may wrap it.
    return payload.get("profile", payload) if isinstance(payload, dict) else payload


def _build_alert_input(profile: dict, score: dict) -> dict:
    """Assemble the dict route_alert expects: name + prospect_score + signal fields."""
    payload = {
        "name": profile.get("name", "Unknown"),
        "prospect_score": score.get("prospect_score", 0),
    }
    for field in ALERT_SIGNAL_FIELDS:
        if field in profile:
            payload[field] = profile[field]
    return payload


def _print_summary(profile: dict, score: dict, revenue: dict, alert: dict) -> None:
    name = profile.get("name", "Unknown")
    tier = score.get("tier", "?")
    overall = score.get("prospect_score", 0)
    confidence = score.get("confidence", 0)
    completeness = score.get("data_completeness", 0)
    profile_used = score.get("profile_used", "?")

    print("\n" + "=" * 72)
    print(f"  {name} — {tier}  (score: {overall} / 100)")
    print(
        f"  profile: {profile_used}   "
        f"confidence: {confidence}   data_completeness: {completeness}"
    )
    print("=" * 72)

    print("\nDimension breakdown:")
    print(f"  {'dimension':<28}{'score':>8}{'weight':>10}{'contrib':>10}{'conf':>8}")
    for dim_name, dim in score.get("dimensions", {}).items():
        print(
            f"  {dim_name:<28}"
            f"{dim['score']:>8.1f}"
            f"{dim['weight']:>10.2f}"
            f"{dim['weighted_contribution']:>10.1f}"
            f"{dim['confidence']:>8.2f}"
        )
        print(f"    rationale: {dim.get('rationale', '')[:120]}")

    countries = profile.get("listener_countries", [])[:3]
    if countries:
        print("\nTop 3 markets:")
        for c in countries:
            cur = c.get("listeners", 0)
            prev = c.get("prev_listeners", 0)
            delta = ((cur - prev) / prev * 100) if prev else 0
            print(
                f"  {c.get('country_code', '??'):<4}"
                f"{cur:>14,} listeners "
                f"({delta:+6.1f}% vs prev)"
            )

    if revenue and "monthly_total" in revenue:
        print("\nRevenue projection:")
        print(f"  monthly_total:    ${revenue.get('monthly_total', 0):,.0f}")
        print(f"  annual_projected: ${revenue.get('annual_projected', 0):,.0f}")
        print(f"  growth_factor:    {revenue.get('growth_factor', 0)}")

    print("\nAlert:")
    print(f"  tier: {alert.get('tier')}   action: {alert.get('action')}")
    print(f"  channels: {alert.get('all_channels', [])}")
    if alert.get("signal_alerts"):
        print(f"  signal_alerts ({len(alert['signal_alerts'])}):")
        for sa in alert["signal_alerts"]:
            label = sa.get("name", "?")
            detail = sa.get("field") or sa.get("condition") or ""
            print(f"    - {label}  ({detail})")
    else:
        print("  signal_alerts: (none)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "target",
        nargs="?",
        help="Artist name or Chartmetric ID. Omit when using --from-cache.",
    )
    parser.add_argument(
        "--from-cache",
        type=Path,
        help="Load the ArtistProfile from a saved JSON dump (no API calls).",
    )
    parser.add_argument(
        "--profile",
        default="default",
        help="Search profile: default, emerging_momentum, revenue_focus, latam_expansion.",
    )
    args = parser.parse_args()

    # --- Resolve the profile ---
    if args.from_cache:
        if not args.from_cache.exists():
            print(f"Cache file not found: {args.from_cache}", file=sys.stderr)
            return 1
        profile = _load_from_cache(args.from_cache)
        cm_id = profile.get("cm_id")
        print(f"Loaded {profile.get('name')} (cm_id={cm_id}) from {args.from_cache.name}")
    else:
        if not args.target:
            parser.error("Provide an artist name/cm_id, or use --from-cache.")
        cm_id = _resolve_artist(args.target)
        if cm_id is None:
            return 1
        print(f"\nFetching artist data for cm_id={cm_id}...")
        try:
            profile = get_artist_data(cm_id, use_cache=True)
        except Exception as exc:
            print(f"STEP 1 (collection) FAILED: {exc}", file=sys.stderr)
            traceback.print_exc()
            return 1

    # --- Score / revenue / dossier / alert ---
    bundle = {"profile": profile}
    adapted = _adapt_profile_for_models(profile)

    try:
        bundle["score"] = compute_prospect_score(adapted, profile_name=args.profile)
    except Exception as exc:
        print(f"STEP 2 (compute_prospect_score) FAILED: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1

    try:
        bundle["revenue"] = estimate_revenue(adapted)
    except Exception as exc:
        print(f"STEP 3 (estimate_revenue) FAILED: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1

    try:
        bundle["dossier"] = generate_dossier(adapted, bundle["score"], bundle["revenue"])
    except Exception as exc:
        print(f"STEP 4 (generate_dossier) FAILED: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1

    try:
        alert_input = _build_alert_input(profile, bundle["score"])
        bundle["alert"] = route_alert(alert_input)
    except Exception as exc:
        print(f"STEP 5 (route_alert) FAILED: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1

    # --- Persist + display ---
    DUMP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dump_path = DUMP_DIR / f"evaluate_{cm_id}_{stamp}.json"
    dump_path.write_text(json.dumps(bundle, indent=2, default=str))
    print(f"\nWrote {dump_path}")

    _print_summary(profile, bundle["score"], bundle["revenue"], bundle["alert"])

    # Render Markdown dossier (the human-readable form)
    try:
        from mcp_server.tools.dossier_renderer import render_dossier
        print("\n" + "=" * 72)
        print("  DOSSIER (Markdown)")
        print("=" * 72)
        print(render_dossier(bundle["dossier"], profile))
    except Exception as exc:
        print(f"Renderer failed: {exc}", file=sys.stderr)
        traceback.print_exc()

    return 0


if __name__ == "__main__":
    sys.exit(main())
