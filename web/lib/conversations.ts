// Conversation persistence. localStorage-backed for now — works across
// page navigations + browser restarts (same browser only). Move to a
// /api/conversations endpoint later if multi-browser sync is needed.
//
// Storage shape (single JSON blob):
//   faroai.conversations.v1   → { conversations: Record<id, Conversation> }
//   faroai.activeConversation → id of the currently-loaded conversation
//
// Single-blob writes are fine at our scale: a chat session of 50 turns is
// ~50KB; localStorage caps at 5MB. Re-write whole blob on each save so
// we don't have to manage incremental persistence.

import type { Turn } from "./types";

const STORAGE_KEY = "faroai.conversations.v1";
const ACTIVE_KEY = "faroai.activeConversation";
const CHANGE_EVENT = "faroai:conversations-changed";

export type StoredTurn = Turn;

export type Conversation = {
  id: string;
  title: string;
  createdAt: number; // epoch ms
  updatedAt: number;
  turns: StoredTurn[];
  // claude --print's session_id from the most recent assistant turn.
  // Passed as `resume_session_id` on the next user message so the
  // model continues the same context instead of starting fresh.
  claudeSessionId?: string;
};

type Blob = { conversations: Record<string, Conversation> };

// ─── Storage I/O ────────────────────────────────────────────────────────
function readBlob(): Blob {
  if (typeof window === "undefined") return { conversations: {} };
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return { conversations: {} };
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object" && parsed.conversations) {
      return parsed as Blob;
    }
  } catch {
    // localStorage corrupted — start fresh rather than crash.
  }
  return { conversations: {} };
}

function writeBlob(blob: Blob): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(blob));
  notifyChanged();
}

function notifyChanged(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(CHANGE_EVENT));
}

// ─── Public API ─────────────────────────────────────────────────────────

/** Newest-first list of all conversations. */
export function listConversations(): Conversation[] {
  return Object.values(readBlob().conversations).sort((a, b) => b.updatedAt - a.updatedAt);
}

export function getConversation(id: string): Conversation | null {
  return readBlob().conversations[id] ?? null;
}

export function createConversation(seedPrompt?: string): Conversation {
  const now = Date.now();
  const id = `c_${now.toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
  const c: Conversation = {
    id,
    title: seedPrompt ? truncateTitle(seedPrompt) : "New chat",
    createdAt: now,
    updatedAt: now,
    turns: [],
  };
  const blob = readBlob();
  blob.conversations[id] = c;
  writeBlob(blob);
  return c;
}

export function saveConversation(c: Conversation): void {
  const blob = readBlob();
  blob.conversations[c.id] = { ...c, updatedAt: Date.now() };
  writeBlob(blob);
}

export function deleteConversation(id: string): void {
  const blob = readBlob();
  delete blob.conversations[id];
  writeBlob(blob);
  if (getActiveConversationId() === id) setActiveConversationId(null);
}

export function getActiveConversationId(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ACTIVE_KEY);
}

export function setActiveConversationId(id: string | null): void {
  if (typeof window === "undefined") return;
  if (id) window.localStorage.setItem(ACTIVE_KEY, id);
  else window.localStorage.removeItem(ACTIVE_KEY);
  notifyChanged();
}

/** Subscribe to any change in the conversation store (this tab + cross-tab).
 *  Returns an unsubscribe fn. */
export function subscribeToConversations(cb: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const sameTab = () => cb();
  const crossTab = (e: StorageEvent) => {
    if (e.key === STORAGE_KEY || e.key === ACTIVE_KEY) cb();
  };
  window.addEventListener(CHANGE_EVENT, sameTab);
  window.addEventListener("storage", crossTab);
  return () => {
    window.removeEventListener(CHANGE_EVENT, sameTab);
    window.removeEventListener("storage", crossTab);
  };
}

// ─── Helpers ────────────────────────────────────────────────────────────

function truncateTitle(prompt: string, max = 50): string {
  // Drop a leading @skill prefix if present so the title is the actual subject.
  const stripped = prompt.replace(/^@\S+\s*/, "").trim() || prompt.trim();
  if (stripped.length <= max) return stripped;
  return stripped.slice(0, max - 1).trim() + "…";
}

/** Group conversations into Today / Yesterday / Last week / Older
 *  buckets — used by the sidebar's date-grouped list. The `labelKey`
 *  is an i18n key the sidebar resolves via `t()` at render time, so
 *  this util stays language-agnostic. */
export function groupByRecency(
  items: Conversation[],
): Array<{ labelKey: string; items: Conversation[] }> {
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const startOfYesterday = startOfToday - 24 * 3600_000;
  const startOfWeek = startOfToday - 6 * 24 * 3600_000;

  const buckets: Record<string, Conversation[]> = {
    today: [],
    yesterday: [],
    week: [],
    older: [],
  };
  for (const c of items) {
    if (c.updatedAt >= startOfToday) buckets.today.push(c);
    else if (c.updatedAt >= startOfYesterday) buckets.yesterday.push(c);
    else if (c.updatedAt >= startOfWeek) buckets.week.push(c);
    else buckets.older.push(c);
  }
  return [
    { labelKey: "sidebar.history.today", items: buckets.today },
    { labelKey: "sidebar.history.yesterday", items: buckets.yesterday },
    { labelKey: "sidebar.history.last_week", items: buckets.week },
    { labelKey: "sidebar.history.older", items: buckets.older },
  ].filter((g) => g.items.length > 0);
}
