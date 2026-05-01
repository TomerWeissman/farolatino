"""Render an artist dossier dict as human-readable Markdown.

Produces the output Mariana actually sees in the Streamlit UI and the
CLI. Adds two things the raw dossier dict doesn't carry:
- A confidence indicator on the revenue projection (high / medium / low)
  with an explicit error band.
- A NETO / distributor-cut breakdown (74% / 26% of BRUTO).

Plus inline data-quality callouts for sparse-Chartmetric or legacy-catalog
artists so projections are read in context.
"""
from __future__ import annotations


def _fmt_money(v: float | int | None) -> str:
    if v is None:
        return "—"
    if v >= 1_000_000:
        return f"${v/1_000_000:.2f}M"
    if v >= 1_000:
        return f"${v/1_000:.0f}K"
    return f"${v:,.0f}"


def _fmt_int(v: int | None) -> str:
    if v is None:
        return "—"
    return f"{v:,}"


def _fmt_pct(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:+.1f}%"


def _confidence_for(profile: dict) -> tuple[str, str, float, float]:
    """Return (level, reason, lo_band, hi_band).

    Bands are multiplicative: lo=0.5 hi=2.0 means project ± 50%.
    """
    sp_listeners = profile.get("sp_monthly_listeners") or 0
    sp_followers = profile.get("sp_followers") or 0
    yt_subs = profile.get("yt_subscribers") or 0
    recent_12m = profile.get("recent_release_count_12m") or 0

    # Hard signals of low confidence first
    sparse_signals = []
    if sp_listeners < 50_000:
        sparse_signals.append("Spotify monthly listeners < 50K")
    if sp_followers < 10_000:
        sparse_signals.append("Spotify followers < 10K")
    if yt_subs == 0 and sp_listeners < 1_000_000:
        sparse_signals.append("Chartmetric reports 0 YouTube subscribers")

    if len(sparse_signals) >= 2:
        return ("Low", "; ".join(sparse_signals), 0.4, 2.5)
    if sparse_signals:
        return ("Medium", sparse_signals[0], 0.6, 1.7)

    # High-confidence band: substantial Chartmetric presence + active catalog
    if sp_listeners >= 500_000 and recent_12m > 0:
        return ("High", "active artist with strong Chartmetric coverage", 0.75, 1.4)

    return ("Medium", "moderate Chartmetric coverage", 0.65, 1.6)


def _legacy_callout(profile: dict) -> str | None:
    """If the artist is flagged as legacy/heritage catalog, surface it."""
    trend = (profile.get("career_trend") or "").lower()
    stage = (profile.get("career_stage") or "").lower()
    no_recent = (profile.get("recent_release_count_12m") or 0) == 0
    sp_listeners = profile.get("sp_monthly_listeners") or 0
    sp_followers = profile.get("sp_followers") or 0
    legacy_tier = stage in ("superstar", "mainstream")
    declining = "decline" in trend
    low_lf = (
        sp_followers > 100_000
        and sp_listeners > 0
        and (sp_listeners / sp_followers) < 2.0
    )

    if no_recent and legacy_tier and (declining or low_lf):
        return (
            "⚠️ **Legacy / heritage catalog detected.** Revenue projection "
            "assumes active distribution. Real streams are likely far lower "
            "because Chartmetric's monthly_listeners count includes passive "
            "saved tracks. Treat the number as a ceiling, not an estimate."
        )
    return None


def _render_revenue_section(dossier: dict, profile: dict) -> str:
    revenue = dossier.get("revenue_projection") or {}
    bruto = revenue.get("annual_projected") or 0
    monthly = revenue.get("monthly_total") or 0

    level, reason, lo_mult, hi_mult = _confidence_for(profile)
    bruto_lo, bruto_hi = bruto * lo_mult, bruto * hi_mult
    neto_artist = bruto * 0.74  # artist payout share
    distributor_cut = bruto * 0.26

    lines = [
        "## Total Artist Revenue Projection",
        "",
        f"**Confidence: {level}** — {reason}",
        "",
        "| Metric | Estimate | Range |",
        "|---|---|---|",
        f"| **Annual gross (BRUTO)** | {_fmt_money(bruto)} | {_fmt_money(bruto_lo)} – {_fmt_money(bruto_hi)} |",
        f"| Monthly gross | {_fmt_money(monthly)} | |",
        f"| Artist payout (~74% of gross) | {_fmt_money(neto_artist)} | {_fmt_money(neto_artist*lo_mult)} – {_fmt_money(neto_artist*hi_mult)} |",
        f"| Distributor cut if signed (~26%) | {_fmt_money(distributor_cut)} | {_fmt_money(distributor_cut*lo_mult)} – {_fmt_money(distributor_cut*hi_mult)} |",
        "",
        "*Predicts the artist's **total catalog** revenue across all platforms and "
        "all distributors — i.e. what the catalog is worth if FaroLatino had full "
        "rights. Distributor cut is what FaroLatino would actually earn under "
        "typical splits.*",
    ]

    callout = _legacy_callout(profile)
    if callout:
        lines = lines[:2] + [callout, ""] + lines[2:]

    by_platform = revenue.get("monthly_revenue_by_platform") or {}
    if by_platform:
        lines.append("")
        lines.append("**Per-platform monthly contribution (BRUTO):**")
        lines.append("")
        for plat, val in sorted(by_platform.items(), key=lambda kv: -kv[1]):
            if val < 1:
                continue
            pct = (val / monthly * 100) if monthly else 0
            lines.append(f"- {plat}: {_fmt_money(val)} ({pct:.0f}%)")

    return "\n".join(lines)


