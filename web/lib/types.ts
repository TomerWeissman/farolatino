// Shapes mirroring api/schemas.py + api/routes/chat.py SSE events.

export type SkillSummary = {
  slug: string;
  name: string;
  description: string;
};

export type ToolUseEvent = {
  kind: "tool_use";
  name: string;
  label: string;
  input: Record<string, unknown>;
};

export type ThinkingEvent = { kind: "thinking"; delta: string };
export type TextEvent = { kind: "text"; delta: string };

export type ResultEvent = {
  kind: "result";
  run_id: string;
  status: "ok" | "error" | "no_text";
  duration_s: number;
  cost_usd: number | null;
  tool_calls: string[];
  thinking_block_count: number;
  // claude --print's session_id from the init event. The frontend stashes
  // it on the conversation so the next turn can pass it as
  // resume_session_id and the model has prior context (otherwise "yes"
  // / "go ahead" follow-ups land in a brand-new session).
  session_id: string | null;
};

export type ErrorEvent = { kind: "error"; message: string };

export type ChatEvent =
  | ToolUseEvent
  | ThinkingEvent
  | TextEvent
  | ResultEvent
  | ErrorEvent;

// What we keep in client state per chat turn.
export type Turn = {
  role: "user" | "assistant";
  content: string;
  thinking?: string[]; // assistant only; concatenated thinking blocks
  toolCalls?: { name: string; label: string }[]; // assistant only
  result?: Pick<ResultEvent, "run_id" | "duration_s" | "cost_usd" | "status">;
};
