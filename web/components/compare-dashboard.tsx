"use client";

// /compare — two-artist comparison via twin radar charts (v0.5.2).
//
// Two text inputs at top (Artist A / Artist B). Fires POST /api/evaluate
// for each in parallel; loading + disambiguation states are independent
// per side so one slow lookup doesn't block the other. Once both
// resolve, renders two radar charts:
//
//   - REACH (6 platform metrics, each axis scaled to max(a,b))
//   - PERFORMANCE (7 scoring dimensions, each axis on 0-100)
//
// Each artist contributes a colored polygon to both radars. Artist A
// in tier-accent color; Artist B in a contrasting purple. A small data
// table below each radar shows the exact values + the delta — the
// shapes give a fast read, the table answers "how much".
//
// The input UX mirrors /evaluate: photos + initials on disambig
// candidates, elapsed-seconds spinner during loading, structured error.

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { evaluate } from "@/lib/api";
import { useT } from "@/lib/i18n/context";
import { TIER_COLOR, formatInt, formatMoney } from "@/lib/format";
import type { DisambigCandidate, Dossier, EvaluateResponse } from "@/lib/types";
import { RadarChart, type RadarDim } from "@/components/radar-chart";

type SideState =
  | { kind: "empty" }
  | { kind: "loading"; artist: string }
  | { kind: "disambig"; query: string; candidates: DisambigCandidate[] }
  | { kind: "error"; message: string; artist: string }
  | { kind: "loaded"; artist: string; cm_id: number; dossier: Dossier };

// Artist B's color across all tier accents — chosen to be visually
// distinct from any TIER_COLOR (orange / blue / green / gray).
const SECONDARY_ACCENT = "#a855f7";

// Reach radar — six platform-presence axes, normalized per-axis to
// max(a, b) so the bigger artist always touches the outer ring.
const REACH_DIMS: Array<{
  labelKey: string;
  fmt: (n: number) => string;
  get: (d: Dossier) => number | null;
}> = [
  { labelKey: "compare.dim.sp_listeners", fmt: formatInt, get: (d) => d.metrics?.spotify?.monthly_listeners ?? null },
  { labelKey: "compare.dim.sp_followers", fmt: formatInt, get: (d) => d.metrics?.spotify?.followers ?? null },
  { labelKey: "compare.dim.yt_subs",      fmt: formatInt, get: (d) => d.metrics?.youtube?.subscribers ?? null },
  { labelKey: "compare.dim.yt_views",     fmt: formatInt, get: (d) => d.metrics?.youtube?.views ?? null },
  { labelKey: "compare.dim.tt_followers", fmt: formatInt, get: (d) => d.metrics?.tiktok?.followers ?? null },
  { labelKey: "compare.dim.ig_followers", fmt: formatInt, get: (d) => d.metrics?.instagram?.followers ?? null },
];


