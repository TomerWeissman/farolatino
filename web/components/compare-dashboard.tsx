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
import { useRouter, useSearchParams } from "next/navigation";
import { evaluate, searchArtists } from "@/lib/api";
import { useT } from "@/lib/i18n/context";
import { dimensionLabel, formatInt, formatMoney } from "@/lib/format";
import {
  clearRecentCompares,
  loadRecentCompares,
  pushRecentCompare,
  relativeTime,
  subscribeToRecents,
} from "@/lib/recents";
import type { DisambigCandidate, Dossier, EvaluateResponse, RecentCompare } from "@/lib/types";
import { OtherMatchesPanel } from "@/components/evaluate-dashboard";
import { RadarChart, type RadarDim } from "@/components/radar-chart";

type SideState =
  | { kind: "empty" }
  | { kind: "loading"; artist: string }
  | { kind: "disambig"; query: string; candidates: DisambigCandidate[] }
  | { kind: "error"; message: string; artist: string }
  | { kind: "loaded"; artist: string; cm_id: number; dossier: Dossier };

// v0.5.3 — fixed Compare palette, independent of either artist's tier.
// Before, Artist A inherited TIER_COLOR (could be blue, green, orange,
// gray) and Artist B was always purple; whenever the tier color landed
// close to purple the two polygons read as the same artist. These two
// values are high-contrast against each other AND against the radar's
// neutral grid in every combo. Kept in sync with the matching CSS
// custom properties in web/app/globals.css so the radar polygons,
// header borders, and the income block all draw from one palette.
const ACCENT_A = "#0ea5e9"; // cyan-blue
const ACCENT_B = "#f97316"; // orange

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
  const [recents, setRecents] = useState<RecentCompare[]>([]);

  // Load recents on mount. Subscribing also picks up async hydration
  // from /api/recents so the panel doesn't render empty on first paint.
  useEffect(() => {
    setRecents(loadRecentCompares());
    return subscribeToRecents(() => setRecents(loadRecentCompares()));
  }, []);

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

  /**
   * v0.5.3 — search-first per-side flow. Same shape as evaluate.tsx's
   * runSearch: hit /api/search, drop into the disambig picker so the
   * user explicitly confirms which Chartmetric artist they meant,
   * unless the input was a URL (single resolved candidate → skip the
   * picker, run evaluate immediately).
   */
  const runSearchSide = useCallback(
    async (side: "A" | "B", query: string) => {
      const trimmed = query.trim();
      if (!trimmed) return;
      const setter = side === "A" ? setSideA : setSideB;
      setter({ kind: "loading", artist: trimmed });
      try {
        const r = await searchArtists(trimmed, 10);
        if (r.error) {
          setter({ kind: "error", message: r.error, artist: trimmed });
          return;
        }
        if (r.resolved_from_url && r.artists[0]?.cm_id && r.artists[0]?.name) {
          void runSide(side, r.artists[0].name, r.artists[0].cm_id);
          return;
        }
        const candidates: DisambigCandidate[] = (r.artists ?? []).filter(
          (a): a is DisambigCandidate => a.cm_id != null && a.name != null,
        );
        setter({ kind: "disambig", query: trimmed, candidates });
      } catch (e) {
        setter({
          kind: "error",
          message: e instanceof Error ? e.message : "Network error",
          artist: trimmed,
        });
      }
    },
    [runSide],
  );

  // Pre-populate from URL: ?primary=A&primary_cm_id=X&secondary=B&secondary_cm_id=Y
  // cm_id in the URL means we already know which Chartmetric artist it
  // is (e.g. an evaluate-page "Compare" click brings one along), so we
  // skip the picker. Plain ?primary=Name without an id goes through
  // the search-first flow.
  useEffect(() => {
    const a = searchParams.get("primary");
    const b = searchParams.get("secondary");
    const aId = searchParams.get("primary_cm_id");
    const bId = searchParams.get("secondary_cm_id");
    if (a) {
      setDraftA(a);
      if (aId) void runSide("A", a, Number(aId));
      else void runSearchSide("A", a);
    }
    if (b) {
      setDraftB(b);
      if (bId) void runSide("B", b, Number(bId));
      else void runSearchSide("B", b);
    }
  }, [searchParams, runSide, runSearchSide]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (draftA.trim()) void runSearchSide("A", draftA.trim());
    if (draftB.trim()) void runSearchSide("B", draftB.trim());
  };

  const handlePickRecent = (rc: RecentCompare) => {
    setDraftA(rc.artist_a);
    setDraftB(rc.artist_b);
    void runSide("A", rc.artist_a, rc.cm_id_a);
    void runSide("B", rc.artist_b, rc.cm_id_b);
  };

  const handleClearRecents = () => {
    clearRecentCompares();
    setRecents([]);
  };

  const bothLoaded = sideA.kind === "loaded" && sideB.kind === "loaded";

  // Push to recents whenever a NEW pair (cm_id_a + cm_id_b) lands.
  // Compare against the current head of recents so we don't duplicate
  // on every re-render of the loaded state.
  useEffect(() => {
    if (sideA.kind !== "loaded" || sideB.kind !== "loaded") return;
    const head = recents[0];
    if (head && head.cm_id_a === sideA.cm_id && head.cm_id_b === sideB.cm_id) return;
    const updated = pushRecentCompare({
      artist_a: sideA.artist,
      cm_id_a: sideA.cm_id,
      artist_b: sideB.artist,
      cm_id_b: sideB.cm_id,
      compared_at: Date.now(),
    });
    setRecents(updated);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sideA, sideB]);

  const bothEmpty = sideA.kind === "empty" && sideB.kind === "empty";

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

      {bothEmpty && recents.length > 0 && (
        <RecentComparesList
          recents={recents}
          onPick={handlePickRecent}
          onClear={handleClearRecents}
        />
      )}

      {!bothLoaded && (
        <div className="cmp-side-status-grid">
          <SideStatus
            side="A"
            state={sideA}
            onPick={(id, name) => { setDraftA(name); void runSide("A", name, id); }}
            onRetry={(name) => void runSearchSide("A", name)}
          />
          <SideStatus
            side="B"
            state={sideB}
            onPick={(id, name) => { setDraftB(name); void runSide("B", name, id); }}
            onRetry={(name) => void runSearchSide("B", name)}
          />
        </div>
      )}

      {bothLoaded && sideA.kind === "loaded" && sideB.kind === "loaded" && (
        <ComparisonView
          a={sideA}
          b={sideB}
          onPickOther={(side, name, cmId) => {
            if (side === "A") setDraftA(name); else setDraftB(name);
            void runSide(side, name, cmId);
          }}
        />
      )}
    </div>
  );
}


