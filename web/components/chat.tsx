"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { fetchSkills, streamChat } from "@/lib/api";
import type { ChatEvent, SkillSummary, Turn } from "@/lib/types";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandItem,
  CommandList,
} from "@/components/ui/command";

// Live state of the in-flight assistant turn — separate from `history`
// so we re-render only the streaming bits at high frequency without
// re-rendering past turns.
type LiveState =
  | { kind: "idle" }
  | {
      kind: "streaming";
      text: string;
      thinking: string[];
      toolStatus: string | null;
      tools: { name: string; label: string }[];
      startedAt: number; // monotonic-ish ms; drives the elapsed timer
    }
  | { kind: "error"; message: string };

// Re-render budget for streaming text. Without this, every text delta
// triggers a setState → ReactMarkdown re-parses the whole accumulated
// string. For a long dossier (~2-3K chars across hundreds of chunks)
// that's hundreds of re-parses; the UI feels sluggish even though the
// network is fast. Same throttle the Streamlit version used.
const TEXT_THROTTLE_MS = 100;

export function Chat() {
  const [history, setHistory] = useState<Turn[]>([]);
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [draft, setDraft] = useState("");
  const [live, setLive] = useState<LiveState>({ kind: "idle" });
  const [elapsed, setElapsed] = useState(0); // seconds since stream start
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  // Pending-text buffer so we can throttle the React render rate.
  const pendingTextRef = useRef("");
  const flushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Load skills once for the picker. Best-effort — we don't block the UI.
  useEffect(() => {
    fetchSkills().then(setSkills).catch(() => {});
  }, []);

  // Auto-scroll to bottom whenever history grows or the stream ticks.
  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [history.length, live]);

  // Tick the elapsed-seconds display while streaming, so the user
  // sees "Thinking… (8s)" instead of an indefinitely pulsing spinner.
  useEffect(() => {
    if (live.kind !== "streaming") {
      setElapsed(0);
      return;
    }
    const id = setInterval(() => {
      setElapsed(Math.floor((Date.now() - live.startedAt) / 1000));
    }, 1000);
    return () => clearInterval(id);
  }, [live.kind, live.kind === "streaming" ? live.startedAt : 0]);

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || live.kind === "streaming") return;
    setHistory((h) => [...h, { role: "user", content: trimmed }]);
    setDraft("");
    setLive({
      kind: "streaming",
      text: "",
      thinking: [],
      toolStatus: null,
      tools: [],
      startedAt: Date.now(),
    });

    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      for await (const ev of streamChat(trimmed, ctrl.signal)) {
        applyEvent(ev);
      }
    } catch (e: unknown) {
      const err = e as { name?: string; message?: string };
      if (err?.name !== "AbortError") {
        setLive({ kind: "error", message: err?.message ?? "stream failed" });
      }
    } finally {
      abortRef.current = null;
    }
  }

  function flushPendingText() {
    const pending = pendingTextRef.current;
    if (!pending) return;
    pendingTextRef.current = "";
    setLive((s) => {
      if (s.kind !== "streaming") return s;
      return { ...s, text: s.text + pending, toolStatus: null };
    });
    flushTimerRef.current = null;
  }

  function applyEvent(ev: ChatEvent) {
    if (ev.kind === "text") {
      // Buffer text deltas; flush at most TEXT_THROTTLE_MS apart so
      // ReactMarkdown doesn't re-parse on every chunk.
      pendingTextRef.current += ev.delta;
      if (!flushTimerRef.current) {
        flushTimerRef.current = setTimeout(flushPendingText, TEXT_THROTTLE_MS);
      }
      return;
    }
    setLive((s) => {
      if (s.kind !== "streaming") return s;
      switch (ev.kind) {
        case "tool_use":
          return {
            ...s,
            toolStatus: ev.label,
            tools: [...s.tools, { name: ev.name, label: ev.label }],
          };
        case "thinking":
          return { ...s, thinking: [...s.thinking, ev.delta] };
        case "result":
          // Flush any pending text BEFORE finalizing so we don't drop
          // the tail of the response on the floor.
          if (pendingTextRef.current) {
            const pendingTail = pendingTextRef.current;
            pendingTextRef.current = "";
            if (flushTimerRef.current) {
              clearTimeout(flushTimerRef.current);
              flushTimerRef.current = null;
            }
            finalizeTurn({ ...s, text: s.text + pendingTail }, ev);
          } else {
            finalizeTurn(s, ev);
          }
          return { kind: "idle" };
        case "error":
          return s;
      }
      return s;
    });
    if (ev.kind === "error") {
      setLive({ kind: "error", message: ev.message });
    }
  }

  function finalizeTurn(s: Extract<LiveState, { kind: "streaming" }>, ev: Extract<ChatEvent, { kind: "result" }>) {
    setHistory((h) => [
      ...h,
      {
        role: "assistant",
        content: s.text || "_(no response)_",
        thinking: s.thinking.length ? s.thinking : undefined,
        toolCalls: s.tools.length ? s.tools : undefined,
        result: {
          run_id: ev.run_id,
          duration_s: ev.duration_s,
          cost_usd: ev.cost_usd,
          status: ev.status,
        },
      },
    ]);
  }

  function onPickSkill(slug: string) {
    setDraft((d) => {
      const prefix = `@${slug} `;
      // Don't double-prefix.
      return d.startsWith(prefix) ? d : prefix + d.replace(/^@\S+\s*/, "");
    });
  }

  return (
    <div className="chat-shell">
      {history.length === 0 && live.kind === "idle" ? (
        <div>
          <div className="empty-greet">How can I help?</div>
          <div className="empty-hint">
            Type a message, or pick a skill below.
          </div>
        </div>
      ) : (
        <div>
          {history.map((turn, i) =>
            turn.role === "user" ? (
              <div key={i} className="chat-user-row">
                <div className="chat-user-bubble">{turn.content}</div>
              </div>
            ) : (
              <AssistantMessage key={i} turn={turn} />
            )
          )}
          {live.kind === "streaming" && (
            <LiveAssistant
              text={live.text}
              thinking={live.thinking}
              toolStatus={live.toolStatus}
              elapsedSec={elapsed}
            />
          )}
          {live.kind === "error" && (
            <div className="chat-status text-red-600">⚠️ {live.message}</div>
          )}
        </div>
      )}
      <div ref={scrollRef} />

      <ChatInputZone
        draft={draft}
        setDraft={setDraft}
        skills={skills}
        onPickSkill={onPickSkill}
        onSend={send}
        disabled={live.kind === "streaming"}
      />
    </div>
  );
}

