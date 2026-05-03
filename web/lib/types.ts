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