function RecentComparesList({
  recents,
  onPick,
  onClear,
}: {
  recents: RecentCompare[];
  onPick: (rc: RecentCompare) => void;
  onClear: () => void;
}) {
  const t = useT();
  return (
    <div className="cmp-recents">
      <div className="cmp-recents-title">{t("compare.recents.title")}</div>
      {recents.map((rc) => (
        <button
          key={`${rc.cm_id_a}-${rc.cm_id_b}`}
          type="button"
          className="cmp-recents-row"
          onClick={() => onPick(rc)}
        >
          <span className="cmp-recents-pair">
            <strong>{rc.artist_a}</strong>
            <span className="cmp-recents-vs">vs</span>
            <strong>{rc.artist_b}</strong>
          </span>
          <span className="cmp-recents-time">{relativeTime(rc.compared_at, t)}</span>
        </button>
      ))}
      <button type="button" className="evaluate-btn-link cmp-recents-clear" onClick={onClear}>
        {t("compare.recents.clear")}
      </button>
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
    const empty = state.candidates.length === 0;
    return (
      <div className="cmp-side cmp-side-disambig">
        <div className="cmp-side-label">{side}</div>
        <div className="cmp-side-disambig-title">
          {empty
            ? t("eval.disambig.empty_title", { query: state.query })
            : t("eval.disambig.title", { query: state.query })}
        </div>
        <div className="cmp-side-disambig-hint">
          {empty ? t("eval.disambig.empty_hint") : t("eval.disambig.hint")}
        </div>
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
  onPickOther,
}: {
  a: Extract<SideState, { kind: "loaded" }>;
  b: Extract<SideState, { kind: "loaded" }>;
  // v0.5.3 — picking a different Chartmetric match from the OtherMatches
  // panel re-runs ONE side's evaluation. The parent CompareDashboard
  // owns runSide() so the disambiguation flow is consistent with the
  // initial-search flow.
  onPickOther?: (side: "A" | "B", name: string, cmId: number) => void;
}) {
  const t = useT();
  const accentA = ACCENT_A;
  const accentB = ACCENT_B;

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
    label: dimensionLabel(t, name),
    fmt: (n) => `${Math.round(n)}`,
    valueA: a.dossier.prospect_score.dimensions?.[name]?.score ?? null,
    valueB: b.dossier.prospect_score.dimensions?.[name]?.score ?? null,
  }));

  return (
    <article className="evaluate-column">
      <CompareHeader a={a} b={b} accentA={accentA} accentB={accentB} />

      {onPickOther && (
        <div className="cmp-other-matches-row">
          <OtherMatchesPanel
            artist={a.artist}
            onPick={(name, cmId) => onPickOther("A", name, cmId)}
          />
          <OtherMatchesPanel
            artist={b.artist}
            onPick={(name, cmId) => onPickOther("B", name, cmId)}
          />
        </div>
      )}

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

      <CompareIncome a={a} b={b} accentA={accentA} accentB={accentB} />

      <div className="ev-source">{t("compare.source")}</div>
    </article>
  );
}


