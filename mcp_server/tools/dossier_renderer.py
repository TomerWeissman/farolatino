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


def render_similar(result: dict) -> str:
    """Render the ``find_similar_artists`` output as canonical Markdown.

    ``result`` is the dict from ``composite_similar.find_similar_artists``:
    ``{"seed": {...}, "neighbors": [...], "tier_distribution": {...}}``.
    Output mirrors the dossier's tone — header + seed line + tier rollup
    + a sortable table — so chat output is identical regardless of LLM
    provider.
    """
    seed = result.get("seed") or {}
    neighbors = result.get("neighbors") or []
    bands = result.get("tier_distribution") or {}
    seed_name = seed.get("name") or "—"

    lines: list[str] = [f"# Similar to {seed_name}"]

    # Seed summary line — the user wants quick "what was the seed like"
    # context without scrolling up to find the prior @evaluate.
    seed_bits = []
    if seed.get("career_stage"):
        seed_bits.append(f"_{seed['career_stage']}_")
    if seed.get("country_code"):
        seed_bits.append(seed["country_code"])
    listeners = seed.get("sp_monthly_listeners")
    if listeners:
        seed_bits.append(f"{_fmt_int(listeners)} monthly listeners")
    genres = seed.get("genres") or []
    if genres:
        seed_bits.append(", ".join(genres[:3]))
    if seed_bits:
        lines.append(" · ".join(seed_bits))

    if not neighbors:
        lines.append(
            "\n_No neighbors returned._ Chartmetric's similar-artists graph "
            "doesn't have data for this seed yet — try @similar on a more "
            "established artist, or @evaluate first to confirm the seed resolved."
        )
        return "\n\n".join(lines)

    # Tier rollup — surfaces the comp question fast: "are these peers,
    # ladder-down, or ladder-up?" Skipping zero buckets keeps it lean.
    tier_bits = []
    for k in ("tier-similar", "larger", "smaller", "unknown"):
        if bands.get(k, 0):
            label = {
                "tier-similar": "tier peers",
                "larger": "larger",
                "smaller": "smaller",
                "unknown": "unknown",
            }[k]
            tier_bits.append(f"**{bands[k]}** {label}")
    if tier_bits:
        lines.append("**Mix:** " + " · ".join(tier_bits))

    # Table — name, country, tier band, monthly listeners, signed flag.
    # signed=False means available to chase, so we surface it boldly.
    lines.append(
        "\n| # | Artist | Country | Tier | Monthly listeners | Signed |"
    )
    lines.append("|---|---|---|---|---|---|")
    for i, n in enumerate(neighbors, start=1):
        signed_mark = "—" if n.get("signed") is None else ("yes" if n.get("signed") else "**no**")
        lines.append(
            "| {i} | {name} | {country} | {tier} | {listeners} | {signed} |".format(
                i=i,
                name=n.get("name") or "—",
                country=n.get("country_code") or "—",
                tier=n.get("tier_band") or "—",
                listeners=_fmt_int(n.get("sp_monthly_listeners")),
                signed=signed_mark,
            )
        )

    return "\n".join(lines)


def render_dossier(dossier: dict, profile: dict) -> str:
    """Render the full dossier as Markdown — Option B "stat-card" format.

    Optimized for at-a-glance scanning + side-by-side artist comparison.
    Big score + tier at top, dense data tables with bar-chart visuals
    for scoring dimensions, single recommendation callout at the
    bottom. Closes with a "Ask follow-up questions" invitation so the
    user knows the chat picks up from here.

    The shape is deliberately deterministic — same bytes regardless
    of LLM provider — but the user can ask any free-form question
    after the dossier renders and the LLM will answer based on the
    full dossier context (Phase 1's message-history replay carries it).
    """
    sections = [
        _b_header(dossier),
        _b_streaming_audience(dossier),
        _b_revenue(dossier, profile),
        _b_scoring(dossier),
        _b_geographic(dossier),
        _b_catalog(dossier),
        _b_comps(dossier),
        _b_risks(dossier),
        _b_recommendation(dossier),
        _b_followup_invite(),
    ]
    return "\n\n".join(s for s in sections if s)


# ─── Option B sections ──────────────────────────────────────────────
#
# Each section is self-contained, returns "" when there's no data so
# the section is skipped. Output renders cleanly under remarkGfm
# (the React Markdown renderer the chat UI uses).