export function CompareDashboard() {
  const t = useT();
  const searchParams = useSearchParams();
  const [draftA, setDraftA] = useState("");
  const [draftB, setDraftB] = useState("");
  const [sideA, setSideA] = useState<SideState>({ kind: "empty" });
  const [sideB, setSideB] = useState<SideState>({ kind: "empty" });

  const runSide = useCallback(async (side: "A" | "B", artist: string, cmId?: number) => {
    if (!artist.trim()) return;
    const setter = side === "A" ? setSideA : setSideB;
    setter({ kind: "loading", artist });
    try {
      const r: EvaluateResponse = await evaluate(artist, cmId);
      if ("error" in r && r.error) {
        setter({ kind: "error", message: r.error, artist });
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
      setter({ kind: "error", message: e instanceof Error ? e.message : "Network error", artist });
    }
  }, []);

  // Pre-populate from URL: ?primary=A&primary_cm_id=X&secondary=B&secondary_cm_id=Y
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
  }, [searchParams, runSide]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (draftA.trim()) void runSide("A", draftA.trim());
    if (draftB.trim()) void runSide("B", draftB.trim());
  };

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

      {!bothLoaded && (
        <div className="cmp-side-status-grid">
          <SideStatus
            side="A"
            state={sideA}
            onPick={(id, name) => { setDraftA(name); void runSide("A", name, id); }}
            onRetry={(name) => void runSide("A", name)}
          />
          <SideStatus
            side="B"
            state={sideB}
            onPick={(id, name) => { setDraftB(name); void runSide("B", name, id); }}
            onRetry={(name) => void runSide("B", name)}
          />
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
  onRetry,
}: {
  side: "A" | "B";
  state: SideState;
  onPick: (cmId: number, name: string) => void;
  onRetry: (artist: string) => void;
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
    return <SideLoading side={side} artist={state.artist} />;
  }
  if (state.kind === "disambig") {
    return (
      <div className="cmp-side cmp-side-disambig">
        <div className="cmp-side-label">{side}</div>
        <div className="cmp-side-disambig-title">
          {t("eval.disambig.title", { query: state.query })}
        </div>
        <div className="cmp-side-disambig-hint">{t("eval.disambig.hint")}</div>
        {state.candidates.map((c) => (
          <DisambigRow key={c.cm_id} c={c} onPick={onPick} />
        ))}
      </div>
    );
  }
  if (state.kind === "error") {
    return (
      <div className="cmp-side cmp-side-error">
        <div className="cmp-side-label">{side}</div>
        <div className="cmp-side-error-title">
          {t("eval.error.title", { artist: state.artist })}
        </div>
        <div className="cmp-side-error-message">{state.message}</div>
        <button
          type="button"
          className="evaluate-btn evaluate-btn-secondary"
          onClick={() => onRetry(state.artist)}
        >
          {t("eval.error.retry")}
        </button>
      </div>
    );
  }
  // loaded — show a compact "ready" card
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


function SideLoading({ side, artist }: { side: "A" | "B"; artist: string }) {
  const t = useT();
  // Elapsed seconds — same UX as /evaluate's LoadingState. Resets per
  // mount because the component remounts when the artist changes.
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(id);
  }, []);
  return (
    <div className="cmp-side cmp-side-loading">
      <div className="cmp-side-label">{side}</div>
      <div className="cmp-side-loading-head">
        <span className="evaluate-spinner" aria-hidden="true" />
        <div className="cmp-side-loading-title">
          {t("eval.loading.title", { artist })}
          {elapsed >= 3 && <span className="evaluate-loading-elapsed"> · {elapsed}s</span>}
        </div>
      </div>
      <div className="evaluate-loading-steps cmp-side-loading-steps">
        <div>{t("eval.loading.step.lookup")}</div>
        <div>{t("eval.loading.step.pull")}</div>
        <div>{t("eval.loading.step.score")}</div>
      </div>
    </div>
  );
}


