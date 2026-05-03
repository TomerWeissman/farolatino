"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { fetchSkills } from "@/lib/api";
import type { SkillSummary, Turn } from "@/lib/types";
import {
  type Conversation,
  createConversation,
  getActiveConversationId,
  getConversation,
  saveConversation,
  setActiveConversationId,
  subscribeToConversations,
} from "@/lib/conversations";
import { useConversationStream, useStreams, type StreamSnapshot } from "@/lib/streams";
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

export function Chat() {
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [draft, setDraft] = useState("");
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [historyTick, setHistoryTick] = useState(0); // bumps when conversation turns change
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // The streams provider owns all in-flight stream state. It survives
  // navigation between routes and supports multiple parallel streams
  // (one per conversation), so navigating away or starting a new chat
  // doesn't kill ongoing thinking.
  const { snapshot } = useConversationStream(conversation?.id ?? null);
  // Raw provider access — needed because send() can MINT a new
  // conversation id and start a stream against it in the same call,
  // before any re-render has bound `useConversationStream` to that
  // new id.
  const streams = useStreams();

  // Skills for the @-typeahead.
  useEffect(() => {
    fetchSkills().then(setSkills).catch(() => {});
  }, []);

  // Resync the active conversation from localStorage whenever the sidebar
  // (or this component) signals a change.
  useEffect(() => {
    const sync = () => {
      const id = getActiveConversationId();
      if (!id) {
        setConversation(null);
        return;
      }
      const c = getConversation(id);
      if (c) {
        setConversation(c);
      } else {
        setActiveConversationId(null);
        setConversation(null);
      }
      setHistoryTick((t) => t + 1);
    };
    sync();
    return subscribeToConversations(sync);
  }, []);

  // Auto-scroll on new history entries or stream tick.
  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [historyTick, snapshot?.text, snapshot?.thinking.length]);

  // Refresh `conversation` when the stream completes — saveConversation
  // (called from the provider on result) fires the change event, which
  // our subscribeToConversations sync above handles. So we just need
  // to bump the tick to re-render with the new turns.
  useEffect(() => {
    if (snapshot?.status === "done") {
      setHistoryTick((t) => t + 1);
    }
  }, [snapshot?.status]);

  // Live elapsed timer — drives the "Thinking… (12s)" pill text.
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (snapshot?.status !== "streaming") {
      setElapsed(0);
      return;
    }
    const id = setInterval(() => {
      setElapsed(Math.floor((Date.now() - snapshot.startedAt) / 1000));
    }, 1000);
    return () => clearInterval(id);
  }, [snapshot?.status, snapshot?.startedAt]);

  function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed) return;
    if (snapshot?.status === "streaming") return;

    // Lazy-create on first message so empty chats don't pollute the sidebar.
    let active = conversation;
    if (!active) {
      active = createConversation(trimmed);
      setActiveConversationId(active.id);
      setConversation(active);
    }
    const userTurn: Turn = { role: "user", content: trimmed };
    const updated: Conversation = { ...active, turns: [...active.turns, userTurn] };
    saveConversation(updated);
    setConversation(updated);
    setDraft("");
    // Hand off to the streams provider, calling with the active id
    // directly (which may have just been created in this same call).
    streams.startTurn(active.id, trimmed);
  }

  // The "history" we render is the conversation's persisted turns plus
  // (if a stream is active for THIS conversation) the live snapshot.
  // Reading conversation.turns directly each render is fine — the bump
  // above triggers re-render after saveConversation.
  const history = conversation?.turns ?? [];
  const isError = snapshot?.status === "error";
  const isStreaming = snapshot?.status === "streaming";

  return (
    <div className="chat-shell">
      {history.length === 0 && !isStreaming && !isError ? (
        <div>
          <div className="empty-greet">How can I help?</div>
          <div className="empty-hint">
            Type a message, or use <code>@</code> to pick a skill.
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
          {isStreaming && snapshot && (
            <LiveAssistant snapshot={snapshot} elapsedSec={elapsed} />
          )}
          {isError && snapshot?.errorMessage && (
            <div className="chat-status text-red-600">⚠️ {snapshot.errorMessage}</div>
          )}
        </div>
      )}
      <div ref={scrollRef} />

      <ChatInputZone
        draft={draft}
        setDraft={setDraft}
        skills={skills}
        onSend={send}
        disabled={isStreaming}
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
  snapshot,
  elapsedSec,
}: {
  snapshot: StreamSnapshot;
  elapsedSec: number;
}) {
  const { text, thinking, toolStatus } = snapshot;
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

// ─── Chat input + @-autocomplete ────────────────────────────────────────

function findActiveTrigger(
  value: string,
  caret: number,
): { start: number; query: string } | null {
  const before = value.slice(0, caret);
  const at = before.lastIndexOf("@");
  if (at === -1) return null;
  const between = before.slice(at + 1);
  if (/\s/.test(between)) return null;
  if (at > 0 && !/\s/.test(before[at - 1])) return null;
  return { start: at, query: between };
}

function ChatInputZone({
  draft,
  setDraft,
  skills,
  onSend,
  disabled,
}: {
  draft: string;
  setDraft: (s: string) => void;
  skills: SkillSummary[];
  onSend: (s: string) => void;
  disabled: boolean;
}) {
  const taRef = useRef<HTMLTextAreaElement | null>(null);
  const popupRef = useRef<HTMLDivElement | null>(null);
  const [trigger, setTrigger] = useState<{ start: number; query: string } | null>(null);
  const [activeIdx, setActiveIdx] = useState(0);

  const refreshTrigger = useCallback(() => {
    const ta = taRef.current;
    if (!ta) return;
    setTrigger(findActiveTrigger(ta.value, ta.selectionStart ?? ta.value.length));
  }, []);

  useEffect(() => {
    setActiveIdx(0);
  }, [trigger?.query, trigger == null]);

  useEffect(() => {
    if (trigger === null) return;
    const el = popupRef.current?.querySelector<HTMLElement>('[data-active="true"]');
    el?.scrollIntoView({ block: "nearest" });
  }, [activeIdx, trigger]);

  const matches: SkillSummary[] = trigger ? rankSkills(skills, trigger.query) : [];
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
        <div className="chat-input-shell" style={{ position: "relative" }}>
          {popupOpen && (
            <div className="autocomplete-popup" ref={popupRef}>
              <Command shouldFilter={false} onKeyDown={(e) => e.stopPropagation()}>
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
              requestAnimationFrame(refreshTrigger);
            }}
            onSelect={refreshTrigger}
            onClick={refreshTrigger}
            onBlur={() => {
              setTimeout(() => setTrigger(null), 100);
            }}
            placeholder="Type a message, or @ to pick a skill"
            rows={2}
            disabled={disabled}
            onKeyDown={(e) => {
              if (popupOpen && matches.length > 0) {
                if (e.key === "ArrowDown") {
                  e.preventDefault();
                  setActiveIdx((i) => Math.min(i + 1, matches.length - 1));
                  return;
                }
                if (e.key === "ArrowUp") {
                  e.preventDefault();
                  setActiveIdx((i) => Math.max(i - 1, 0));
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