def _render_identity(dossier: dict) -> str:
    ident = dossier.get("identity") or {}
    score = dossier.get("prospect_score") or {}
    name = ident.get("name", "Unknown")
    stage = ident.get("career_stage", "")
    trend = ident.get("career_trend", "")
    label = ident.get("label") or "—"
    genres = ident.get("genres") or []
    tier = score.get("tier", "?")
    # The dossier dict re-keys the score: prospect_score.overall is the
    # numeric score (the dossier_generator's renaming). prospect_score on
    # the score-result dict (pre-dossier) is the same number. Tolerate both.
    score_val = score.get("overall", score.get("prospect_score", 0))
    confidence = score.get("confidence", 0)

    return (
        f"# {name}\n\n"
        f"**Tier: {tier}** · Prospect score: {score_val}/100 (confidence {confidence:.2f})\n\n"
        f"- Career stage: {stage} / {trend or '—'}\n"
        f"- Label: {label}\n"
        f"- Genres: {', '.join(genres[:5]) or '—'}\n"
    )


def _render_dimensions(dossier: dict) -> str:
    score = dossier.get("prospect_score") or {}
    dims = score.get("dimensions") or {}
    if not dims:
        return ""
    lines = [
        "## Dimension Breakdown",
        "",
        "| Dimension | Score | Weight | Contribution | Confidence |",
        "|---|---|---|---|---|",
    ]
    for name, d in dims.items():
        lines.append(
            f"| {name} | {d.get('score', 0):.0f} | {d.get('weight', 0):.0%} | "
            f"{d.get('weighted_contribution', 0):.1f} | {d.get('confidence', 0):.2f} |"
        )
    return "\n".join(lines)


def _render_geography(dossier: dict) -> str:
    geo = dossier.get("geographic_profile") or {}
    # dossier_generator emits geographic_profile.top_markets as the list.
    countries = geo.get("top_markets") or geo.get("top_listener_countries") or geo.get("listener_countries") or []
    if not countries:
        return ""
    lines = ["## Geographic Profile", "", "| Country | Listeners | Growth |", "|---|---|---|"]
    for c in countries[:5]:
        country = c.get("country") or c.get("country_code") or "?"
        cur = c.get("listeners", 0) or 0
        # top_markets format uses pre-rendered "growth" string; fall back to delta calc
        growth = c.get("growth")
        if growth is None:
            prev = c.get("prev_listeners", 0) or 0
            delta = ((cur - prev) / prev * 100) if prev else None
            growth = _fmt_pct(delta)
        lines.append(f"| {country} | {_fmt_int(cur)} | {growth} |")
    return "\n".join(lines)


def _render_similar(dossier: dict) -> str:
    comp = dossier.get("competitive_context") or {}
    similar = comp.get("similar_artists") or []
    if not similar:
        return "## Similar Artists\n\n*(no comparable artists surfaced — Chartmetric clustering and genre-search both empty)*"
    lines = ["## Similar Artists", "", "| Artist | Country | Listeners | Stage | Source |", "|---|---|---|---|---|"]
    for s in similar[:10]:
        lines.append(
            f"| {s.get('name', '?')} | {s.get('country_code', '—')} | "
            f"{_fmt_int(s.get('sp_monthly_listeners'))} | "
            f"{s.get('career_stage') or '—'} | "
            f"{s.get('_similarity_source') or s.get('source', '—')} |"
        )
    return "\n".join(lines)


def _render_catalog(dossier: dict) -> str:
    cat = dossier.get("catalog") or {}
    if not cat:
        return ""
    lines = [
        "## Catalog",
        "",
        f"- Tracks (last 6m): **{cat.get('releases_6m', 0)}**",
        f"- Tracks (last 12m): {cat.get('releases_12m', 0)}",
        f"- Total tracks: {cat.get('total_tracks', '—')}",
    ]
    return "\n".join(lines)


def _render_risks(dossier: dict) -> str:
    risks = dossier.get("risk_signals") or {}
    if not risks:
        return ""
    lines = ["## Risk Signals", ""]
    for k, v in risks.items():
        if v:
            lines.append(f"- **{k.replace('_', ' ').title()}**: {v}")
    if len(lines) <= 2:
        return ""
    return "\n".join(lines)


def _render_actionable(dossier: dict) -> str:
    act = dossier.get("actionable") or {}
    if not act:
        return ""
    tier = act.get("tier", "?")
    return (
        "## Action\n\n"
        f"**Tier: {tier}**\n\n"
        "Use `/evaluate {name}` to drill in further, `/similar {name}` to map "
        "the competitive landscape, or `/compare {a} {b}` to put two prospects side-by-side."
    )


def render_dossier(dossier: dict, profile: dict) -> str:
    """Render the full dossier as Markdown.

    `dossier` is the dict returned by `generate_dossier`.
    `profile` is the original ArtistProfile dict (used for confidence
    indicator inputs).
    """
    sections = [
        _render_identity(dossier),
        _render_revenue_section(dossier, profile),
        _render_dimensions(dossier),
        _render_geography(dossier),
        _render_catalog(dossier),
        _render_similar(dossier),
        _render_risks(dossier),
        _render_actionable(dossier),
    ]
    return "\n\n".join(s for s in sections if s)
