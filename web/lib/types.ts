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

export type ErrorEvent = {
  kind: "error";
  message: string;
  // Optional structured fields the backend attaches when it can map a
  // provider error to a known shape. Lets the UI render a one-line
  // hint, a "Fix it" link button, and a collapsible raw-details block.
  hint?: string;
  fix_url?: string;
  raw?: string;
};

// What we render on a turn that errored out. Persisted alongside the
// assistant turn in localStorage so the user can scroll back to old
// errors without losing the actionable info.
export type TurnError = {
  message: string;
  hint?: string;
  fix_url?: string;
  raw?: string;
};

// Emitted by the chat backend when the LLM's evaluate_artist tool
// returns successfully — the frontend attaches it to the assistant
// turn so the chat renders a compact pill card instead of the LLM
// pasting the dossier markdown wall.
export type EvaluatePillEvent = {
  kind: "evaluate_pill";
  artist: string;
  cm_id: number;
  image?: string | null;
  tier?: string | null;
  score?: number | null;
};

// Sibling of EvaluatePillEvent for chat-initiated compares — emitted
// when the LLM's compare_artists tool returns both sides resolved.
export type ComparePillEvent = {
  kind: "compare_pill";
  artist_a: string;
  artist_b: string;
  cm_id_a: number;
  cm_id_b: number;
  image_a?: string | null;
  image_b?: string | null;
  tier_a?: string | null;
  tier_b?: string | null;
  score_a?: number | null;
  score_b?: number | null;
};

export type ChatEvent =
  | ToolUseEvent
  | ThinkingEvent
  | TextEvent
  | ResultEvent
  | ErrorEvent
  | EvaluatePillEvent
  | ComparePillEvent;

// Compact "I evaluated X" chip rendered in the chat instead of a
// big Markdown wall. Click → goes back to /evaluate?artist=X. The
// dossier is still in the turn's `content` field so the LLM has it
// as context — the UI just renders the pill on top of the markdown.
//
// `inline=true` is the v0.5.2 chat-initiated mode: the LLM emits a
// short reply (intro + web "Recent News") AND the backend emits a
// pill event, so the UI renders the pill ALONGSIDE the brief content.
// Default (unset / false) is the dashboard "Continue in chat" mode:
// the dossier markdown lives in content for LLM context but the UI
// hides it and shows only the pill.
export type EvaluatePill = {
  artist: string;
  cm_id: number;
  image?: string;
  tier?: string;
  score?: number;
  inline?: boolean;
};

// Compact two-photo "I compared X vs Y" chip. Same inline semantics as
// EvaluatePill — when the LLM emits it the chat renders pill + the
// LLM's brief follow-up content. Click → /compare?primary=...&secondary=...
export type ComparePill = {
  artist_a: string;
  artist_b: string;
  cm_id_a: number;
  cm_id_b: number;
  image_a?: string;
  image_b?: string;
  tier_a?: string;
  tier_b?: string;
  score_a?: number;
  score_b?: number;
  inline?: boolean;
};

// What we keep in client state per chat turn.
export type Turn = {
  role: "user" | "assistant";
  content: string;
  thinking?: string[]; // assistant only; concatenated thinking blocks
  toolCalls?: { name: string; label: string }[]; // assistant only
  result?: Pick<ResultEvent, "run_id" | "duration_s" | "cost_usd" | "status">;
  error?: TurnError; // assistant only; populated when the turn errored
  // When set, the chat renders a compact pill instead of `content`.
  // `content` still holds the full dossier markdown so the LLM has
  // context for follow-up questions via Phase 1's history replay.
  evaluatePill?: EvaluatePill;
  // Sibling for chat-initiated compares — same inline semantics.
  comparePill?: ComparePill;
};

// ─── /api/evaluate response types ──────────────────────────────────────
//
// Mirrors the dossier dict produced by mcp_server/tools/dossier_generator.py.
// All sub-fields are optional because Chartmetric coverage varies per
// artist — a brand-new artist might have no milestones; an instrumental
// artist might have no engagement data; etc. The dashboard handles each
// section's "empty" state gracefully.

