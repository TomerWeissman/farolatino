"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { evaluate, searchArtists } from "@/lib/api";
import { useT } from "@/lib/i18n/context";
import { clearRecents, loadRecents, pushRecent, relativeTime, subscribeToRecents } from "@/lib/recents";
import type { DisambigCandidate, Dossier, EvaluateResponse, RecentEval } from "@/lib/types";
import {
  createConversation,
  saveConversation,
  setActiveConversationId,
} from "@/lib/conversations";
import { EvaluateDashboard } from "@/components/evaluate-dashboard";

type State =
  | { kind: "empty" }
  | { kind: "loading"; artist: string }
  | { kind: "disambig"; query: string; candidates: DisambigCandidate[] }
  | { kind: "error"; message: string; artist: string }
  | { kind: "loaded"; primary: LoadedDossier };

// What we keep around per artist after a successful evaluation.
type LoadedDossier = {
  artist: string;
  cm_id: number;
  dossier: Dossier;
  rendered_markdown: string;
};


export function Evaluate() {
  const t = useT();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [state, setState] = useState<State>({ kind: "empty" });
  const [draft, setDraft] = useState("");
  const [recents, setRecents] = useState<RecentEval[]>([]);
  const inputRef = useRef<HTMLInputElement | null>(null);
  // Tracks whether we've already auto-run for the current ?artist= URL
  // so we don't re-trigger on every state change.
  const autoRanFor = useRef<string | null>(null);

  // Load recents on mount. Subscribing also picks up the async
  // hydration from /api/recents — without this we'd render an empty
  // "Recently evaluated" panel until the next user interaction.
  useEffect(() => {
    setRecents(loadRecents());
    const unsub = subscribeToRecents(() => setRecents(loadRecents()));
    setTimeout(() => inputRef.current?.focus(), 50);
    return unsub;
  }, []);

  /**
   * Run /api/evaluate for a single artist by cm_id. Called AFTER the
   * user has picked a specific Chartmetric candidate from the search
   * picker (or when a recent-card click brings a stored cm_id with
   * it). The backend skips the search step when cm_id is provided
   * and goes straight to the cached dossier, so this is the cheap
   * path for resolved artists.
   */
  const run = useCallback(async (artist: string, cmId?: number) => {
    if (!artist.trim()) return;
    setState({ kind: "loading", artist });
    try {
      const r: EvaluateResponse = await evaluate(artist, cmId);
      if ("error" in r && r.error) {
        setState({ kind: "error", message: r.error, artist });
        return;
      }
      if ("needs_disambiguation" in r && r.needs_disambiguation) {
        setState({ kind: "disambig", query: r.query, candidates: r.needs_disambiguation });
        return;
      }
      if ("dossier" in r && r.dossier) {
        const loaded: LoadedDossier = {
          artist: r.dossier.identity.name,
          cm_id: r.cm_id,
          dossier: r.dossier,
          rendered_markdown: r.rendered_markdown,
        };
        setState({ kind: "loaded", primary: loaded });
        const updated = pushRecent({ name: loaded.artist, cm_id: loaded.cm_id, evaluated_at: Date.now() });
        setRecents(updated);
        return;
      }
      setState({ kind: "error", message: "Unexpected response shape", artist });
    } catch (e) {
      setState({ kind: "error", message: e instanceof Error ? e.message : "Network error", artist });
    }
  }, []);

  /**
   * v0.5.3 — top-of-funnel: always go through /api/search first.
   *
   * Replaces the previous "type a name → backend auto-picks the
   * dominant hit → user discovers it was wrong only after seeing the
   * dossier" flow. Now: type a name → see the candidate list → click
   * the right one → evaluate. The input also accepts a Chartmetric /
   * Spotify URL; URL-shaped queries skip the picker (there's nothing
   * to disambiguate) and go straight to evaluate.
   */
  const runSearch = useCallback(
    async (query: string) => {
      const trimmed = query.trim();
      if (!trimmed) return;
      setState({ kind: "loading", artist: trimmed });
      try {
        const r = await searchArtists(trimmed, 10);
        if (r.error) {
          setState({ kind: "error", message: r.error, artist: trimmed });
          return;
        }
        // URL path → exactly one (resolved) candidate. No picker —
        // the user already chose this artist by pasting their URL.
        if (r.resolved_from_url && r.artists[0]?.cm_id && r.artists[0]?.name) {
          void run(r.artists[0].name, r.artists[0].cm_id);
          return;
        }
        // Name path → always show the picker, even with one result, so
        // the user explicitly confirms the artist before we burn cycles
        // running the full dossier pipeline.
        const candidates: DisambigCandidate[] = (r.artists ?? []).filter(
          (a): a is DisambigCandidate => a.cm_id != null && a.name != null,
        );
        setState({ kind: "disambig", query: trimmed, candidates });
      } catch (e) {
        setState({
          kind: "error",
          message: e instanceof Error ? e.message : "Network error",
          artist: trimmed,
        });
      }
    },
    [run],
  );

  // Auto-run when navigated to /evaluate?artist=Name (e.g. from a
  // similar-artist card click or a chat-pill click-back). Only fires
  // once per URL value so the user can edit + re-search without it
  // bouncing back. cm_id is honoured when present — lets pills jump
  // straight to the cached dossier without re-searching.
  useEffect(() => {
    const queryArtist = searchParams.get("artist");
    const queryCmId = searchParams.get("cm_id");
    const key = queryCmId ? `${queryArtist}#${queryCmId}` : queryArtist;
    if (queryArtist && autoRanFor.current !== key) {
      autoRanFor.current = key;
      setDraft(queryArtist);
      // When the deep-link includes a cm_id (e.g. a pill click-back),
      // go straight to evaluate. Otherwise go through the search picker
      // — same flow as a manual submit.
      if (queryCmId) {
        void run(queryArtist, Number(queryCmId));
      } else {
        void runSearch(queryArtist);
      }
    }
  }, [searchParams, run, runSearch]);

  // Listen for the custom event fired by similar-artist card clicks
  // (covers Next.js's same-route-no-remount case where the URL changes
  // but the component doesn't unmount).
  useEffect(() => {
    function onEvalEvent(e: Event) {
      const detail = (e as CustomEvent<{ name: string }>).detail;
      if (detail?.name) {
        setDraft(detail.name);
        // Similar-artist card clicks ship a name only — funnel them
        // through the picker like a manual search would.
        void runSearch(detail.name);
      }
    }
    window.addEventListener("faroai-evaluate-artist", onEvalEvent);
    return () => window.removeEventListener("faroai-evaluate-artist", onEvalEvent);
  }, [runSearch]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void runSearch(draft.trim());
  };

  const handlePickRecent = (r: RecentEval) => {
    setDraft(r.name);
    void run(r.name, r.cm_id);
  };

  const handlePickDisambig = (cmId: number, name: string) => {
    setDraft(name);
    void run(name, cmId);
  };

  /**
   * Continue in chat — creates a new conversation with the dossier as
   * a compact pill (clickable to return to /evaluate). The full
   * Markdown is still in the turn's content so the LLM has the data
   * as context via Phase 1's message-history replay; the UI just
   * renders the pill on top of the markdown instead of dumping the
   * whole dossier as a wall of text.
   */
  const handleContinueInChat = () => {
    if (state.kind !== "loaded") return;
    const { primary } = state;
    const conv = createConversation(`Evaluate: ${primary.artist}`);
    conv.turns.push({ role: "user", content: `@evaluate ${primary.artist}` });
    conv.turns.push({
      role: "assistant",
      content: primary.rendered_markdown,  // LLM context — hidden from chat UI when pill is set
      evaluatePill: {
        artist: primary.artist,
        cm_id: primary.cm_id,
        image: primary.dossier.identity.image ?? undefined,
        tier: primary.dossier.prospect_score.tier,
        score: primary.dossier.prospect_score.overall,
      },
    });
    saveConversation(conv);
    setActiveConversationId(conv.id);
    router.push("/");
  };

  /**
   * Compare button → navigate to /compare with the current artist
   * preloaded as the primary slot. The compare page does the rest;
   * see plan for v0.3.2.
   */
  const handleCompare = () => {
    if (state.kind !== "loaded") return;
    const { primary } = state;
    router.push(`/compare?primary=${encodeURIComponent(primary.artist)}&primary_cm_id=${primary.cm_id}`);
  };

  const startOver = () => {
    setState({ kind: "empty" });
    setDraft("");
    setTimeout(() => inputRef.current?.focus(), 50);
  };

  return (
    <div className="evaluate-shell">
      {/* Top search bar — always visible at top of the page so the user
          can start a new evaluation without navigating away. */}
      <header className="evaluate-header">
        <div className="evaluate-eyebrow">{t("eval.eyebrow")}</div>
        <form onSubmit={handleSubmit} className="evaluate-search">
          <input
            ref={inputRef}
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={t("eval.search.placeholder")}
            className="evaluate-input"
            disabled={state.kind === "loading"}
          />
          <button
            type="submit"
            className="evaluate-btn evaluate-btn-primary"
            disabled={!draft.trim() || state.kind === "loading"}
          >
            {t("eval.search.button")}
          </button>
          {state.kind !== "empty" && (
            <button type="button" onClick={startOver} className="evaluate-btn-link">
              {t("eval.start_over")}
            </button>
          )}
        </form>
      </header>

      {state.kind === "empty" && (
        <EmptyState recents={recents} onPick={handlePickRecent} onClear={() => { setRecents([]); clearRecents(); }} />
      )}
      {state.kind === "loading" && <LoadingState artist={state.artist} />}
      {state.kind === "disambig" && (
        <DisambigState
          query={state.query}
          candidates={state.candidates}
          onPick={handlePickDisambig}
        />
      )}
      {state.kind === "error" && (
        <ErrorState message={state.message} artist={state.artist} onRetry={() => runSearch(state.artist)} />
      )}
      {state.kind === "loaded" && (
        <EvaluateDashboard
          primary={state.primary}
          onContinueInChat={handleContinueInChat}
          onCompare={handleCompare}
          onPickOther={(name, cmId) => {
            setDraft(name);
            void run(name, cmId);
          }}
        />
      )}
    </div>
  );
}


