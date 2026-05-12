// "Recently used" lists — two independent histories:
//
//   faroai-recent-evals     — single-artist evaluations (/evaluate empty state)
//   faroai-recent-compares  — artist pairs (/compare empty state, v0.5.2)
//
// Both are stored in localStorage, capped at 5 entries, oldest evicted
// on push. Clicking a row on either page resolves the artist(s) by
// cm_id (cache hit → instant render).

import type { RecentCompare, RecentEval } from "@/lib/types";

const RECENT_KEY = "faroai-recent-evals";
const RECENT_COMPARE_KEY = "faroai-recent-compares";
const RECENT_LIMIT = 5;

export function loadRecents(): RecentEval[] {
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

export function pushRecent(item: RecentEval): RecentEval[] {
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

export function clearRecents(): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(RECENT_KEY);
  } catch {
    /* no-op */
  }
}

// ─── Recent comparisons (artist pairs) ─────────────────────────────

export function loadRecentCompares(): RecentCompare[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(RECENT_COMPARE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.slice(0, RECENT_LIMIT);
  } catch {
    return [];
  }
}

export function pushRecentCompare(item: RecentCompare): RecentCompare[] {
  if (typeof window === "undefined") return [];
  const cur = loadRecentCompares();
  // Dedupe by ORDERED pair — Bad Bunny vs Karol G is a different
  // entry from Karol G vs Bad Bunny (positions matter on the radar).
  const filtered = cur.filter(
    (r) => !(r.cm_id_a === item.cm_id_a && r.cm_id_b === item.cm_id_b),
  );
  const next = [item, ...filtered].slice(0, RECENT_LIMIT);
  try {
    localStorage.setItem(RECENT_COMPARE_KEY, JSON.stringify(next));
  } catch {
    /* no-op */
  }
  return next;
}

export function clearRecentCompares(): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(RECENT_COMPARE_KEY);
  } catch {
    /* no-op */
  }
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
