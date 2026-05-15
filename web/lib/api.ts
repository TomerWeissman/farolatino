// API client — talks to FastAPI on the same origin (proxied in dev,
// served directly in prod where the static export is mounted by FastAPI).

import type { ChatEvent, DisambigCandidate, EvaluateResponse, SkillSummary, Turn } from "./types";

const BASE = "/api";

export async function fetchSkills(): Promise<SkillSummary[]> {
  const r = await fetch(`${BASE}/skills`, { cache: "no-store" });
  if (!r.ok) throw new Error(`/api/skills ${r.status}`);
  return r.json();
}

/**
 * POST /api/evaluate — runs the @evaluate skill, returns the full dossier
 * JSON for the dashboard at /evaluate.
 *
 * Three response shapes — caller distinguishes by which keys are
 * present (see EvaluateResponse in types.ts):
 *   - { dossier, cm_id, rendered_markdown }: success
 *   - { needs_disambiguation, query }: ambiguous artist name
 *   - { error }: tool error (Chartmetric down, etc.)
 *
 * cmId is passed when the user picks a disambiguation candidate so
 * the second call skips the search step and goes straight to the
 * cached data fetch.
 */
export async function evaluate(
  artist: string,
  cmId?: number,
  signal?: AbortSignal,
): Promise<EvaluateResponse> {
  const body: Record<string, unknown> = { artist };
  if (cmId) body.cm_id = cmId;
  const r = await fetch(`${BASE}/evaluate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!r.ok) {
    const text = await r.text().catch(() => r.statusText);
    throw new Error(`/api/evaluate ${r.status}: ${text.slice(0, 200)}`);
  }
  return r.json();
}

/**
 * POST /api/search — cheap Chartmetric candidate lookup with no scoring.
 *
 * Powers the v0.5.3 "See other matches" panel on Evaluate / Compare
 * and the URL-paste fallback when a name returns zero hits. URLs
 * (Spotify, Chartmetric, YouTube, etc.) are auto-routed server-side
 * via search_artist_by_url, so the caller doesn't have to detect them.
 */
export type SearchResponse = {
  query: string;
  count: number;
  artists: DisambigCandidate[];
  resolved_from_url?: string | null;
  error?: string | null;
};

export async function searchArtists(
  query: string,
  limit = 10,
  signal?: AbortSignal,
): Promise<SearchResponse> {
  const r = await fetch(`${BASE}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, limit }),
    signal,
  });
  if (!r.ok) {
    const text = await r.text().catch(() => r.statusText);
    throw new Error(`/api/search ${r.status}: ${text.slice(0, 200)}`);
  }
  return r.json();
}

export async function fetchPersona(): Promise<{ content: string }> {
  const r = await fetch(`${BASE}/persona`, { cache: "no-store" });
  if (!r.ok) throw new Error(`/api/persona ${r.status}`);
  return r.json();
}

export async function fetchRuns(limit = 20) {
  const r = await fetch(`${BASE}/runs?limit=${limit}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`/api/runs ${r.status}`);
  return r.json();
}

export async function fetchRun(runId: string) {
  const r = await fetch(`${BASE}/runs/${runId}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`/api/runs/${runId} ${r.status}`);
  return r.json();
}

/**
 * POST /api/chat and yield SSE events as they arrive.
 *
 * We don't use EventSource because POST + JSON body isn't supported
 * in the EventSource API. Instead we read the response body as a
 * stream and parse the SSE wire format ourselves — minimal, ~30 lines.
 */
export async function* streamChat(
  prompt: string,
  signal?: AbortSignal,
  opts?: { resumeSessionId?: string | null; priorTurns?: Turn[] },
): AsyncIterableIterator<ChatEvent> {
  // V2 multi-turn: backend has no session memory (the Claude Code CLI is
  // gone). The frontend ships its localStorage-cached turns on every
  // request and the agent runner replays them as the message history.
  // resume_session_id is kept transitional but ignored by the runner.
  const messages = (opts?.priorTurns ?? []).map((t) => ({
    role: t.role,
    content: t.content,
  }));
  console.log(`[api] POST /api/chat (${prompt.length} chars, ${messages.length} prior turns)`);
  const body: Record<string, unknown> = { prompt, messages };
  if (opts?.resumeSessionId) body.resume_session_id = opts.resumeSessionId;
  const r = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });
  console.log(`[api] response: ${r.status} ${r.statusText} (body=${!!r.body})`);
  if (!r.ok || !r.body) {
    throw new Error(`/api/chat ${r.status}`);
  }
  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let chunkNum = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      console.log(`[api] stream done after ${chunkNum} chunks`);
      break;
    }
    chunkNum++;
    buffer += decoder.decode(value, { stream: true });
    // SSE messages are separated by a blank line. The spec allows either
    // `\n\n` or `\r\n\r\n` and individual ASGI implementations differ —
    // sse-starlette specifically emits CRLF, which an `indexOf("\n\n")`
    // never matches, so 20 chunks of perfectly valid SSE yielded zero
    // events on the previous build. Match both with a regex.
    let m;
    while ((m = SSE_BOUNDARY.exec(buffer)) !== null) {
      const block = buffer.slice(0, m.index);
      buffer = buffer.slice(m.index + m[0].length);
      const ev = parseSseBlock(block);
      if (ev) yield ev;
    }
  }
}

// `\r?\n\r?\n` matches the message terminator in either CRLF or LF form.
// `g` flag is intentionally absent — we slice the buffer between hits, so
// each iteration uses a fresh exec from index 0.
const SSE_BOUNDARY = /\r?\n\r?\n/;
const SSE_LINE = /\r?\n/;

function parseSseBlock(block: string): ChatEvent | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of block.split(SSE_LINE)) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    // ignore comments + id: + retry:
  }
  if (dataLines.length === 0) return null;
  let data: Record<string, unknown>;
  try {
    data = JSON.parse(dataLines.join("\n"));
  } catch {
    return null;
  }
  switch (event) {
    case "tool_use":
      return { kind: "tool_use", ...data } as ChatEvent;
    case "thinking":
      return { kind: "thinking", ...data } as ChatEvent;
    case "text":
      return { kind: "text", ...data } as ChatEvent;
    case "result":
      return { kind: "result", ...data } as ChatEvent;
    case "error":
      return { kind: "error", ...data } as ChatEvent;
    case "evaluate_pill":
      return { kind: "evaluate_pill", ...data } as ChatEvent;
    case "compare_pill":
      return { kind: "compare_pill", ...data } as ChatEvent;
    default:
      return null;
  }
}