function EmptyState({
  recents,
  onPick,
  onClear,
}: {
  recents: RecentEval[];
  onPick: (r: RecentEval) => void;
  onClear: () => void;
}) {
  const t = useT();
  return (
    <div className="evaluate-empty">
      <p className="evaluate-empty-hint">{t("eval.empty.hint")}</p>
      {recents.length > 0 && (
        <div className="evaluate-recents">
          <div className="evaluate-recents-title">{t("eval.recents.title")}</div>
          {recents.map((r) => (
            <button key={r.cm_id} type="button" className="evaluate-recents-row" onClick={() => onPick(r)}>
              <span className="evaluate-recents-name">{r.name}</span>
              <span className="evaluate-recents-time">{relativeTime(r.evaluated_at, t)}</span>
            </button>
          ))}
          <button type="button" className="evaluate-btn-link evaluate-recents-clear" onClick={onClear}>
            {t("eval.recents.clear")}
          </button>
        </div>
      )}
    </div>
  );
}


function LoadingState({ artist }: { artist: string }) {
  const t = useT();
  // Tracks how long this load has been running so the user can see
  // something is still happening on a slow first lookup. Resets when
  // the artist changes (LoadingState remounts).
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="evaluate-loading">
      <div className="evaluate-loading-head">
        <span className="evaluate-spinner" aria-hidden="true" />
        <div className="evaluate-loading-title">
          {t("eval.loading.title", { artist })}
          {elapsed >= 3 && <span className="evaluate-loading-elapsed"> · {elapsed}s</span>}
        </div>
      </div>
      <div className="evaluate-loading-steps">
        <div>{t("eval.loading.step.lookup")}</div>
        <div>{t("eval.loading.step.pull")}</div>
        <div>{t("eval.loading.step.score")}</div>
        <div>{t("eval.loading.step.revenue")}</div>
        <div>{t("eval.loading.step.dossier")}</div>
      </div>
      <div className="evaluate-loading-note">{t("eval.loading.note")}</div>
    </div>
  );
}


