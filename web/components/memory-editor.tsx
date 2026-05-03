"use client";

import { useCallback, useEffect, useState } from "react";
import { Save, Brain } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";

const API = "/api";

type RunSummary = {
  run_id: string;
  started_at: string;
  prompt: string;
  status: string;
  duration_s: number;
  tool_calls: string[];
  cost_usd: number | null;
  summary: string;
};

type RunDetail = RunSummary & {
  thinking_blocks: string[];
  response_text: string;
};

export function MemoryEditor() {
  return (
    <div className="page-shell">
      <header style={{ marginBottom: 32 }}>
        <h1 className="page-title">Memory</h1>
        <p className="page-subtitle">
          Edit the FaroAI persona that&apos;s loaded into every chat, and browse the
          reasoning history of past runs.
        </p>
      </header>

      <PersonaSection />
      <ReasoningHistorySection />
    </div>
  );
}

// ─── FAROAI.md editor ──────────────────────────────────────────────────────
function PersonaSection() {
  const [text, setText] = useState("");
  const [original, setOriginal] = useState("");
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);
  const dirty = text !== original;

  const load = useCallback(async () => {
    const r = await fetch(`${API}/persona`, { cache: "no-store" });
    if (!r.ok) return;
    const d: { content: string } = await r.json();
    setText(d.content);
    setOriginal(d.content);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function save() {
    setSaving(true);
    setStatus(null);
    try {
      const r = await fetch(`${API}/persona`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: text }),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({ detail: r.statusText }));
        throw new Error(err.detail || "save failed");
      }
      setOriginal(text);
      setStatus({ kind: "ok", msg: "Saved. Takes effect on the next chat message." });
    } catch (e) {
      setStatus({ kind: "err", msg: e instanceof Error ? e.message : "save failed" });
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="memory-section">
      <h2 className="memory-section-title">FaroAI persona</h2>
      <p className="memory-section-hint">
        <code>FAROAI.md</code> at the project root. Loaded into every chat as the system prompt.
      </p>
      <textarea
        className="skills-editor-textarea"
        value={text}
        onChange={(e) => setText(e.target.value)}
        spellCheck={false}
        rows={24}
      />
      <div className="skills-editor-actions">
        <button type="button" className="btn btn-primary" disabled={!dirty || saving} onClick={save}>
          <Save size={14} /> {saving ? "Saving…" : "Save"}
        </button>
        {status && (
          <span className={cn("skills-editor-status", status.kind === "err" && "skills-editor-status-err")}>
            {status.msg}
          </span>
        )}
      </div>
    </section>
  );
}

// ─── Recent reasoning ─────────────────────────────────────────────────────
function ReasoningHistorySection() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const r = await fetch(`${API}/runs?limit=20`, { cache: "no-store" });
        if (r.ok) setRuns(await r.json());
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <section className="memory-section memory-history">
      <h2 className="memory-section-title">Recent reasoning</h2>
      <p className="memory-section-hint">
        How FaroAI thought through past chats. Click a run to expand its
        reasoning blocks (visible only when extended thinking was on).
      </p>
      {loading && <div className="page-empty">Loading…</div>}
      {!loading && runs.length === 0 && (
        <div className="page-empty">No runs yet. Send a chat from the FaroAI page first.</div>
      )}
      <div className="memory-runs">
        {runs.map((r) => (
          <RunCard key={r.run_id} run={r} />
        ))}
      </div>
    </section>
  );
}

function RunCard({ run }: { run: RunSummary }) {
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState<RunDetail | null>(null);

  async function expand(o: boolean) {
    setOpen(o);
    if (o && !detail) {
      const r = await fetch(`${API}/runs/${run.run_id}`, { cache: "no-store" });
      if (r.ok) setDetail(await r.json());
    }
  }

  const statusIcon = run.status === "ok" ? "✓" : run.status === "error" ? "✗" : "⚠";
  const ts = run.started_at.split("T")[1]?.slice(0, 8) ?? run.started_at;

  return (
    <Collapsible open={open} onOpenChange={expand} className="memory-run">
      <CollapsibleTrigger className="memory-run-trigger">
        <span className="memory-run-icon">{statusIcon}</span>
        <span className="memory-run-time">{ts}</span>
        <span className="memory-run-prompt">{run.prompt}</span>
        <span className="memory-run-meta">
          {run.duration_s.toFixed(1)}s · {run.tool_calls.length} tools
          {run.cost_usd != null && ` · $${run.cost_usd.toFixed(3)}`}
        </span>
      </CollapsibleTrigger>
      <CollapsibleContent className="memory-run-content">
        {!detail && <div className="page-empty">Loading details…</div>}
        {detail && (
          <>
            {detail.thinking_blocks?.length ? (
              <div>
                <div className="memory-run-section-label">
                  <Brain size={12} /> Reasoning ({detail.thinking_blocks.length} block{detail.thinking_blocks.length === 1 ? "" : "s"})
                </div>
                <div className="reasoning-panel">
                  {detail.thinking_blocks.map((b, i) => (
                    <div key={i}>
                      {i > 0 && <hr className="reasoning-sep" />}
                      <div style={{ whiteSpace: "pre-wrap" }}>{b}</div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="page-empty">No reasoning recorded — extended thinking was off for this run.</div>
            )}
            {detail.response_text && (
              <details className="memory-run-response">
                <summary>Response ({detail.response_text.length.toLocaleString()} chars)</summary>
                <pre className="memory-run-response-pre">{detail.response_text}</pre>
              </details>
            )}
          </>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}