def _b_header(dossier: dict) -> str:
    """Big name + score + one-line context. The first thing the user sees."""
    ident = dossier.get("identity") or {}
    score = dossier.get("prospect_score") or {}
    name = ident.get("name") or "Unknown"
    stage = ident.get("career_stage") or "—"
    trend = ident.get("career_trend") or "—"
    label = ident.get("label") or "—"
    genres = ident.get("genres") or []
    score_val = score.get("overall", 0)
    tier = score.get("tier") or "?"
    confidence = score.get("confidence", 0)

    # Top genre tag is enough — full list is data-dense without adding insight.
    primary_genre = genres[0] if genres else None

    parts = [
        f"# {name}",
        f"## **{score_val}**/100 · **{tier}** · confidence {confidence:.0%}",
    ]

    context_bits = [f"_{stage} / {trend}_"] if stage != "—" else []
    if label and label != "—":
        context_bits.append(f"signed to **{label}**")
    if primary_genre:
        context_bits.append(primary_genre)
    if context_bits:
        parts.append(" · ".join(context_bits))

    return "\n".join(parts)


def _b_streaming_audience(dossier: dict) -> str:
    """Platform reach in one table. The headline numbers."""
    metrics = dossier.get("metrics") or {}
    sp = metrics.get("spotify") or {}
    yt = metrics.get("youtube") or {}
    ig = metrics.get("instagram") or {}
    tt = metrics.get("tiktok") or {}

    sp_listeners = sp.get("monthly_listeners") or 0
    sp_change = sp.get("monthly_listeners_change") or ""
    sp_followers = sp.get("followers") or 0
    yt_subs = yt.get("subscribers") or 0
    yt_views = yt.get("views") or 0
    ig_followers = ig.get("followers") or 0
    ig_engagement = ig.get("engagement_rate") or ""
    tt_followers = tt.get("followers") or 0

    if not any([sp_listeners, yt_subs, ig_followers, tt_followers]):
        return ""

    lines = ["## Reach", "", "| Platform | Audience | Detail |", "|---|---|---|"]
    if sp_listeners:
        change_suffix = f" ({sp_change})" if sp_change else ""
        lines.append(
            f"| Spotify | **{_fmt_int(sp_listeners)}** monthly listeners{change_suffix} | "
            f"{_fmt_int(sp_followers)} followers |"
        )
    if yt_subs:
        lines.append(
            f"| YouTube | **{_fmt_int(yt_subs)}** subscribers | "
            f"{_fmt_int(yt_views)} total views |"
        )
    if ig_followers:
        eng_suffix = f" · engagement {ig_engagement}" if ig_engagement else ""
        lines.append(f"| Instagram | **{_fmt_int(ig_followers)}** followers{eng_suffix} | |")
    if tt_followers:
        lines.append(f"| TikTok | **{_fmt_int(tt_followers)}** followers | |")

    return "\n".join(lines)


def _b_revenue(dossier: dict, profile: dict) -> str:
    """Annual gross + distributor cut. Uses the existing
    revenue-section helper since it's already battle-tested."""
    return _render_revenue_section(dossier, profile)


def _b_scoring(dossier: dict) -> str:
    """Score breakdown with inline bar-chart visuals.

    Sorted descending so strongest dimensions land first — readers
    scan top-to-bottom and the order tells the strength story.
    Rationale text is included as the third column so the user
    doesn't have to ask "why is content_velocity 32?".
    """
    score = dossier.get("prospect_score") or {}
    dims = score.get("dimensions") or {}
    if not dims:
        return ""

    # Sort by score descending so the strongest dimensions read first.
    rows = sorted(dims.items(), key=lambda kv: -(kv[1].get("score", 0)))

    lines = [
        "## Scoring",
        "",
        "| Dimension | Score | Why |",
        "|---|---|---|",
    ]
    for raw_name, d in rows:
        # "geographic_fit" → "Geographic fit"
        name = raw_name.replace("_", " ").capitalize()
        s = d.get("score", 0)
        rationale = (d.get("rationale") or "").strip()
        # Trim verbose rationales — first sentence is enough at a glance.
        if rationale:
            first_sentence = rationale.split(". ")[0].rstrip(".")
            if len(first_sentence) > 90:
                first_sentence = first_sentence[:87].rstrip() + "…"
            rationale_short = first_sentence
        else:
            rationale_short = "—"
        bar = _bar_chart(s, width=10)
        lines.append(f"| {name} | `{bar}` **{s:.0f}** | {rationale_short} |")

    return "\n".join(lines)