function DisambigRow({
  c,
  onPick,
}: {
  c: DisambigCandidate;
  onPick: (cmId: number, name: string) => void;
}) {
  const t = useT();
  const country = c.country_code ?? c.code2 ?? "—";
  const initials = c.name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((s) => s[0]?.toUpperCase() ?? "")
    .join("") || "?";
  const listenersLbl = c.sp_monthly_listeners
    ? t("eval.disambig.monthly_listeners")
    : t("eval.disambig.spotify_followers");
  const listeners = c.sp_monthly_listeners ?? c.sp_followers ?? 0;
  return (
    <button
      type="button"
      className="cmp-disambig-row"
      onClick={() => onPick(c.cm_id, c.name)}
    >
      {c.image_url ? (
        <img
          src={c.image_url}
          alt={c.name}
          className="cmp-disambig-photo"
          onError={(e) => {
            const tgt = e.currentTarget;
            const fb = document.createElement("div");
            fb.className = "cmp-disambig-photo cmp-disambig-photo-fallback";
            fb.textContent = initials;
            tgt.replaceWith(fb);
          }}
        />
      ) : (
        <div className="cmp-disambig-photo cmp-disambig-photo-fallback">{initials}</div>
      )}
      <div className="cmp-disambig-text">
        <span className="cmp-disambig-name">{c.name}</span>
        <span className="cmp-disambig-meta">
          {country} · {listeners ? `${formatInt(listeners)} ${listenersLbl}` : t("eval.disambig.no_streaming")}
          {c.genres && c.genres.length > 0 && ` · ${c.genres.slice(0, 2).join(", ")}`}
        </span>
      </div>
    </button>
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

  const reachDims: RadarDim[] = REACH_DIMS.map((d) => ({
    label: t(d.labelKey),
    fmt: d.fmt,
    valueA: d.get(a.dossier),
    valueB: d.get(b.dossier),
  }));

  // Scoring radar — pull all dimensions that both dossiers expose.
  const scoringNames = Array.from(
    new Set([
      ...Object.keys(a.dossier.prospect_score.dimensions ?? {}),
      ...Object.keys(b.dossier.prospect_score.dimensions ?? {}),
    ])
  );
  const scoringDims: RadarDim[] = scoringNames.map((name) => ({
    label: name.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()),
    fmt: (n) => `${Math.round(n)}`,
    valueA: a.dossier.prospect_score.dimensions?.[name]?.score ?? null,
    valueB: b.dossier.prospect_score.dimensions?.[name]?.score ?? null,
  }));

  return (
    <article className="evaluate-column">
      <CompareHeader a={a} b={b} accentA={accentA} accentB={accentB} />

      <section className="ev-section">
        <h2 className="ev-h2">{t("compare.reach_title")}</h2>
        <div className="cmp-radar-wrap">
          <RadarChart dims={reachDims} accentA={accentA} accentB={accentB} normalizeMode="max" />
          <RadarLegend a={a} b={b} accentA={accentA} accentB={accentB} dims={reachDims} />
        </div>
      </section>

      <section className="ev-section">
        <h2 className="ev-h2">{t("compare.scoring_title")}</h2>
        <div className="cmp-radar-wrap">
          <RadarChart dims={scoringDims} accentA={accentA} accentB={accentB} normalizeMode="percent" />
          <RadarLegend a={a} b={b} accentA={accentA} accentB={accentB} dims={scoringDims} />
        </div>
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
          const tgt = e.target as HTMLImageElement;
          const fb = document.createElement("div");
          fb.className = "cmp-header-photo cmp-header-photo-fallback";
          fb.textContent = initials;
          tgt.replaceWith(fb);
        }}
      />
    );
  }
  return <div className="cmp-header-photo cmp-header-photo-fallback">{initials}</div>;
}


function RadarLegend({
  a,
  b,
  accentA,
  accentB,
  dims,
}: {
  a: Extract<SideState, { kind: "loaded" }>;
  b: Extract<SideState, { kind: "loaded" }>;
  accentA: string;
  accentB: string;
  dims: RadarDim[];
}) {
  // Compact value table next to the radar — gives the analyst the
  // exact numbers without needing tooltips. Two columns of values per
  // axis, color-keyed back to the polygons.
  return (
    <div className="cmp-radar-legend">
      <div className="cmp-radar-legend-head">
        <div className="cmp-radar-legend-spacer" />
        <div className="cmp-radar-legend-name" style={{ color: accentA }}>
          {a.artist}
        </div>
        <div className="cmp-radar-legend-name" style={{ color: accentB }}>
          {b.artist}
        </div>
      </div>
      {dims.map((d, i) => (
        <div key={i} className="cmp-radar-legend-row">
          <div className="cmp-radar-legend-dim">{d.label}</div>
          <div className="cmp-radar-legend-val">
            {d.valueA != null ? d.fmt(d.valueA) : "—"}
          </div>
          <div className="cmp-radar-legend-val">
            {d.valueB != null ? d.fmt(d.valueB) : "—"}
          </div>
        </div>
      ))}
    </div>
  );
}