function AssistantMessage({ turn }: { turn: Turn }) {
  return (
    <div className="chat-assistant">
      {turn.thinking && turn.thinking.length > 0 && (
        <ReasoningPanel blocks={turn.thinking} />
      )}
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{turn.content}</ReactMarkdown>
    </div>
  );
}

function LiveAssistant({
  text,
  thinking,
  toolStatus,
  elapsedSec,
}: {
  text: string;
  thinking: string[];
  toolStatus: string | null;
  elapsedSec: number;
}) {
  // After 3s of waiting with no text and no tool fired, append elapsed
  // seconds so the user knows time is passing — Streamlit's silent dot
  // pulse felt indefinite, several test users said the chat "felt stuck".
  const showTimer = elapsedSec >= 3;
  const baseLabel = toolStatus ?? "Thinking…";
  const statusLabel = showTimer ? `${baseLabel} (${elapsedSec}s)` : baseLabel;
  return (
    <div className="chat-assistant">
      {thinking.length > 0 && <ReasoningPanel blocks={thinking} />}
      {text ? (
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
      ) : (
        <div className="chat-status">
          <span className="dot" />
          {statusLabel}
        </div>
      )}
      {text && toolStatus && (
        <div className="chat-status">
          <span className="dot" />
          {statusLabel}
        </div>
      )}
    </div>
  );
}

