// Conversation persistence — server-backed since v0.5.3.
//
// Storage moved from browser localStorage to a JSON file in the
// per-user config dir (see core/storage.py + api/routes/conversations.py).
// Motivation: pywebview's WebKit data store wasn't surviving py2app
// rebuilds across version bumps, so every update silently wiped the
// user's chat history. Disk-side storage takes that whole class of
// failure off the table.
//
// We keep the historical synchronous API surface (listConversations(),
// saveConversation(c), etc.) so existing call sites don't change.
// Reads return whatever's in the in-memory cache; on first call we
// kick off a hydration fetch in the background and dispatch the
// CHANGE event when it lands — same hook the sidebar already
// listens on. Writes update the cache immediately AND fire a PUT
// in the background. The active-conversation id stays in
// localStorage because it's strictly a per-browser-window UX state,
// not user content.

import type { Turn } from "./types";

const CHANGE_EVENT = "faroai:conversations-changed";
const ACTIVE_KEY = "faroai.activeConversation";
// Legacy localStorage key we drain into the server on first launch
// after the v0.5.3 upgrade.
const LEGACY_STORAGE_KEY = "faroai.conversations.v1";

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

// ─── In-memory cache (hydrated from the server) ─────────────────────────

let cache: Record<string, Conversation> | null = null;
let hydratePromise: Promise<void> | null = null;

function notifyChanged(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(CHANGE_EVENT));
}

async function fetchAll(): Promise<Conversation[]> {
  const resp = await fetch("/api/conversations", { cache: "no-store" });
  if (!resp.ok) throw new Error(`GET /api/conversations: HTTP ${resp.status}`);
  const data = await resp.json();
  const list = Array.isArray(data?.conversations) ? data.conversations : [];
  return list as Conversation[];
}

async function migrateLegacyLocalStorage(): Promise<Conversation[] | null> {
  // One-time pull from the v0.5.2 localStorage blob. Returns the
  // imported conversations on success, null if there was nothing to
  // migrate, throws only if the POST itself fails (in which case the
  // caller falls back to whatever was already on the server, which
  // is empty — that's fine; the legacy blob stays put so a retry
  // can pick it up).
  if (typeof window === "undefined") return null;
  let legacy: { conversations?: Record<string, Conversation> } | null = null;
  try {
    const raw = window.localStorage.getItem(LEGACY_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object" && parsed.conversations) {
      legacy = parsed;
    }
  } catch {
    return null;
  }
  if (!legacy?.conversations) return null;
  const items = Object.values(legacy.conversations);
  if (items.length === 0) return null;

  const resp = await fetch("/api/conversations/migrate", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ conversations: items }),
  });
  if (!resp.ok) throw new Error(`migrate failed: HTTP ${resp.status}`);
  // Only clear localStorage AFTER the server has accepted the import —
  // otherwise a network blip during upgrade would lose history.
  try {
    window.localStorage.removeItem(LEGACY_STORAGE_KEY);
  } catch {
    /* no-op */
  }
  return items;
}

async function hydrate(): Promise<void> {
  let serverItems: Conversation[];
  try {
    serverItems = await fetchAll();
  } catch {
    // Network/storage error on hydrate: keep cache empty so the UI
    // renders the empty state rather than crashing. A later mutation
    // will retry indirectly when it tries to PUT.
    cache = {};
    notifyChanged();
    return;
  }

  // If the server is empty and the user has legacy localStorage
  // entries (the v0.5.2 → v0.5.3 path), drain them into the server
  // and use the migrated set as the hydrated cache.
  if (serverItems.length === 0) {
    try {
      const migrated = await migrateLegacyLocalStorage();
      if (migrated && migrated.length > 0) {
        serverItems = migrated;
      }
    } catch {
      // Migration POST failed; proceed with the empty server set.
      // The legacy blob is still in localStorage so the next launch
      // can retry.
    }
  }

  const next: Record<string, Conversation> = {};
  for (const c of serverItems) {
    if (c && typeof c === "object" && typeof c.id === "string") next[c.id] = c;
  }
  cache = next;
  notifyChanged();
}

function ensureHydrated(): void {
  if (cache !== null) return;
  if (typeof window === "undefined") {
    cache = {};
    return;
  }
  if (!hydratePromise) {
    cache = {}; // expose an empty view until hydration lands
    hydratePromise = hydrate();
  }
}

// ─── Public API (synchronous reads, fire-and-forget writes) ─────────────

export function listConversations(): Conversation[] {
  ensureHydrated();
  if (!cache) return [];
  return Object.values(cache).sort((a, b) => b.updatedAt - a.updatedAt);
}

export function getConversation(id: string): Conversation | null {
  ensureHydrated();
  return cache?.[id] ?? null;
}

export function createConversation(seedPrompt?: string): Conversation {
  ensureHydrated();
  const now = Date.now();
  const id = `c_${now.toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
  const c: Conversation = {
    id,
    title: seedPrompt ? truncateTitle(seedPrompt) : "New chat",
    createdAt: now,
    updatedAt: now,
    turns: [],
  };
  if (!cache) cache = {};
  cache[id] = c;
  notifyChanged();
  void persistConversation(c);
  return c;
}

export function saveConversation(c: Conversation): void {
  ensureHydrated();
  const updated: Conversation = { ...c, updatedAt: Date.now() };
  if (!cache) cache = {};
  cache[updated.id] = updated;
  notifyChanged();
  void persistConversation(updated);
}

export function deleteConversation(id: string): void {
  ensureHydrated();
  if (cache && cache[id]) {
    delete cache[id];
    notifyChanged();
  }
  void fetch(`/api/conversations/${encodeURIComponent(id)}`, {
    method: "DELETE",
  }).catch(() => {
    /* best-effort; if it fails the next hydrate will rehydrate from
       the server's authoritative copy */
  });
  if (getActiveConversationId() === id) setActiveConversationId(null);
}

async function persistConversation(c: Conversation): Promise<void> {
  try {
    await fetch(`/api/conversations/${encodeURIComponent(c.id)}`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(c),
    });
  } catch {
    /* best-effort — the cache still holds the user's data locally,
       and a hard reload will rehydrate from the server. */
  }
}

// Active-conversation id stays in localStorage: it's a per-window UX
// pointer, not durable user content. If it gets wiped on an update,
// the user just lands on /new-chat — no data lost.
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
    if (e.key === ACTIVE_KEY) cb();
  };
  window.addEventListener(CHANGE_EVENT, sameTab);
  window.addEventListener("storage", crossTab);
  // Trigger hydration on first subscribe so the sidebar populates
  // without needing a listConversations() call first.
  ensureHydrated();
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
