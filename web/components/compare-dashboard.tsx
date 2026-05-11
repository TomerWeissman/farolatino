"use client";

// /compare — overlay-style two-artist comparison.
//
// Two text inputs at top (Artist A / Artist B). Fires POST /api/evaluate
// for each in parallel; loading + disambiguation states are independent
// per side so one slow lookup doesn't block the other. Once both
// resolve, renders a vertical stack of overlaid bar charts — each row
// has the dimension label, value A, an overlaid bar (A in tier accent,
// B in a secondary accent), value B.
//
// No new backend endpoint: this is purely a frontend assembly of two
// /api/evaluate responses. Cache hits on either side make the
// comparison effectively instant after the first cold lookup.

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { evaluate } from "@/lib/api";
import { useT } from "@/lib/i18n/context";
import { TIER_COLOR, formatInt, formatMoney } from "@/lib/format";
import type { DisambigCandidate, Dossier, EvaluateResponse } from "@/lib/types";

// Per-side state. Each slot evolves independently of the other.
type SideState =
  | { kind: "empty" }
  | { kind: "loading"; artist: string }
  | { kind: "disambig"; query: string; candidates: DisambigCandidate[] }
  | { kind: "error"; message: string }
  | { kind: "loaded"; artist: string; cm_id: number; dossier: Dossier };

// One row in the comparison stack — formatter + extractor per dimension.
type Dim = {
  key: string;
  // i18n key for the row's label (without "compare.dim." prefix); appended below.
  labelKey: string;
  // Pull the raw numeric value from a dossier. null = missing data.
  get: (d: Dossier) => number | null;
  // Render the value for display next to the bar.
  fmt: (n: number) => string;
  // When true, smaller numbers are "better" (e.g., release cadence days
  // — fewer days between drops = more active). The bar still sizes by
  // value/max(a,b) so the visual is correct; this flag lets us label the
  // dimension with the right framing.
  lowerIsBetter?: boolean;
};

const DIMENSIONS: Dim[] = [
  { key: "score", labelKey: "compare.dim.score",
    get: (d) => d.prospect_score?.overall ?? null,
    fmt: (n) => `${Math.round(n)}/100` },
  { key: "sp_listeners", labelKey: "compare.dim.sp_listeners",
    get: (d) => d.metrics?.spotify?.monthly_listeners ?? null,
    fmt: formatInt },
  { key: "sp_followers", labelKey: "compare.dim.sp_followers",
    get: (d) => d.metrics?.spotify?.followers ?? null,
    fmt: formatInt },
  { key: "yt_subs", labelKey: "compare.dim.yt_subs",
    get: (d) => d.metrics?.youtube?.subscribers ?? null,
    fmt: formatInt },
  { key: "yt_views", labelKey: "compare.dim.yt_views",
    get: (d) => d.metrics?.youtube?.views ?? null,
    fmt: formatInt },
  { key: "ig_followers", labelKey: "compare.dim.ig_followers",
    get: (d) => d.metrics?.instagram?.followers ?? null,
    fmt: formatInt },
  { key: "tt_followers", labelKey: "compare.dim.tt_followers",
    get: (d) => d.metrics?.tiktok?.followers ?? null,
    fmt: formatInt },
  { key: "revenue", labelKey: "compare.dim.revenue",
    get: (d) => d.revenue_projection?.annual_projected ?? null,
    fmt: formatMoney },
  { key: "sp_cadence", labelKey: "compare.dim.sp_cadence", lowerIsBetter: true,
    get: (d) => d.content_velocity?.spotify?.cadence_days ?? null,
    fmt: (n) => `${Math.round(n)}d` },
  { key: "yt_avg_views", labelKey: "compare.dim.yt_avg_views",
    get: (d) => d.content_velocity?.youtube?.avg_views_recent_3 ?? null,
    fmt: formatInt },
  { key: "releases_12m", labelKey: "compare.dim.releases_12m",
    get: (d) => d.catalog?.releases_12m ?? null,
    fmt: (n) => `${Math.round(n)}` },
];

// Artist B uses a secondary accent across all tier colors so the
// overlay bars are visually distinct from A's tier-accent.
const SECONDARY_ACCENT = "#a855f7"; // purple — far from any tier color