function ReasoningPanel({ blocks }: { blocks: string[] }) {
  return (
    <Collapsible className="my-2">
      <CollapsibleTrigger className="text-xs text-[color:var(--text-faint)] hover:text-[color:var(--text-muted)] cursor-pointer">
        💭 Reasoning ({blocks.length} block{blocks.length === 1 ? "" : "s"})
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="reasoning-panel">
          {blocks.map((b, i) => (
            <div key={i}>
              {i > 0 && <hr className="reasoning-sep" />}
              <div style={{ whiteSpace: "pre-wrap" }}>{b}</div>
            </div>
          ))}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

/**
 * Find the `@<token>` the cursor is currently anchored to (no whitespace
 * between the @ and the caret). Returns {start, query} or null.
 *
 * This is what makes typeahead work: as the user types after `@`, we slice
 * the query out and feed it to cmdk for filtering.
 */
function findActiveTrigger(
  value: string,
  caret: number,
): { start: number; query: string } | null {
  const before = value.slice(0, caret);
  const at = before.lastIndexOf("@");
  if (at === -1) return null;
  const between = before.slice(at + 1);
  // Reject if there's whitespace between the @ and caret.
  if (/\s/.test(between)) return null;
  // The @ must be at start-of-string or preceded by whitespace.
  if (at > 0 && !/\s/.test(before[at - 1])) return null;
  return { start: at, query: between };
}

function ChatInputZone({
  draft,
  setDraft,
  skills,
  onPickSkill,
  onSend,
  disabled,
}: {
  draft: string;
  setDraft: (s: string) => void;
  skills: SkillSummary[];
  onPickSkill: (slug: string) => void;
  onSend: (s: string) => void;
  disabled: boolean;
}) {
  const taRef = useRef<HTMLTextAreaElement | null>(null);
  const [trigger, setTrigger] = useState<{ start: number; query: string } | null>(null);
  const [activeIdx, setActiveIdx] = useState(0);

  // Recompute the active @-trigger from the textarea state.
  const refreshTrigger = useCallback(() => {
    const ta = taRef.current;
    if (!ta) return;
    setTrigger(findActiveTrigger(ta.value, ta.selectionStart ?? ta.value.length));
  }, []);

  // Reset highlight when the popup closes or the query changes.
  useEffect(() => {
    setActiveIdx(0);
  }, [trigger?.query, trigger == null]);

  // Filter skills by the @-query (slug then name then description).
  const matches: SkillSummary[] = trigger
    ? rankSkills(skills, trigger.query)
    : [];

  const popupOpen = trigger !== null;

  function insertSkill(slug: string) {
    if (!trigger) return;
    const ta = taRef.current;
    if (!ta) return;
    const before = draft.slice(0, trigger.start);
    const after = draft.slice(ta.selectionStart ?? draft.length);
    const inserted = `@${slug} `;
    const newValue = before + inserted + after;
    const newCaret = before.length + inserted.length;
    setDraft(newValue);
    setTrigger(null);
    // Restore caret position after React commits the new value.
    requestAnimationFrame(() => {
      const t = taRef.current;
      if (t) {
        t.focus();
        t.setSelectionRange(newCaret, newCaret);
      }
    });
  }

  return (
    <div className="chat-input-zone">
      <div className="chat-input-inner">
        {skills.length > 0 && (
          <div className="skill-row">
            {skills.map((s) => (
              <button
                key={s.slug}
                type="button"
                className="skill-chip"
                title={s.description || s.name}
                onClick={() => onPickSkill(s.slug)}
              >
                @{s.slug}
              </button>
            ))}
          </div>
        )}
        <div className="chat-input-shell" style={{ position: "relative" }}>
          {popupOpen && (
            <div className="autocomplete-popup">
              <Command
                shouldFilter={false}
                onKeyDown={(e) => {
                  // cmdk handles arrow keys, but we need to forward Enter
                  // and Esc out via the textarea handler — so swallow none
                  // here and let the textarea onKeyDown drive it.
                  e.stopPropagation();
                }}
              >
                <CommandList>
                  {matches.length === 0 ? (
                    <CommandEmpty>No matching skills</CommandEmpty>
                  ) : (
                    <CommandGroup>
                      {matches.map((s, i) => (
                        <CommandItem
                          key={s.slug}
                          value={s.slug}
                          onSelect={() => insertSkill(s.slug)}
                          onMouseEnter={() => setActiveIdx(i)}
                          data-active={i === activeIdx}
                          className="data-[active=true]:bg-accent"
                        >
                          <div className="flex flex-col gap-0.5">
                            <span className="font-medium">@{s.slug}</span>
                            <span className="text-xs text-muted-foreground line-clamp-2">
                              {s.description || s.name}
                            </span>
                          </div>
                        </CommandItem>
                      ))}
                    </CommandGroup>
                  )}
                </CommandList>
              </Command>
            </div>
          )}
          <textarea
            ref={taRef}
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value);
              // Defer trigger recompute so selectionStart reflects post-change.
              requestAnimationFrame(refreshTrigger);
            }}
            onSelect={refreshTrigger}
            onClick={refreshTrigger}
            onBlur={() => {
              // Small delay so a click on a popup item still fires.
              setTimeout(() => setTrigger(null), 100);
            }}
            placeholder="Type a message, or pick a skill above"
            rows={2}
            disabled={disabled}
            onKeyDown={(e) => {
              if (popupOpen && matches.length > 0) {
                if (e.key === "ArrowDown") {
                  e.preventDefault();
                  setActiveIdx((i) => (i + 1) % matches.length);
                  return;
                }
                if (e.key === "ArrowUp") {
                  e.preventDefault();
                  setActiveIdx((i) => (i - 1 + matches.length) % matches.length);
                  return;
                }
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  insertSkill(matches[activeIdx].slug);
                  return;
                }
                if (e.key === "Tab") {
                  e.preventDefault();
                  insertSkill(matches[activeIdx].slug);
                  return;
                }
                if (e.key === "Escape") {
                  e.preventDefault();
                  setTrigger(null);
                  return;
                }
              }
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                onSend(draft);
              }
            }}
          />
        </div>
      </div>
    </div>
  );
}

function rankSkills(skills: SkillSummary[], query: string): SkillSummary[] {
  const q = query.toLowerCase();
  if (!q) return skills;
  // Tier ranking: slug-startsWith > slug-contains > name-startsWith > name-contains > desc-contains
  const ranked = skills
    .map((s) => {
      const slug = s.slug.toLowerCase();
      const name = (s.name || "").toLowerCase();
      const desc = (s.description || "").toLowerCase();
      let tier = -1;
      if (slug.startsWith(q)) tier = 0;
      else if (slug.includes(q)) tier = 1;
      else if (name.startsWith(q)) tier = 2;
      else if (name.includes(q)) tier = 3;
      else if (desc.includes(q)) tier = 4;
      return tier === -1 ? null : { skill: s, tier };
    })
    .filter((x): x is { skill: SkillSummary; tier: number } => x !== null);
  ranked.sort((a, b) => a.tier - b.tier || a.skill.slug.localeCompare(b.skill.slug));
  return ranked.map((r) => r.skill);
}
