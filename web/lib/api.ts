// API client — talks to FastAPI on the same origin (proxied in dev,
// served directly in prod where the static export is mounted by FastAPI).

import type { ChatEvent, SkillSummary } from "./types";

const BASE = "/api";

export async function fetchSkills(): Promise<SkillSummary[]> {
  const r = await fetch(`${BASE}/skills`, { cache: "no-store" });
  if (!r.ok) throw new Error(`/api/skills ${r.status}`);
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
): AsyncIterableIterator<ChatEvent> {
  console.log(`[api] POST /api/chat (${prompt.length} chars)`);
  const r = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ prompt }),
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
    // SSE messages are separated by blank lines. Process whole messages
    // only — the next chunk may complete a partial message.
    let idx;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const ev = parseSseBlock(block);
      if (ev) yield ev;
    }
  }
}

function parseSseBlock(block: string): ChatEvent | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
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
    default:
      return null;
  }
}