def _b_geographic(dossier: dict) -> str:
    """Top markets — short list, growth signal."""
    geo = dossier.get("geographic_profile") or {}
    countries = geo.get("top_markets") or []
    if not countries:
        return ""

    lines = ["## Top markets", "", "| Country | Listeners | Growth |", "|---|---|---|"]
    for c in countries[:5]:
        country = c.get("country") or c.get("country_code") or "?"
        cur = c.get("listeners", 0) or 0
        growth = c.get("growth")
        if growth is None:
            prev = c.get("prev_listeners", 0) or 0
            delta = ((cur - prev) / prev * 100) if prev else None
            growth = _fmt_pct(delta)
        lines.append(f"| {country} | {_fmt_int(cur)} | {growth} |")
    return "\n".join(lines)


def _b_catalog(dossier: dict) -> str:
    """Catalog activity — recent releases vs total. One-line."""
    cat = dossier.get("catalog") or {}
    if not cat:
        return ""
    r6 = cat.get("releases_6m", 0)
    r12 = cat.get("releases_12m", 0)
    total = cat.get("total_tracks") or "—"
    return (
        "## Catalog\n\n"
        f"**{r6}** releases in last 6 months · **{r12}** in last 12 months · "
        f"**{total}** tracks total"
    )


def _b_comps(dossier: dict) -> str:
    """Comparable artists as an inline list — one line per artist
    with country + size context. Capped at 5 to stay scannable.
    """
    comp = dossier.get("competitive_context") or {}
    similar = comp.get("similar_artists") or []
    if not similar:
        return ""
    lines = ["## Similar artists (tier-similar)"]
    for s in similar[:5]:
        name = s.get("name") or "?"
        country = s.get("country_code") or "—"
        listeners = s.get("sp_monthly_listeners")
        bits = [country]
        if listeners:
            bits.append(f"{_fmt_int(listeners)} monthly")
        lines.append(f"- **{name}** ({' · '.join(bits)})")
    return "\n".join(lines)


def _b_risks(dossier: dict) -> str:
    """Risk callouts. Skip the section if nothing to flag — silence is
    a useful signal."""
    risks = dossier.get("risk_signals") or {}
    flagged = [(k, v) for k, v in risks.items() if v]
    if not flagged:
        return ""
    lines = ["## Risk signals", ""]
    for k, v in flagged:
        lines.append(f"- ⚠️ **{k.replace('_', ' ').title()}** — {v}")
    return "\n".join(lines)


def _b_recommendation(dossier: dict) -> str:
    """Single sentence verdict at the bottom. Action-first, the thing
    the A&R team carries forward to their next decision."""
    act = dossier.get("actionable") or {}
    score = dossier.get("prospect_score") or {}
    tier = act.get("tier") or score.get("tier") or "?"
    ident = dossier.get("identity") or {}
    label = ident.get("label")
    stage = (ident.get("career_stage") or "").lower()

    # Tier-driven default text. Each line is the "what to do next"
    # phrased as an instruction, not a description.
    body_by_tier = {
        "BUY": "Active outreach. Lead profile in this tier — push to PROSPECT pipeline.",
        "PROSPECT": "Schedule a deeper look this week. Strong signals, watching for momentum confirmation.",
        "WATCH": "Re-check quarterly. Holding pattern — signals not yet strong enough to chase.",
        "PASS": "Skip. Not a fit on current criteria.",
    }
    body = body_by_tier.get(tier.upper(), "Re-check next cycle.")

    # Add a label-specific addendum if they're already locked.
    if tier.upper() in ("WATCH", "PASS") and label and stage in ("superstar", "mainstream"):
        body += f" Currently signed to **{label}** — no signing window unless contract status shifts."

    return f"## Recommendation\n\n**{tier}.** {body}"


def _b_followup_invite() -> str:
    """Invite the user to ask follow-up questions. Phase 1's message-
    history replay means the LLM gets the full dossier as context on
    the next turn — they can ask anything about the artist and get a
    grounded answer.
    """
    return (
        "---\n\n"
        "_Ask a follow-up about catalog, momentum, comps, or risk signals — "
        "e.g._ `is his catalog mostly evergreen or hit-driven?` _·_ "
        "`who in his tier is unsigned?` _·_ `what's his TikTok presence like?`"
    )


def _bar_chart(value: float, width: int = 10) -> str:
    """Unicode block bar chart for a 0-100 score.

    Uses U+2588 (full block) for filled, U+2591 (light shade) for
    empty. Renders as monospace inside Markdown table cells when
    wrapped in backticks.
    """
    filled = max(0, min(width, round(value / 100 * width)))
    return "█" * filled + "░" * (width - filled)
