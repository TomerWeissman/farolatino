"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { evaluate } from "@/lib/api";
import type { Dossier, EvaluateResponse, RecentEval } from "@/lib/types";
import {
  createConversation,
  saveConversation,
  setActiveConversationId,
} from "@/lib/conversations";
import { EvaluateDashboard } from "@/components/evaluate-dashboard";

// Keys to coordinate state across the page.
const RECENT_KEY = "faroai-recent-evals";
const RECENT_LIMIT = 5;

type State =
  | { kind: "empty" }
  | { kind: "loading"; artist: string }
  | { kind: "disambig"; query: string; candidates: Array<{ cm_id: number; name: string; country_code?: string; sp_followers?: number; sp_monthly_listeners?: number }> }
  | { kind: "error"; message: string; artist: string }
  | { kind: "loaded"; primary: LoadedDossier; secondary?: LoadedDossier };

// What we keep around per artist after a successful evaluation.
type LoadedDossier = {
  artist: string;
  cm_id: number;
  dossier: Dossier;
  rendered_markdown: string;
};


export function Evaluate() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [state, setState] = useState<State>({ kind: "empty" });
  const [draft, setDraft] = useState("");
  const [recents, setRecents] = useState<RecentEval[]>([]);
  // Compare-mode flag: when true, the second search bar is visible.
  const [compareOpen, setCompareOpen] = useState(false);
  const [compareDraft, setCompareDraft] = useState("");
  const inputRef = useRef<HTMLInputElement | null>(null);
  // Tracks whether we've already auto-run for the current ?artist= URL
  // so we don't re-trigger on every state change.
  const autoRanFor = useRef<string | null>(null);

  // Load recents on mount.
  useEffect(() => {
    setRecents(loadRecents());
    setTimeout(() => inputRef.current?.focus(), 50);
  }, []);

  /**
   * Run /api/evaluate for a single artist. Handles the four response
   * shapes: success → loaded; ambiguous → disambig; error → error.
   * `slot` distinguishes the primary artist (default) from the
   * comparison's second artist.
   */
  const run = useCallback(async (artist: string, cmId?: number, slot: "primary" | "secondary" = "primary") => {
    if (!artist.trim()) return;
    if (slot === "primary") {
      setState({ kind: "loading", artist });
    }
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
        // Merge into current state; if we're adding a secondary,
        // preserve the primary that's already loaded.
        setState((cur) => {
          if (slot === "secondary" && cur.kind === "loaded") {
            return { ...cur, secondary: loaded };
          }
          return { kind: "loaded", primary: loaded };
        });
        // Track in recents (primary slot only — secondary is a
        // throwaway compare).
        if (slot === "primary") {
          const updated = pushRecent({ name: loaded.artist, cm_id: loaded.cm_id, evaluated_at: Date.now() });
          setRecents(updated);
        }
        return;
      }
      setState({ kind: "error", message: "Unexpected response shape", artist });
    } catch (e) {
      setState({ kind: "error", message: e instanceof Error ? e.message : "Network error", artist });
    }
  }, []);

  // Auto-run when navigated to /evaluate?artist=Name (e.g. from a
  // similar-artist card click). Only fires once per URL value so the
  // user can edit + re-search without it bouncing back.
  useEffect(() => {
    const queryArtist = searchParams.get("artist");
    if (queryArtist && autoRanFor.current !== queryArtist) {
      autoRanFor.current = queryArtist;
      setDraft(queryArtist);
      void run(queryArtist);
    }
  }, [searchParams, run]);

  // Listen for the custom event fired by similar-artist card clicks
  // (covers Next.js's same-route-no-remount case where the URL changes
  // but the component doesn't unmount).
  useEffect(() => {
    function onEvalEvent(e: Event) {
      const detail = (e as CustomEvent<{ name: string }>).detail;
      if (detail?.name) {
        setDraft(detail.name);
        void run(detail.name);
      }
    }
    window.addEventListener("faroai-evaluate-artist", onEvalEvent);
    return () => window.removeEventListener("faroai-evaluate-artist", onEvalEvent);
  }, [run]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void run(draft.trim());
  };

  const handleSubmitCompare = (e: React.FormEvent) => {
    e.preventDefault();
    void run(compareDraft.trim(), undefined, "secondary");
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
   * Continue in chat — creates a new conversation seeded with the
   * dossier as the first assistant turn, then navigates to /. The
   * LLM gets the full dossier as context on the next turn via Phase 1's
   * message-history replay. If we're in compare mode, both dossiers
   * are concatenated so the LLM has both as context.
   */
  const handleContinueInChat = () => {
    if (state.kind !== "loaded") return;
    const { primary, secondary } = state;
    const title = secondary
      ? `Evaluate: ${primary.artist} vs ${secondary.artist}`
      : `Evaluate: ${primary.artist}`;
    const conv = createConversation(title);
    const userPrompt = secondary
      ? `@evaluate ${primary.artist}  (then) @evaluate ${secondary.artist}`
      : `@evaluate ${primary.artist}`;
    const assistantContent = secondary
      ? `${primary.rendered_markdown}\n\n---\n\n${secondary.rendered_markdown}`
      : primary.rendered_markdown;
    conv.turns.push({ role: "user", content: userPrompt });
    conv.turns.push({ role: "assistant", content: assistantContent });
    saveConversation(conv);
    setActiveConversationId(conv.id);
    router.push("/");
  };

  const resetCompare = () => {
    setCompareOpen(false);
    setCompareDraft("");
    setState((cur) => (cur.kind === "loaded" ? { kind: "loaded", primary: cur.primary } : cur));
  };

  const startOver = () => {
    setState({ kind: "empty" });
    setDraft("");
    setCompareOpen(false);
    setCompareDraft("");
    setTimeout(() => inputRef.current?.focus(), 50);
  };

  return (
    <div className="evaluate-shell">
      {/* Top search bar — always visible at top of the page so the user
          can start a new evaluation without navigating away. */}
      <header className="evaluate-header">
        <div className="evaluate-eyebrow">Evaluate</div>
        <form onSubmit={handleSubmit} className="evaluate-search">
          <input
            ref={inputRef}
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Enter an artist name to generate a full dossier"
            className="evaluate-input"
            disabled={state.kind === "loading"}
          />
          <button
            type="submit"
            className="evaluate-btn evaluate-btn-primary"
            disabled={!draft.trim() || state.kind === "loading"}
          >
            Search
          </button>
          {state.kind !== "empty" && (
            <button type="button" onClick={startOver} className="evaluate-btn-link">
              Start over
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
        <ErrorState message={state.message} artist={state.artist} onRetry={() => run(state.artist)} />
      )}
      {state.kind === "loaded" && (
        <>
          {/* Compare-mode second-artist input slides in above the dashboards */}
          {compareOpen && !state.secondary && (
            <form onSubmit={handleSubmitCompare} className="evaluate-compare-bar">
              <span className="evaluate-compare-label">Compare with</span>
              <input
                type="text"
                value={compareDraft}
                onChange={(e) => setCompareDraft(e.target.value)}
                placeholder="Second artist name…"
                className="evaluate-input"
                autoFocus
              />
              <button type="submit" className="evaluate-btn evaluate-btn-primary" disabled={!compareDraft.trim()}>
                Add
              </button>
              <button type="button" onClick={resetCompare} className="evaluate-btn-link">Cancel</button>
            </form>
          )}

          <EvaluateDashboard
            primary={state.primary}
            secondary={state.secondary}
            onContinueInChat={handleContinueInChat}
            onCompareToggle={() => setCompareOpen(true)}
            onResetCompare={resetCompare}
          />
        </>
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
  return (
    <div className="evaluate-empty">
      <p className="evaluate-empty-hint">
        Type an artist name above and press Search. Returns a full dossier with score,
        revenue projection, top markets, and recent activity. ~10–30s on first lookup,
        instant on re-runs.
      </p>
      {recents.length > 0 && (
        <div className="evaluate-recents">
          <div className="evaluate-recents-title">Recently evaluated</div>
          {recents.map((r) => (
            <button key={r.cm_id} type="button" className="evaluate-recents-row" onClick={() => onPick(r)}>
              <span className="evaluate-recents-name">{r.name}</span>
              <span className="evaluate-recents-time">{relativeTime(r.evaluated_at)}</span>
            </button>
          ))}
          <button type="button" className="evaluate-btn-link evaluate-recents-clear" onClick={onClear}>
            Clear history
          </button>
        </div>
      )}
    </div>
  );
}


function LoadingState({ artist }: { artist: string }) {
  return (
    <div className="evaluate-loading">
      <div className="evaluate-loading-title">Evaluating {artist}</div>
      <div className="evaluate-loading-steps">
        <div>· Looking up on Chartmetric…</div>
        <div>· Pulling streaming + social + catalog data</div>
        <div>· Scoring across 7 dimensions</div>
        <div>· Projecting revenue</div>
        <div>· Building dossier</div>
      </div>
      <div className="evaluate-loading-note">Cold lookups take 10–30 seconds. Re-runs are instant (cached).</div>
    </div>
  );
}


function DisambigState({
  query,
  candidates,
  onPick,
}: {
  query: string;
  candidates: Array<{ cm_id: number; name: string; country_code?: string; sp_followers?: number; sp_monthly_listeners?: number }>;
  onPick: (cmId: number, name: string) => void;
}) {
  return (
    <div className="evaluate-disambig">
      <div className="evaluate-disambig-title">Multiple artists match &ldquo;{query}&rdquo;</div>
      <div className="evaluate-disambig-hint">Pick one — re-runs evaluate with that artist.</div>
      {candidates.map((c) => {
        const listeners = c.sp_monthly_listeners ?? c.sp_followers ?? 0;
        const listenersLbl = c.sp_monthly_listeners ? "monthly listeners" : "Spotify followers";
        return (
          <button key={c.cm_id} type="button" className="evaluate-disambig-row" onClick={() => onPick(c.cm_id, c.name)}>
            <span className="evaluate-disambig-name">{c.name}</span>
            <span className="evaluate-disambig-meta">
              {c.country_code ?? "—"} · {listeners ? `${formatInt(listeners)} ${listenersLbl}` : "no streaming data"}
            </span>
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
  return (
    <div className="evaluate-error">
      <div className="evaluate-error-title">Couldn&apos;t evaluate {artist}</div>
      <div className="evaluate-error-message">{message}</div>
      <button type="button" className="evaluate-btn evaluate-btn-secondary" onClick={onRetry}>
        Retry
      </button>
    </div>
  );
}


// ─── localStorage helpers for the recents list ─────────────────────

function loadRecents(): RecentEval[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.slice(0, RECENT_LIMIT);
  } catch {
    return [];
  }
}

function pushRecent(item: RecentEval): RecentEval[] {
  if (typeof window === "undefined") return [];
  const cur = loadRecents();
  const filtered = cur.filter((r) => r.cm_id !== item.cm_id);
  const next = [item, ...filtered].slice(0, RECENT_LIMIT);
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  } catch {
    /* no-op */
  }
  return next;
}

function clearRecents(): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(RECENT_KEY);
  } catch {
    /* no-op */
  }
}


// ─── Misc formatters ──────────────────────────────────────────────

function formatInt(n: number): string {
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)}B`;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return n.toLocaleString();
}

function relativeTime(epoch: number): string {
  const diffSec = (Date.now() - epoch) / 1000;
  if (diffSec < 60) return "just now";
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
  const days = Math.floor(diffSec / 86400);
  if (days === 1) return "yesterday";
  if (days < 7) return `${days}d ago`;
  return new Date(epoch).toLocaleDateString();
}
