// "Recently used" lists — server-backed since v0.5.3.
//
// Two independent histories (single-artist evals + artist-pair compares),
// each capped at 5 entries with oldest evicted on push. Storage moved
// from localStorage to a JSON file under the per-user config dir
// (core/storage.py + api/routes/recents.py) for the same reason as
// conversations.ts — pywebview's WebKit data store wasn't surviving
// py2app rebuilds across version bumps.
//
// Synchronous reads + fire-and-forget writes mirror conversations.ts:
// the in-memory cache is hydrated lazily, hydration dispatches a
// CHANGE event, the existing UI hooks re-read on the event. Same
// migration pattern: drain the legacy localStorage blob into the
// server on first launch and then clear it.

import type { RecentCompare, RecentEval } from "@/lib/types";

const LEGACY_RECENT_KEY = "faroai-recent-evals";
const LEGACY_RECENT_COMPARE_KEY = "faroai-recent-compares";
const CHANGE_EVENT = "faroai:recents-changed";

let cache: { evals: RecentEval[]; compares: RecentCompare[] } | null = null;
let hydratePromise: Promise<void> | null = null;

function notify(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(CHANGE_EVENT));
}

async function fetchAll(): Promise<{ evals: RecentEval[]; compares: RecentCompare[] }> {
  const resp = await fetch("/api/recents", { cache: "no-store" });
  if (!resp.ok) throw new Error(`GET /api/recents: HTTP ${resp.status}`);
  const data = await resp.json();
  return {
    evals: Array.isArray(data?.evals) ? data.evals : [],
    compares: Array.isArray(data?.compares) ? data.compares : [],
  };
}

function readLegacy<T>(key: string): T[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as T[]) : [];
  } catch {
    return [];
  }
}

async function migrateLegacyLocalStorage(
  current: { evals: RecentEval[]; compares: RecentCompare[] },
): Promise<{ evals: RecentEval[]; compares: RecentCompare[] } | null> {
  // Only migrate when the server side is empty for BOTH lists — that
  // matches the "first launch after upgrade" condition. If the user
  // has already populated either list on disk we leave the legacy
  // blob alone.
  if (current.evals.length > 0 || current.compares.length > 0) return null;
  const legacyEvals = readLegacy<RecentEval>(LEGACY_RECENT_KEY);
  const legacyCompares = readLegacy<RecentCompare>(LEGACY_RECENT_COMPARE_KEY);
  if (legacyEvals.length === 0 && legacyCompares.length === 0) return null;

  const resp = await fetch("/api/recents/migrate", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ evals: legacyEvals, compares: legacyCompares }),
  });
  if (!resp.ok) throw new Error(`recents migrate failed: HTTP ${resp.status}`);
  try {
    localStorage.removeItem(LEGACY_RECENT_KEY);
    localStorage.removeItem(LEGACY_RECENT_COMPARE_KEY);
  } catch {
    /* no-op */
  }
  // Re-fetch so the cache reflects the server-side limit + dedup.
  return await fetchAll();
}

async function hydrate(): Promise<void> {
  let server: { evals: RecentEval[]; compares: RecentCompare[] };
  try {
    server = await fetchAll();
  } catch {
    cache = { evals: [], compares: [] };
    notify();
    return;
  }
  try {
    const migrated = await migrateLegacyLocalStorage(server);
    if (migrated) server = migrated;
  } catch {
    /* fall through with whatever the server gave us */
  }
  cache = server;
  notify();
}

function ensureHydrated(): void {
  if (cache !== null) return;
  if (typeof window === "undefined") {
    cache = { evals: [], compares: [] };
    return;
  }
  if (!hydratePromise) {
    cache = { evals: [], compares: [] };
    hydratePromise = hydrate();
  }
}

// ─── Recent evals ───────────────────────────────────────────────────────

export function loadRecents(): RecentEval[] {
  ensureHydrated();
  return cache?.evals ?? [];
}

export function pushRecent(item: RecentEval): RecentEval[] {
  ensureHydrated();
  if (!cache) cache = { evals: [], compares: [] };
  const filtered = cache.evals.filter((r) => r.cm_id !== item.cm_id);
  cache.evals = [item, ...filtered].slice(0, 5);
  notify();
  void fetch("/api/recents/eval", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(item),
  }).catch(() => {
    /* best-effort */
  });
  return cache.evals;
}

export function clearRecents(): void {
  ensureHydrated();
  if (cache) cache.evals = [];
  notify();
  void fetch("/api/recents/eval", { method: "DELETE" }).catch(() => {});
}

// ─── Recent compares ────────────────────────────────────────────────────

export function loadRecentCompares(): RecentCompare[] {
  ensureHydrated();
  return cache?.compares ?? [];
}

export function pushRecentCompare(item: RecentCompare): RecentCompare[] {
  ensureHydrated();
  if (!cache) cache = { evals: [], compares: [] };
  // Dedupe by ORDERED pair — Bad Bunny vs Karol G is a different
  // entry from Karol G vs Bad Bunny (positions matter on the radar).
  const filtered = cache.compares.filter(
    (r) => !(r.cm_id_a === item.cm_id_a && r.cm_id_b === item.cm_id_b),
  );
  cache.compares = [item, ...filtered].slice(0, 5);
  notify();
  void fetch("/api/recents/compare", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(item),
  }).catch(() => {});
  return cache.compares;
}

export function clearRecentCompares(): void {
  ensureHydrated();
  if (cache) cache.compares = [];
  notify();
  void fetch("/api/recents/compare", { method: "DELETE" }).catch(() => {});
}

/** Subscribe to any change in the recents store. Returns an unsubscribe fn. */
export function subscribeToRecents(cb: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const handler = () => cb();
  window.addEventListener(CHANGE_EVENT, handler);
  ensureHydrated();
  return () => window.removeEventListener(CHANGE_EVENT, handler);
}

/** "just now", "5m ago", "2h ago", "yesterday", "3d ago", or a date. */
export function relativeTime(
  epoch: number,
  t: (key: string, vars?: Record<string, string | number>) => string,
): string {
  const diffSec = (Date.now() - epoch) / 1000;
  if (diffSec < 60) return t("eval.time.just_now");
  if (diffSec < 3600) return t("eval.time.minutes", { n: Math.floor(diffSec / 60) });
  if (diffSec < 86400) return t("eval.time.hours", { n: Math.floor(diffSec / 3600) });
  const days = Math.floor(diffSec / 86400);
  if (days === 1) return t("eval.time.yesterday");
  if (days < 7) return t("eval.time.days", { n: days });
  return new Date(epoch).toLocaleDateString();
}
