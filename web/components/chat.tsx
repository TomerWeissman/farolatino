"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { fetchSkills, streamChat } from "@/lib/api";
import type { ChatEvent, SkillSummary, Turn } from "@/lib/types";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";

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
    }
  | { kind: "error"; message: string };

export function Chat() {
  const [history, setHistory] = useState<Turn[]>([]);
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [draft, setDraft] = useState("");
  const [live, setLive] = useState<LiveState>({ kind: "idle" });
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // Load skills once for the picker. Best-effort — we don't block the UI.
  useEffect(() => {
    fetchSkills().then(setSkills).catch(() => {});
  }, []);

  // Auto-scroll to bottom whenever history grows or the stream ticks.
  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [history.length, live]);

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || live.kind === "streaming") return;
    setHistory((h) => [...h, { role: "user", content: trimmed }]);
    setDraft("");
    setLive({ kind: "streaming", text: "", thinking: [], toolStatus: null, tools: [] });

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

  function applyEvent(ev: ChatEvent) {
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
        case "text":
          return { ...s, text: s.text + ev.delta, toolStatus: null };
        case "result":
          // Commit the in-flight turn to history; reset live to idle.
          // setLive runs in its own setter call to avoid stacking
          // inside this dispatch.
          finalizeTurn(s, ev);
          return { kind: "idle" };
        case "error":
          return s; // handled below via setLive("error")
      }
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
}: {
  text: string;
  thinking: string[];
  toolStatus: string | null;
}) {
  return (
    <div className="chat-assistant">
      {thinking.length > 0 && <ReasoningPanel blocks={thinking} />}
      {text ? (
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
      ) : (
        <div className="chat-status">
          <span className="dot" />
          {toolStatus ?? "Thinking…"}
        </div>
      )}
      {text && toolStatus && (
        <div className="chat-status">
          <span className="dot" />
          {toolStatus}
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
        <div className="chat-input-shell">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Type a message, or pick a skill above"
            rows={2}
            disabled={disabled}
            onKeyDown={(e) => {
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
