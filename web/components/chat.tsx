"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { AlertCircle, ArrowRight, Globe } from "lucide-react";

import { fetchSkills } from "@/lib/api";
import { useT } from "@/lib/i18n/context";
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

// Onboarding redirect + reminder banner state. We pull the keys
// status on mount: if no LLM key AND the user hasn't explicitly
// skipped the wizard, push them to /onboarding. If they skipped or
// have keys missing for non-blocking services (Chartmetric), show a
// soft reminder above the chat.
type OnboardingState = {
  needs_onboarding: boolean;
  has_llm_key: boolean;
  has_chartmetric: boolean;
};

const SKIP_KEY = "faroai-onboarding-skipped";

function useOnboardingGate(): OnboardingState | null {
  const router = useRouter();
  const [state, setState] = useState<OnboardingState | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await fetch("/api/onboarding/status", { cache: "no-store" });
        if (!r.ok) return;
        const s: OnboardingState = await r.json();
        if (cancelled) return;
        setState(s);
        // Redirect to wizard ONLY if:
        //   - no LLM key (chat literally can't work), AND
        //   - user hasn't explicitly skipped (in which case we
        //     respect their choice and just show the reminder banner).
        if (s.needs_onboarding && !localStorage.getItem(SKIP_KEY)) {
          router.push("/onboarding");
        }
      } catch {
        // Backend down — don't redirect, just let the chat fail
        // with the existing structured error banner.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [router]);

  return state;
}