export function CompareDashboard() {
  const t = useT();
  const searchParams = useSearchParams();
  const [draftA, setDraftA] = useState("");
  const [draftB, setDraftB] = useState("");
  const [sideA, setSideA] = useState<SideState>({ kind: "empty" });
  const [sideB, setSideB] = useState<SideState>({ kind: "empty" });

  // Pre-populate from URL params: ?primary=A&primary_cm_id=X&secondary=B&secondary_cm_id=Y.
  // The cm_id params skip the search step on each side (mirrors the
  // /evaluate pattern). Used by the future compare-pill chat handoff
  // and by the /evaluate "Compare to another artist" CTA.
  useEffect(() => {
    const a = searchParams.get("primary");
    const b = searchParams.get("secondary");
    const aId = searchParams.get("primary_cm_id");
    const bId = searchParams.get("secondary_cm_id");
    if (a) {
      setDraftA(a);
      void runSide("A", a, aId ? Number(aId) : undefined);
    }
    if (b) {
      setDraftB(b);
      void runSide("B", b, bId ? Number(bId) : undefined);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const runSide = useCallback(async (side: "A" | "B", artist: string, cmId?: number) => {
    if (!artist.trim()) return;
    const setter = side === "A" ? setSideA : setSideB;
    setter({ kind: "loading", artist });
    try {
      const r: EvaluateResponse = await evaluate(artist, cmId);
      if ("error" in r && r.error) {
        setter({ kind: "error", message: r.error });
        return;
      }
      if ("needs_disambiguation" in r && r.needs_disambiguation) {
        setter({ kind: "disambig", query: r.query, candidates: r.needs_disambiguation });
        return;
      }
      if ("dossier" in r && r.dossier) {
        setter({
          kind: "loaded",
          artist: r.dossier.identity.name,
          cm_id: r.cm_id,
          dossier: r.dossier,
        });
      }
    } catch (e) {
      setter({ kind: "error", message: e instanceof Error ? e.message : "Network error" });
    }
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (draftA.trim()) void runSide("A", draftA.trim());
    if (draftB.trim()) void runSide("B", draftB.trim());
  };

  // Show the comparison only when BOTH sides are loaded. Until then, the
  // per-side state UI tells the user what's happening on each side.
  const bothLoaded = sideA.kind === "loaded" && sideB.kind === "loaded";

  return (
    <div className="evaluate-shell">
      <header className="evaluate-header">
        <div className="evaluate-eyebrow">{t("compare.eyebrow")}</div>
        <form onSubmit={handleSubmit} className="cmp-search">
          <input
            type="text"
            value={draftA}
            onChange={(e) => setDraftA(e.target.value)}
            placeholder={t("compare.placeholder_a")}
            className="evaluate-input"
            disabled={sideA.kind === "loading"}
          />
          <span className="cmp-vs">{t("compare.vs")}</span>
          <input
            type="text"
            value={draftB}
            onChange={(e) => setDraftB(e.target.value)}
            placeholder={t("compare.placeholder_b")}
            className="evaluate-input"
            disabled={sideB.kind === "loading"}
          />
          <button
            type="submit"
            className="evaluate-btn evaluate-btn-primary"
            disabled={(!draftA.trim() && !draftB.trim())
              || sideA.kind === "loading"
              || sideB.kind === "loading"}
          >
            {t("compare.search_button")}
          </button>
        </form>
      </header>

      {/* Per-side status panels. Stack vertically when not both loaded. */}
      {!bothLoaded && (
        <div className="cmp-side-status-grid">
          <SideStatus side="A" state={sideA} onPick={(id, name) => { setDraftA(name); void runSide("A", name, id); }} />
          <SideStatus side="B" state={sideB} onPick={(id, name) => { setDraftB(name); void runSide("B", name, id); }} />
        </div>
      )}

      {bothLoaded && sideA.kind === "loaded" && sideB.kind === "loaded" && (
        <ComparisonView a={sideA} b={sideB} />
      )}
    </div>
  );
}


function SideStatus({
  side,
  state,
  onPick,
}: {
  side: "A" | "B";
  state: SideState;
  onPick: (cmId: number, name: string) => void;
}) {
  const t = useT();
  if (state.kind === "empty") {
    return (
      <div className="cmp-side cmp-side-empty">
        <div className="cmp-side-label">{side}</div>
        <div className="cmp-side-empty-hint">{t("compare.side_empty_hint")}</div>
      </div>
    );
  }
  if (state.kind === "loading") {
    return (
      <div className="cmp-side cmp-side-loading">
        <div className="cmp-side-label">{side}</div>
        <span className="evaluate-spinner" aria-hidden="true" />
        <div>{t("eval.loading.title", { artist: state.artist })}</div>
      </div>
    );
  }
  if (state.kind === "disambig") {
    return (
      <div className="cmp-side cmp-side-disambig">
        <div className="cmp-side-label">{side}</div>
        <div className="cmp-side-disambig-title">
          {t("eval.disambig.title", { query: state.query })}
        </div>
        {state.candidates.map((c) => (
          <button
            key={c.cm_id}
            type="button"
            className="cmp-disambig-row"
            onClick={() => onPick(c.cm_id, c.name)}
          >
            <strong>{c.name}</strong>
            <span className="cmp-disambig-meta">
              {(c.country_code ?? c.code2 ?? "—")} ·{" "}
              {c.sp_monthly_listeners
                ? `${formatInt(c.sp_monthly_listeners)} ${t("eval.disambig.monthly_listeners")}`
                : t("eval.disambig.no_streaming")}
            </span>
          </button>
        ))}
      </div>
    );
  }
  if (state.kind === "error") {
    return (
      <div className="cmp-side cmp-side-error">
        <div className="cmp-side-label">{side}</div>
        <div>{state.message}</div>
      </div>
    );
  }
  // loaded — show a compact "ready" card; the actual comparison is
  // rendered separately by ComparisonView once both sides are loaded.
  return (
    <div className="cmp-side cmp-side-ready">
      <div className="cmp-side-label">{side}</div>
      <div className="cmp-side-ready-name">{state.artist}</div>
      <div className="cmp-side-ready-tier">
        {state.dossier.prospect_score.tier} · {Math.round(state.dossier.prospect_score.overall)}/100
      </div>
    </div>
  );
}


function ComparisonView({
  a,
  b,
}: {
  a: Extract<SideState, { kind: "loaded" }>;
  b: Extract<SideState, { kind: "loaded" }>;
}) {
  const t = useT();
  const accentA = TIER_COLOR[a.dossier.prospect_score.tier?.toUpperCase() ?? ""] ?? "#1a1a1a";
  const accentB = SECONDARY_ACCENT;

  return (
    <article className="evaluate-column">
      <CompareHeader a={a} b={b} accentA={accentA} accentB={accentB} />

      <section className="ev-section">
        <h2 className="ev-h2">{t("compare.dimensions_title")}</h2>
        {DIMENSIONS.map((dim) => (
          <CompareRow
            key={dim.key}
            dim={dim}
            valA={dim.get(a.dossier)}
            valB={dim.get(b.dossier)}
            accentA={accentA}
            accentB={accentB}
          />
        ))}
      </section>

      <section className="ev-section">
        <h2 className="ev-h2">{t("compare.scoring_title")}</h2>
        <ScoringCompare a={a.dossier} b={b.dossier} accentA={accentA} accentB={accentB} />
      </section>

      <div className="ev-source">{t("compare.source")}</div>
    </article>
  );
}


function CompareHeader({
  a, b, accentA, accentB,
}: {
  a: Extract<SideState, { kind: "loaded" }>;
  b: Extract<SideState, { kind: "loaded" }>;
  accentA: string;
  accentB: string;
}) {
  return (
    <header className="ev-section ev-hero cmp-header">
      <div className="cmp-header-side" style={{ borderColor: accentA }}>
        <PhotoOrInitials name={a.artist} image={a.dossier.identity.image} />
        <h2 className="cmp-header-name">{a.artist}</h2>
        <div className="cmp-header-tier" style={{ color: accentA }}>
          {a.dossier.prospect_score.tier} · {Math.round(a.dossier.prospect_score.overall)}/100
        </div>
      </div>
      <div className="cmp-header-vs">vs</div>
      <div className="cmp-header-side" style={{ borderColor: accentB }}>
        <PhotoOrInitials name={b.artist} image={b.dossier.identity.image} />
        <h2 className="cmp-header-name">{b.artist}</h2>
        <div className="cmp-header-tier" style={{ color: accentB }}>
          {b.dossier.prospect_score.tier} · {Math.round(b.dossier.prospect_score.overall)}/100
        </div>
      </div>
    </header>
  );
}


function PhotoOrInitials({ name, image }: { name: string; image?: string | null }) {
  const initials = name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((s) => s[0]?.toUpperCase() ?? "")
    .join("") || "?";
  if (image) {
    return (
      <img
        className="cmp-header-photo"
        src={image}
        alt={name}
        onError={(e) => {
          const t = e.target as HTMLImageElement;
          const fb = document.createElement("div");
          fb.className = "cmp-header-photo cmp-header-photo-fallback";
          fb.textContent = initials;
          t.replaceWith(fb);
        }}
      />
    );
  }
  return <div className="cmp-header-photo cmp-header-photo-fallback">{initials}</div>;
}


function CompareRow({
  dim, valA, valB, accentA, accentB,
}: {
  dim: Dim;
  valA: number | null;
  valB: number | null;
  accentA: string;
  accentB: string;
}) {
  const t = useT();
  const max = Math.max(valA ?? 0, valB ?? 0);
  // Both null = nothing to compare. Render an empty row marker for
  // transparency; user can see we did try to pull this dimension.
  const widthA = max > 0 && valA != null ? (valA / max) * 100 : 0;
  const widthB = max > 0 && valB != null ? (valB / max) * 100 : 0;
  const label = t(dim.labelKey);
  return (
    <div className="cmp-bar-row">
      <div className="cmp-bar-label">{label}</div>
      <div className="cmp-bar-value cmp-bar-value-a">
        {valA != null ? dim.fmt(valA) : "—"}
      </div>
      <div className="cmp-overlay-bar">
        <span className="cmp-bar-a" style={{ width: `${widthA}%`, background: accentA }} />
        <span className="cmp-bar-b" style={{ width: `${widthB}%`, background: accentB }} />
      </div>
      <div className="cmp-bar-value cmp-bar-value-b">
        {valB != null ? dim.fmt(valB) : "—"}
      </div>
    </div>
  );
}


function ScoringCompare({
  a, b, accentA, accentB,
}: {
  a: Dossier;
  b: Dossier;
  accentA: string;
  accentB: string;
}) {
  // Union of dimension names across both dossiers — same dim should
  // be present in both, but be defensive.
  const dimNames = Array.from(
    new Set([
      ...Object.keys(a.prospect_score.dimensions ?? {}),
      ...Object.keys(b.prospect_score.dimensions ?? {}),
    ])
  );
  return (
    <>
      {dimNames.map((name) => {
        const sa = a.prospect_score.dimensions?.[name]?.score ?? null;
        const sb = b.prospect_score.dimensions?.[name]?.score ?? null;
        const label = name.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
        // Scores are bounded 0-100, so use 100 as the denominator
        // rather than max(a,b) — keeps the bars comparable across
        // dimensions (an 80 always looks bigger than a 40).
        return (
          <div key={name} className="cmp-bar-row">
            <div className="cmp-bar-label">{label}</div>
            <div className="cmp-bar-value cmp-bar-value-a">
              {sa != null ? Math.round(sa) : "—"}
            </div>
            <div className="cmp-overlay-bar">
              {sa != null && (
                <span className="cmp-bar-a" style={{ width: `${Math.min(100, sa)}%`, background: accentA }} />
              )}
              {sb != null && (
                <span className="cmp-bar-b" style={{ width: `${Math.min(100, sb)}%`, background: accentB }} />
              )}
            </div>
            <div className="cmp-bar-value cmp-bar-value-b">
              {sb != null ? Math.round(sb) : "—"}
            </div>
          </div>
        );
      })}
    </>
  );
}
