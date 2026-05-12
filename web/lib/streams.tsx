"use client";

// Background streaming for chats. The provider is mounted at the layout
// level (above route children), so a stream started in the chat page
// keeps running when the user navigates to /skills, /memory, etc., and
// when they start a new conversation. The chat page reads/writes the
// active stream's state through the useConversationStream hook.
//
// Multiple streams can run in parallel — one per conversation id.
// The sidebar polls activeStreamIds() to show "thinking" spinners
// next to each conversation row.

import {
  type ReactNode,
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
} from "react";

import { streamChat } from "./api";
import {
  type Conversation,
  getConversation,
  saveConversation,
} from "./conversations";
import type { Turn, TurnError } from "./types";

export type StreamSnapshot = {
  conversationId: string;
  status: "streaming" | "done" | "error";
  text: string;
  thinking: string[];
  toolStatus: string | null;
  tools: { name: string; label: string }[];
  startedAt: number;
  errorMessage?: string;
  errorDetails?: TurnError; // structured: title + hint + fix_url + raw
  // The result event's session_id, set when status becomes "done".
  sessionId?: string;
  // Set when the LLM's evaluate_artist call returned successfully —
  // the chat renders a compact pill card instead of dumping the
  // dossier markdown wall.
  evaluatePill?: Turn["evaluatePill"];
  // Sibling for compare_artists.
  comparePill?: Turn["comparePill"];
};

type StreamHandle = {
  controller: AbortController;
  snapshot: StreamSnapshot;
};

type Ctx = {
  /** Live snapshot of one conversation's stream, or null if idle. */
  getSnapshot: (conversationId: string) => StreamSnapshot | null;
  /** Set of conversation IDs currently streaming (for sidebar badges). */
  activeStreamIds: Set<string>;
  /** Start a new turn in `conversationId` with the given prompt. */
  startTurn: (conversationId: string, prompt: string) => void;
  /** Cancel the in-flight stream for one conversation, if any. */
  cancelTurn: (conversationId: string) => void;
};

const StreamCtx = createContext<Ctx | null>(null);

const TEXT_THROTTLE_MS = 100;
const THINKING_PREFIX = "\x01THINK\x01"; // mirror of core/claude_runner.py