function DisambigState({
  query,
  candidates,
  onPick,
}: {
  query: string;
  candidates: DisambigCandidate[];
  onPick: (cmId: number, name: string) => void;
}) {
  const t = useT();
  if (candidates.length === 0) {
    return (
      <div className="evaluate-disambig">
        <div className="evaluate-disambig-title">{t("eval.disambig.empty_title", { query })}</div>
        <div className="evaluate-disambig-hint">{t("eval.disambig.empty_hint")}</div>
      </div>
    );
  }
  return (
    <div className="evaluate-disambig">
      <div className="evaluate-disambig-title">{t("eval.disambig.title", { query })}</div>
      <div className="evaluate-disambig-hint">{t("eval.disambig.hint")}</div>
      {candidates.map((c) => {
        const listeners = c.sp_monthly_listeners ?? c.sp_followers ?? 0;
        const listenersLbl = c.sp_monthly_listeners
          ? t("eval.disambig.monthly_listeners")
          : t("eval.disambig.spotify_followers");
        // Chartmetric search returns code2; the API can also surface
        // a country_code field on other endpoints. Either works.
        const country = c.country_code ?? c.code2 ?? "—";
        const initials = c.name
          .split(" ")
          .filter(Boolean)
          .slice(0, 2)
          .map((s) => s[0]?.toUpperCase() ?? "")
          .join("") || "?";
        return (
          <button key={c.cm_id} type="button" className="evaluate-disambig-row" onClick={() => onPick(c.cm_id, c.name)}>
            {c.image_url ? (
              <img
                src={c.image_url}
                alt={c.name}
                className="evaluate-disambig-photo"
                onError={(e) => {
                  const target = e.currentTarget;
                  const fallback = document.createElement("div");
                  fallback.className = "evaluate-disambig-photo evaluate-disambig-photo-fallback";
                  fallback.textContent = initials;
                  target.replaceWith(fallback);
                }}
              />
            ) : (
              <div className="evaluate-disambig-photo evaluate-disambig-photo-fallback">{initials}</div>
            )}
            <div className="evaluate-disambig-text">
              <span className="evaluate-disambig-name">{c.name}</span>
              <span className="evaluate-disambig-meta">
                {country} · {listeners ? `${formatInt(listeners)} ${listenersLbl}` : t("eval.disambig.no_streaming")}
                {c.genres && c.genres.length > 0 && ` · ${c.genres.slice(0, 2).join(", ")}`}
              </span>
            </div>
          </button>
        );
      })}
    </div>
  );
}


function ErrorState({
  message,
  artist,
  onRetry,
}: {
  message: string;
  artist: string;
  onRetry: () => void;
}) {
  const t = useT();
  return (
    <div className="evaluate-error">
      <div className="evaluate-error-title">{t("eval.error.title", { artist })}</div>
      <div className="evaluate-error-message">{message}</div>
      <button type="button" className="evaluate-btn evaluate-btn-secondary" onClick={onRetry}>
        {t("eval.error.retry")}
      </button>
    </div>
  );
}


// ─── Misc formatters ──────────────────────────────────────────────
// (loadRecents / pushRecent / clearRecents / relativeTime moved to
//  web/lib/recents.ts in v0.5.2 so /compare reuses the same code.)

function formatInt(n: number): string {
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)}B`;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return n.toLocaleString();
}