export function Chat() {
  const t = useT();
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [draft, setDraft] = useState("");
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [historyTick, setHistoryTick] = useState(0); // bumps when conversation turns change
  const scrollRef = useRef<HTMLDivElement | null>(null);
  // Tracks whether the user is currently scrolled to the bottom of
  // the conversation. We only auto-scroll on stream updates when this
  // is true — otherwise long replies yank the page out from under
  // a user who's reading something earlier in the thread.
  const stickToBottomRef = useRef(true);
  const onboarding = useOnboardingGate();

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

  // Window scroll listener — flips stickToBottomRef whenever the user
  // moves away from the bottom or scrolls back. The chat scroll
  // container is the document itself (chat-shell has no overflow rule),
  // so we measure window vs. document height. 64px threshold means
  // "near the bottom" still counts as pinned, since smooth-scroll can
  // leave a tiny gap mid-animation.
  useEffect(() => {
    const update = () => {
      const distanceFromBottom =
        document.documentElement.scrollHeight -
        (window.scrollY + window.innerHeight);
      stickToBottomRef.current = distanceFromBottom < 64;
    };
    update();
    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    return () => {
      window.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
    };
  }, []);

  // Auto-scroll on new history entries or stream tick — but only when
  // the user was already at the bottom. Otherwise we'd hijack their
  // reading position every time a thinking-delta arrives.
  useEffect(() => {
    if (!stickToBottomRef.current) return;
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
    // Sending a new message is always an explicit "show me what comes
    // next" — re-engage stick-to-bottom so the user's own bubble plus
    // the streaming reply scroll into view, even if they were reading
    // earlier in the thread when they hit Send.
    stickToBottomRef.current = true;
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
      {/* Onboarding reminder banners. Only shown when the user has
          explicitly skipped onboarding (or has partial keys) — the
          gate hook would have redirected them to /onboarding
          otherwise. */}
      {onboarding && !onboarding.has_llm_key && (
        <OnboardingReminderBanner
          tone="error"
          title={t("chat.onboarding.no_llm_title")}
          message={t("chat.onboarding.no_llm_message")}
          ctaLabel={t("chat.onboarding.no_llm_cta")}
          ctaHref="/onboarding"
        />
      )}
      {onboarding && onboarding.has_llm_key && !onboarding.has_chartmetric && (
        <OnboardingReminderBanner
          tone="warn"
          title={t("chat.onboarding.no_chartmetric_title")}
          message={t("chat.onboarding.no_chartmetric_message")}
          ctaLabel={t("chat.onboarding.no_chartmetric_cta")}
          ctaHref="/connections"
        />
      )}

      {history.length === 0 && !isStreaming && !isError ? (
        <div>
          <div className="empty-greet">{t("chat.empty.greeting")}</div>
          <div className="empty-hint">
            {t("chat.empty.hint_prefix")} <code>@</code> {t("chat.empty.hint_suffix")}
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
          {isError && (snapshot?.errorDetails || snapshot?.errorMessage) && (
            <ErrorBanner
              error={
                snapshot.errorDetails ?? { message: snapshot.errorMessage ?? "Unknown error" }
              }
            />
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

function OnboardingReminderBanner({
  tone,
  title,
  message,
  ctaLabel,
  ctaHref,
}: {
  tone: "error" | "warn";
  title: string;
  message: string;
  ctaLabel: string;
  ctaHref: string;
}) {
  const palette = tone === "error"
    ? { bg: "#fef2f2", border: "#fecaca", title: "#7f1d1d", body: "#991b1b" }
    : { bg: "#fffbeb", border: "#fcd34d", title: "#78350f", body: "#92400e" };
  return (
    <div
      style={{
        background: palette.bg,
        border: `1px solid ${palette.border}`,
        borderRadius: 10,
        padding: "12px 16px",
        marginBottom: 16,
        display: "flex",
        alignItems: "center",
        gap: 12,
        flexWrap: "wrap",
      }}
    >
      <AlertCircle size={18} color={palette.title} />
      <div style={{ flex: 1, minWidth: 200 }}>
        <div style={{ fontWeight: 600, color: palette.title, fontSize: 14 }}>{title}</div>
        <div style={{ color: palette.body, fontSize: 13, marginTop: 2 }}>{message}</div>
      </div>
      <a
        href={ctaHref}
        style={{
          color: palette.title,
          fontWeight: 500,
          textDecoration: "underline",
          fontSize: 13,
          display: "inline-flex",
          alignItems: "center",
          gap: 4,
          whiteSpace: "nowrap",
        }}
      >
        {ctaLabel} <ArrowRight size={13} />
      </a>
    </div>
  );
}


function AssistantMessage({ turn }: { turn: Turn }) {
  return (
    <div className="chat-assistant">
      {turn.thinking && turn.thinking.length > 0 && (
        <ReasoningPanel blocks={turn.thinking} />
      )}
      {/* Two pill modes:
          - dashboard "Continue in chat" (pill.inline=false): content is
            the full dossier markdown (LLM context); UI renders only
            the pill.
          - LLM-initiated evaluate_artist (pill.inline=true): content
            is the LLM's brief intro + web "Recent News"; UI renders
            pill AND content. */}
      {turn.evaluatePill && <EvaluatePillCard pill={turn.evaluatePill} />}
      {turn.content && (!turn.evaluatePill || turn.evaluatePill.inline) ? (
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={MARKDOWN_COMPONENTS}>
          {turn.content}
        </ReactMarkdown>
      ) : null}
      {turn.error && <ErrorBanner error={turn.error} />}
    </div>
  );
}


// Custom Markdown component overrides — used for both completed and
// live-streaming assistant turns.
//
// v0.5.2: detect persona-style source tags ([Web: domain.com](url),
// [Chartmetric] / [Spotify] / [YouTube] / [FaroLatino]) and render
// them as styled chip pills instead of plain links. Web-source chips
// open the URL in a new browser tab; internal-source chips are static
// (no link target — they're just "where this fact came from").
const MARKDOWN_COMPONENTS = {
  a: ({ href, children, ...rest }: { href?: string; children?: React.ReactNode }) => {
    const text = childrenToText(children);
    // [Web: domain.com](url) → clickable pill chip with a globe icon.
    const webMatch = text.match(/^\s*Web:\s*(.+?)\s*$/i);
    if (webMatch && href) {
      return (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="chat-source-chip chat-source-chip-web"
          title={href}
          {...rest}
        >
          <Globe className="chat-source-chip-icon" aria-hidden="true" />
          <span>{webMatch[1]}</span>
        </a>
      );
    }
    // Fallback: plain link, default styling.
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" {...rest}>
        {children}
      </a>
    );
  },
};

// Persona-style bracket tags like [Chartmetric] aren't markdown links
// (no URL), so ReactMarkdown leaves them as text inside <p>. We
// post-process text nodes to wrap matching bracket tags in chip spans.
// Implemented via a text-node renderer override so the chip styling
// applies inside any parent node (p, td, li, etc).
const INTERNAL_SOURCE_TAGS = new Set([
  "Chartmetric", "Spotify", "YouTube", "FaroLatino",
]);

// We add a `p` override too so the bracket tags inside paragraph text
// get tokenized. This re-walks the children, splitting strings on the
// bracket pattern and wrapping matches in chip spans.
(MARKDOWN_COMPONENTS as Record<string, unknown>).p = ({ children }: { children?: React.ReactNode }) => (
  <p>{tokenizeSourceTags(children)}</p>
);
(MARKDOWN_COMPONENTS as Record<string, unknown>).li = ({ children }: { children?: React.ReactNode }) => (
  <li>{tokenizeSourceTags(children)}</li>
);
(MARKDOWN_COMPONENTS as Record<string, unknown>).td = ({ children }: { children?: React.ReactNode }) => (
  <td>{tokenizeSourceTags(children)}</td>
);


function tokenizeSourceTags(children: React.ReactNode): React.ReactNode {
  // Recursively walk children, splitting any string text on the
  // [Chartmetric] / [Spotify] / [YouTube] / [FaroLatino] pattern.
  // Non-string children pass through unchanged.
  const tagRe = /\[(Chartmetric|Spotify|YouTube|FaroLatino)\]/g;
  const walk = (node: React.ReactNode): React.ReactNode => {
    if (typeof node === "string") {
      const parts: React.ReactNode[] = [];
      let lastIndex = 0;
      let match: RegExpExecArray | null;
      while ((match = tagRe.exec(node)) !== null) {
        if (match.index > lastIndex) parts.push(node.slice(lastIndex, match.index));
        const tag = match[1];
        if (INTERNAL_SOURCE_TAGS.has(tag)) {
          parts.push(
            <span
              key={`${tag}-${match.index}`}
              className={`chat-source-chip chat-source-chip-internal chat-source-chip-${tag.toLowerCase()}`}
            >
              {tag}
            </span>
          );
        } else {
          parts.push(match[0]);
        }
        lastIndex = tagRe.lastIndex;
      }
      if (lastIndex < node.length) parts.push(node.slice(lastIndex));
      return parts.length > 0 ? parts : node;
    }
    if (Array.isArray(node)) return node.map((c, i) => <span key={i}>{walk(c)}</span>);
    return node;
  };
  return walk(children);
}


function childrenToText(children: React.ReactNode): string {
  if (typeof children === "string") return children;
  if (Array.isArray(children)) return children.map(childrenToText).join("");
  if (children && typeof children === "object" && "props" in children) {
    return childrenToText((children as { props?: { children?: React.ReactNode } }).props?.children);
  }
  return "";
}

function EvaluatePillCard({ pill }: { pill: NonNullable<Turn["evaluatePill"]> }) {
  const t = useT();
  const router = useRouter();
  const initials = pill.artist
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((s) => s[0]?.toUpperCase() ?? "")
    .join("") || "?";
  return (
    <button
      type="button"
      className="chat-eval-pill"
      onClick={() => {
        // Send back to /evaluate with both name + cm_id so it skips
        // the search step and re-renders straight from cache.
        const params = new URLSearchParams({ artist: pill.artist });
        if (pill.cm_id) params.set("cm_id", String(pill.cm_id));
        router.push(`/evaluate?${params.toString()}`);
      }}
      title={t("chat.eval_pill.open_dossier")}
    >
      {pill.image ? (
        <img src={pill.image} alt={pill.artist} className="chat-eval-pill-photo" />
      ) : (
        <div className="chat-eval-pill-photo chat-eval-pill-photo-fallback">{initials}</div>
      )}
      <div className="chat-eval-pill-body">
        <div className="chat-eval-pill-name">{pill.artist}</div>
        <div className="chat-eval-pill-meta">
          {pill.score != null && <span className="chat-eval-pill-score">{Math.round(pill.score)}/100</span>}
          {pill.tier && <span className="chat-eval-pill-tier">{pill.tier}</span>}
          <span className="chat-eval-pill-link">{t("chat.eval_pill.open_dossier")} <ArrowRight size={12} /></span>
        </div>
      </div>
    </button>
  );
}

// Inline structured-error banner. Always shows the title; renders the
// hint + a "Fix it" link when the backend supplied them; the raw
// provider message goes into a collapsible "Show details" so power
// users can copy the original payload without it dominating the view.
function ErrorBanner({
  error,
}: {
  error: { message: string; hint?: string; fix_url?: string; raw?: string };
}) {
  const t = useT();
  const [open, setOpen] = useState(false);
  return (
    <div
      className="chat-error-banner"
      style={{
        marginTop: 8,
        marginBottom: 8,
        padding: "10px 12px",
        background: "#fef2f2",
        border: "1px solid #fecaca",
        borderRadius: 8,
        color: "#7f1d1d",
        fontSize: 14,
        lineHeight: 1.4,
      }}
    >
      <div style={{ fontWeight: 600 }}>⚠️ {error.message}</div>
      {error.hint && (
        <div style={{ marginTop: 4, color: "#991b1b" }}>{error.hint}</div>
      )}
      <div style={{ marginTop: 8, display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        {error.fix_url && (
          <a
            href={error.fix_url}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              textDecoration: "underline",
              color: "#991b1b",
              fontWeight: 500,
            }}
          >
            {t("chat.error.open_fix")}
          </a>
        )}
        <a
          href="/connections"
          style={{ textDecoration: "underline", color: "#991b1b", fontWeight: 500 }}
        >
          {t("chat.error.open_connections")}
        </a>
        {error.raw && (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            style={{
              background: "transparent",
              border: "none",
              color: "#991b1b",
              cursor: "pointer",
              textDecoration: "underline",
              padding: 0,
              font: "inherit",
            }}
          >
            {open ? t("chat.error.hide_details") : t("chat.error.show_details")}
          </button>
        )}
      </div>
      {open && error.raw && (
        <pre
          style={{
            marginTop: 8,
            padding: 8,
            background: "#fff",
            border: "1px solid #fecaca",
            borderRadius: 6,
            fontSize: 12,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            maxHeight: 240,
            overflow: "auto",
          }}
        >
          {error.raw}
        </pre>
      )}
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
  const t = useT();
  const { text, thinking, toolStatus, evaluatePill } = snapshot;
  const showTimer = elapsedSec >= 3;
  const baseLabel = toolStatus ?? t("chat.thinking");
  const statusLabel = showTimer ? `${baseLabel} (${elapsedSec}s)` : baseLabel;
  return (
    <div className="chat-assistant">
      {thinking.length > 0 && <ReasoningPanel blocks={thinking} />}
      {evaluatePill && <EvaluatePillCard pill={evaluatePill} />}
      {text ? (
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={MARKDOWN_COMPONENTS}>{text}</ReactMarkdown>
      ) : (
        <ChatStatusPill label={statusLabel} toolStatus={toolStatus} />
      )}
      {text && toolStatus && (
        <ChatStatusPill label={statusLabel} toolStatus={toolStatus} />
      )}
    </div>
  );
}


// v0.5.2: visual signifier for what the assistant is currently doing.
// When the active tool is `web_search` the pill shows a globe icon +
// "Searching the web" label so users see the search happening — same
// pattern as the existing thinking-dot but with a stronger affordance.
function ChatStatusPill({ label, toolStatus }: { label: string; toolStatus: string | null }) {
  const isWebSearch = (toolStatus ?? "").toLowerCase().includes("search")
    && (toolStatus ?? "").toLowerCase().includes("web");
  if (isWebSearch) {
    return (
      <div className="chat-status chat-status-web">
        <Globe className="chat-status-icon" aria-hidden="true" />
        <span>{label}</span>
      </div>
    );
  }
  return (
    <div className="chat-status">
      <span className="dot" />
      {label}
    </div>
  );
}

function ReasoningPanel({ blocks }: { blocks: string[] }) {
  const t = useT();
  const labelKey = blocks.length === 1 ? "chat.reasoning.label_one" : "chat.reasoning.label_many";
  return (
    <Collapsible className="my-2">
      <CollapsibleTrigger className="text-xs text-[color:var(--text-faint)] hover:text-[color:var(--text-muted)] cursor-pointer">
        💭 {t(labelKey, { n: blocks.length })}
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
  const t = useT();
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
                    <CommandEmpty>{t("chat.autocomplete.no_skills")}</CommandEmpty>
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
            placeholder={t("chat.input.placeholder")}
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