export function ConversationStreamsProvider({ children }: { children: ReactNode }) {
  // We keep the live mutable state in refs (so cross-tick updates don't
  // race) and mirror it into a state Map keyed by conversation id so
  // React subscribers re-render on changes.
  const handlesRef = useRef<Map<string, StreamHandle>>(new Map());
  const [snapshots, setSnapshots] = useState<Map<string, StreamSnapshot>>(new Map());
  const [activeIds, setActiveIds] = useState<Set<string>>(new Set());

  // Bump the snapshots Map identity so React re-renders consumers.
  const bump = useCallback(() => {
    setSnapshots(new Map(collectSnapshots(handlesRef.current)));
    const streamingIds = Array.from(handlesRef.current.keys()).filter(
      (id) => handlesRef.current.get(id)?.snapshot.status === "streaming",
    );
    setActiveIds(new Set(streamingIds));
  }, []);

  const cancelTurn = useCallback((conversationId: string) => {
    const h = handlesRef.current.get(conversationId);
    if (!h) return;
    h.controller.abort();
    handlesRef.current.delete(conversationId);
    bump();
  }, [bump]);

  const startTurn = useCallback((conversationId: string, prompt: string) => {
    // If a previous stream is still running for this conversation, abort it
    // before starting a new one. (Shouldn't happen in normal usage — the
    // chat input disables itself while streaming — but be defensive.)
    cancelTurn(conversationId);

    const handle: StreamHandle = {
      controller: new AbortController(),
      snapshot: {
        conversationId,
        status: "streaming",
        text: "",
        thinking: [],
        toolStatus: null,
        tools: [],
        startedAt: Date.now(),
      },
    };
    handlesRef.current.set(conversationId, handle);
    bump();

    // Resolve resume_session_id (transitional — V2 agent runner ignores
    // it) and the conversation's prior turns. Prior turns are replayed
    // server-side as the message history so the V2 agent loop has the
    // same context Claude Code's --resume used to provide.
    const conv = getConversation(conversationId);
    const resumeSessionId = conv?.claudeSessionId ?? null;
    const priorTurns = conv?.turns ?? [];

    // Throttle text deltas: same 100ms cadence the old chat.tsx had.
    let pendingText = "";
    let flushTimer: ReturnType<typeof setTimeout> | null = null;
    const flushPending = () => {
      if (!pendingText) return;
      handle.snapshot = {
        ...handle.snapshot,
        text: handle.snapshot.text + pendingText,
        toolStatus: null,
      };
      pendingText = "";
      flushTimer = null;
      bump();
    };

    (async () => {
      try {
        for await (const ev of streamChat(prompt, handle.controller.signal, { resumeSessionId, priorTurns })) {
          if (ev.kind === "tool_use") {
            handle.snapshot = {
              ...handle.snapshot,
              toolStatus: ev.label,
              tools: [...handle.snapshot.tools, { name: ev.name, label: ev.label }],
            };
            bump();
          } else if (ev.kind === "thinking") {
            // strip the THINKING_PREFIX (server already strips it on text events,
            // but thinking events carry the raw text)
            const delta = ev.delta.startsWith(THINKING_PREFIX)
              ? ev.delta.slice(THINKING_PREFIX.length)
              : ev.delta;
            handle.snapshot = {
              ...handle.snapshot,
              thinking: [...handle.snapshot.thinking, delta],
            };
            bump();
          } else if (ev.kind === "text") {
            pendingText += ev.delta;
            if (!flushTimer) flushTimer = setTimeout(flushPending, TEXT_THROTTLE_MS);
          } else if (ev.kind === "evaluate_pill") {
            handle.snapshot = {
              ...handle.snapshot,
              evaluatePill: {
                artist: ev.artist,
                cm_id: ev.cm_id,
                image: ev.image ?? undefined,
                tier: ev.tier ?? undefined,
                score: ev.score ?? undefined,
                inline: true,
              },
            };
            bump();
          } else if (ev.kind === "compare_pill") {
            handle.snapshot = {
              ...handle.snapshot,
              comparePill: {
                artist_a: ev.artist_a,
                artist_b: ev.artist_b,
                cm_id_a: ev.cm_id_a,
                cm_id_b: ev.cm_id_b,
                image_a: ev.image_a ?? undefined,
                image_b: ev.image_b ?? undefined,
                tier_a: ev.tier_a ?? undefined,
                tier_b: ev.tier_b ?? undefined,
                score_a: ev.score_a ?? undefined,
                score_b: ev.score_b ?? undefined,
                inline: true,
              },
            };
            bump();
          } else if (ev.kind === "result") {
            // Make sure no buffered text is dropped.
            if (flushTimer) {
              clearTimeout(flushTimer);
              flushTimer = null;
            }
            flushPending();
            handle.snapshot = {
              ...handle.snapshot,
              status: "done",
              sessionId: ev.session_id ?? undefined,
            };
            // Persist the assistant turn + session id to localStorage.
            // When the run errored, persist the structured error
            // alongside so the chat shows a banner with hint + fix
            // link instead of a mute "(no response)".
            const c = getConversation(conversationId);
            if (c) {
              const erroredOut = ev.status === "error" || !!handle.snapshot.errorDetails;
              const assistantTurn: Turn = {
                role: "assistant",
                content: handle.snapshot.text || "",
                thinking: handle.snapshot.thinking.length ? handle.snapshot.thinking : undefined,
                toolCalls: handle.snapshot.tools.length ? handle.snapshot.tools : undefined,
                result: {
                  run_id: ev.run_id,
                  duration_s: ev.duration_s,
                  cost_usd: ev.cost_usd,
                  status: ev.status,
                },
                error: erroredOut
                  ? handle.snapshot.errorDetails ?? { message: handle.snapshot.errorMessage ?? "Unknown error" }
                  : undefined,
                evaluatePill: handle.snapshot.evaluatePill,
                comparePill: handle.snapshot.comparePill,
              };
              const updated: Conversation = {
                ...c,
                turns: [...c.turns, assistantTurn],
                claudeSessionId: ev.session_id ?? c.claudeSessionId,
              };
              saveConversation(updated);
            }
            // Clean up the handle a moment later so the chat page sees
            // the final state, then transitions to idle.
            setTimeout(() => {
              handlesRef.current.delete(conversationId);
              bump();
            }, 50);
            bump();
          } else if (ev.kind === "error") {
            handle.snapshot = {
              ...handle.snapshot,
              status: "error",
              errorMessage: ev.message,
              errorDetails: {
                message: ev.message,
                hint: ev.hint,
                fix_url: ev.fix_url,
                raw: ev.raw,
              },
            };
            bump();
          }
        }
      } catch (e: unknown) {
        const err = e as { name?: string; message?: string };
        if (err?.name !== "AbortError") {
          handle.snapshot = {
            ...handle.snapshot,
            status: "error",
            errorMessage: err?.message ?? "stream failed",
          };
          bump();
        }
      } finally {
        if (flushTimer) clearTimeout(flushTimer);
      }
    })();
  }, [bump, cancelTurn]);

  const getSnapshot = useCallback(
    (conversationId: string) => snapshots.get(conversationId) ?? null,
    [snapshots],
  );

  return (
    <StreamCtx.Provider value={{ getSnapshot, activeStreamIds: activeIds, startTurn, cancelTurn }}>
      {children}
    </StreamCtx.Provider>
  );
}

export function useConversationStream(conversationId: string | null) {
  const ctx = useContext(StreamCtx);
  if (!ctx) throw new Error("useConversationStream outside ConversationStreamsProvider");
  const snapshot = conversationId ? ctx.getSnapshot(conversationId) : null;
  // Note: the hook binds these to the id at call time — only safe when
  // the caller already has an established conversation. For the
  // first-message-in-a-new-conversation case (where the id is created
  // synchronously in send()), use useStreams() and pass the freshly-
  // minted id directly.
  const startTurn = useCallback(
    (prompt: string) => {
      if (conversationId) ctx.startTurn(conversationId, prompt);
    },
    [ctx, conversationId],
  );
  const cancelTurn = useCallback(() => {
    if (conversationId) ctx.cancelTurn(conversationId);
  }, [ctx, conversationId]);
  return { snapshot, startTurn, cancelTurn };
}

/** Raw provider access — for callers that need to start a stream with
 *  a conversation id that didn't exist at render time. */
export function useStreams(): Ctx {
  const ctx = useContext(StreamCtx);
  if (!ctx) throw new Error("useStreams outside ConversationStreamsProvider");
  return ctx;
}

export function useActiveStreamIds(): Set<string> {
  const ctx = useContext(StreamCtx);
  if (!ctx) throw new Error("useActiveStreamIds outside ConversationStreamsProvider");
  return ctx.activeStreamIds;
}

// Helper: copy the current handle snapshots into a plain array.
function collectSnapshots(handles: Map<string, StreamHandle>): Array<[string, StreamSnapshot]> {
  return Array.from(handles.entries()).map(([id, h]) => [id, h.snapshot]);
}