export type Dossier = {
  identity: {
    name: string;
    genres?: string[];
    career_stage?: string;
    career_trend?: string;
    label?: string | null;
    distributor?: string | null;
    image?: string | null;
    urls?: Record<string, string>;
  };
  metrics: {
    spotify?: {
      monthly_listeners?: number;
      monthly_listeners_change?: string;
      followers?: number;
      popularity?: number;
    };
    youtube?: { subscribers?: number; views?: number };
    instagram?: { followers?: number; engagement_rate?: string };
    tiktok?: { followers?: number; likes?: number | null };
    other?: {
      shazam_count?: number;
      deezer_fans?: number;
      soundcloud_followers?: number;
    };
    cpp_score?: number;
  };
  prospect_score: {
    overall: number;
    tier: string;
    confidence: number;
    data_completeness?: number;
    profile_used?: string;
    dimensions: Record<string, {
      score: number;
      confidence?: number;
      rationale?: string;
      weight?: number;
      weighted_contribution?: number;
    }>;
  };
  geographic_profile?: {
    top_markets?: Array<{
      country?: string;
      country_code?: string;
      listeners?: number;
      growth?: string;
    }>;
  };
  revenue_projection?: {
    annual_projected?: number;
    monthly_total?: number;
    monthly_revenue_by_platform?: Record<string, number>;
    note?: string;
  };
  career_trajectory?: {
    stage?: string;
    trend?: string;
    momentum_score?: number;
    milestones?: Array<{ text: string; date?: string; platform?: string }>;
  };
  catalog?: {
    releases_6m?: number;
    releases_12m?: number;
    total_tracks?: number;
    latest_tracks?: Array<{ name: string; release_date?: string; isrc?: string }>;
    editorial_playlists?: number;
    total_playlists?: number;
    // v0.5.0 — Spotify cadence + top-tracks enrichment
    latest_release_date?: string | null;
    days_since_latest_release?: number | null;
    release_cadence_days?: number | null;
    cadence_trend?: "accelerating" | "steady" | "decelerating" | null;
    top_tracks?: Array<{
      name: string;
      release_date?: string;
      popularity?: number;
      spotify_id?: string;
    }>;
  };
  // v0.5.0 — averaged Spotify audio features (top tracks)
  sound_profile?: {
    danceability?: number;
    energy?: number;
    tempo?: number;
    sample_size?: number;
  };
  // v0.5.0 — Spotify + YouTube cadence + YT recent-video performance
  content_velocity?: {
    spotify?: {
      latest_date?: string | null;
      days_since_latest?: number | null;
      cadence_days?: number | null;
      trend?: "accelerating" | "steady" | "decelerating" | null;
    } | null;
    youtube?: {
      latest_date?: string | null;
      days_since_latest?: number | null;
      cadence_days?: number | null;
      trend?: "accelerating" | "steady" | "decelerating" | null;
      avg_views_recent_3?: number | null;
      avg_like_ratio_pct?: number | null;
      // v0.5.2 — comments-per-view (sharper engagement signal than likes)
      avg_comments_per_view_pct?: number | null;
      latest_videos?: Array<{
        title: string;
        published_at: string;
        view_count: number;
        like_count: number;
      }>;
      // v0.5.2 — top videos by lifetime view count
      top_videos?: Array<{
        id: string;
        title: string;
        published_at: string;
        view_count: number;
        like_count: number;
        comment_count: number;
        like_ratio: number | null;
        thumbnail_url: string | null;
        url: string | null;
      }>;
    } | null;
  };
  risk_signals?: Record<string, string>;
  competitive_context?: {
    similar_artists?: Array<{
      name: string;
      // image_url surfaced to the dashboard so the Similar artists
      // card renders a profile photo (initials fallback when missing).
      image_url?: string | null;
      country_code?: string | null;
      sp_monthly_listeners?: number | null;
      career_stage?: string;
      signed?: boolean | null;
      momentum?: string;
    }>;
  };
  actionable?: {
    social_links?: Record<string, string>;
    tier?: string;
  };
  // v0.5.2 — verified signing status (Chartmetric flag + record_label
  // + recent-album labels cross-check). Drives the Hero badge.
  signing?: {
    chartmetric_flag?: boolean | null;
    verified_status?: "signed_major" | "signed_indie" | "self_released" | "unknown";
    confidence?: "high" | "medium" | "low";
    evidence?: string[];
    discrepancy?: boolean;
    label_display?: string;
  };
};

export type DisambigCandidate = {
  cm_id: number;
  name: string;
  country_code?: string;
  code2?: string;  // Chartmetric uses this for country in some endpoints
  sp_followers?: number;
  sp_monthly_listeners?: number;
  image_url?: string;  // small profile photo from Chartmetric search
  genres?: string[] | null;
};

export type EvaluateResponse =
  | {
      dossier: Dossier;
      alert?: { tier: string };
      cm_id: number;
      rendered_markdown: string;
      error?: undefined;
      needs_disambiguation?: undefined;
    }
  | {
      needs_disambiguation: DisambigCandidate[];
      query: string;
      dossier?: undefined;
      error?: undefined;
    }
  | {
      error: string;
      dossier?: undefined;
      needs_disambiguation?: undefined;
    };

// One row in the "Recently evaluated" list on the empty state.
// Persisted to localStorage as `faroai-recent-evals`.
export type RecentEval = {
  name: string;
  cm_id: number;
  evaluated_at: number; // epoch ms
};

// One row in the "Recent comparisons" list on /compare's empty state.
// Persisted to localStorage as `faroai-recent-compares` (v0.5.2).
// Stores both artist names + cm_ids so a click pre-fills the inputs
// AND fast-paths the dispatch via cm_id (cache hit, no search step).
export type RecentCompare = {
  artist_a: string;
  cm_id_a: number;
  artist_b: string;
  cm_id_b: number;
  compared_at: number; // epoch ms
};