// v0.5.3 — side-by-side income block on /compare. Shows annual gross,
// monthly gross, and Faro's monthly share for each artist, using the
// 70/30 split from config/revenue_share.yaml (the dossier attaches it
// at revenue_projection.share). When the revenue model didn't run on
// one side (rare), that column shows "—" for all three rows so the
// layout doesn't collapse asymmetrically.
function CompareIncome({
  a,
  b,
  accentA,
  accentB,
}: {
  a: Extract<SideState, { kind: "loaded" }>;
  b: Extract<SideState, { kind: "loaded" }>;
  accentA: string;
  accentB: string;
}) {
  const t = useT();
  const revA = a.dossier.revenue_projection;
  const revB = b.dossier.revenue_projection;
  // If neither side has a useful projection, skip the section entirely.
  const annA = revA?.annual_projected;
  const annB = revB?.annual_projected;
  if (!annA && !annB) return null;
  // Share lives on either dossier; both will be identical (same config),
  // but fall back defensively if one is missing.
  const share =
    revA?.share ?? revB?.share ?? { artist_pct: 0.7, faro_pct: 0.3 };
  const faroPctLabel = Math.round(share.faro_pct * 100);
  const artistPctLabel = Math.round(share.artist_pct * 100);

  return (
    <section className="ev-section">
      <h2 className="ev-h2">{t("eval.dashboard.revenue")}</h2>
      <div className="cmp-income-grid">
        <CompareIncomeColumn
          name={a.artist}
          accent={accentA}
          annual={annA}
          share={share}
          t={t}
          faroPctLabel={faroPctLabel}
          artistPctLabel={artistPctLabel}
        />
        <CompareIncomeColumn
          name={b.artist}
          accent={accentB}
          annual={annB}
          share={share}
          t={t}
          faroPctLabel={faroPctLabel}
          artistPctLabel={artistPctLabel}
        />
      </div>
    </section>
  );
}


function CompareIncomeColumn({
  name,
  accent,
  annual,
  share,
  t,
  faroPctLabel,
  artistPctLabel,
}: {
  name: string;
  accent: string;
  annual: number | undefined;
  share: { artist_pct: number; faro_pct: number };
  t: (key: string, vars?: Record<string, string | number>) => string;
  faroPctLabel: number;
  artistPctLabel: number;
}) {
  const monthly = annual ? annual / 12 : null;
  const faroMonthly = monthly != null ? monthly * share.faro_pct : null;
  const artistMonthly = monthly != null ? monthly * share.artist_pct : null;
  const dash = "—";
  return (
    <div className="cmp-income-col" style={{ borderColor: accent }}>
      <div className="cmp-income-name" style={{ color: accent }}>{name}</div>
      <div className="cmp-income-row">
        <div className="cmp-income-label">{t("eval.dashboard.revenue.annual_gross")}</div>
        <div className="cmp-income-value">{annual != null ? formatMoney(annual) : dash}</div>
      </div>
      <div className="cmp-income-row">
        <div className="cmp-income-label">{t("eval.dashboard.revenue.monthly_gross")}</div>
        <div className="cmp-income-value">{monthly != null ? formatMoney(monthly) : dash}</div>
      </div>
      <div className="cmp-income-row">
        <div className="cmp-income-label">
          {t("eval.dashboard.revenue.faro_share", { pct: faroPctLabel })}
        </div>
        <div className="cmp-income-value">{faroMonthly != null ? formatMoney(faroMonthly) : dash}</div>
      </div>
      {artistMonthly != null && (
        <div className="cmp-income-sub">
          {t("eval.dashboard.revenue.artist_share_sub", {
            pct: artistPctLabel,
            amount: formatMoney(artistMonthly),
          })}
        </div>
      )}
    </div>
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
  const t = useT();
  const router = useRouter();
  const openDossier = (artist: string, cm_id: number) => {
    router.push(`/evaluate?artist=${encodeURIComponent(artist)}&cm_id=${cm_id}`);
  };
  return (
    <header className="ev-section ev-hero cmp-header">
      <div className="cmp-header-side" style={{ borderColor: accentA }}>
        <PhotoOrInitials name={a.artist} image={a.dossier.identity.image} />
        <h2 className="cmp-header-name">{a.artist}</h2>
        <div className="cmp-header-tier" style={{ color: accentA }}>
          {a.dossier.prospect_score.tier} · {Math.round(a.dossier.prospect_score.overall)}/100
        </div>
        <button
          type="button"
          className="evaluate-btn evaluate-btn-secondary cmp-header-dossier-btn"
          onClick={() => openDossier(a.artist, a.cm_id)}
        >
          {t("compare.open_dossier")}
        </button>
      </div>
      <div className="cmp-header-vs">vs</div>
      <div className="cmp-header-side" style={{ borderColor: accentB }}>
        <PhotoOrInitials name={b.artist} image={b.dossier.identity.image} />
        <h2 className="cmp-header-name">{b.artist}</h2>
        <div className="cmp-header-tier" style={{ color: accentB }}>
          {b.dossier.prospect_score.tier} · {Math.round(b.dossier.prospect_score.overall)}/100
        </div>
        <button
          type="button"
          className="evaluate-btn evaluate-btn-secondary cmp-header-dossier-btn"
          onClick={() => openDossier(b.artist, b.cm_id)}
        >
          {t("compare.open_dossier")}
        </button>
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


