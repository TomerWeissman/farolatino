"use client";

import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, AlertTriangle, XCircle, RefreshCw, ExternalLink, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

const API = "/api";

type Status = "ok" | "missing_creds" | "auth_failed" | "quota_required" | "network_error" | "unknown";

type Connection = {
  name: string;
  status: Status;
  detail?: string;
  env_vars: string[];
  docs_url?: string;
};

const STATUS_META: Record<Status, { icon: React.ReactNode; label: string; tone: "ok" | "warn" | "err" }> = {
  ok:              { icon: <CheckCircle2 size={16} />, label: "Connected",        tone: "ok" },
  missing_creds:   { icon: <AlertTriangle size={16} />, label: "Not configured",  tone: "warn" },
  auth_failed:     { icon: <XCircle size={16} />,       label: "Auth failed",      tone: "err" },
  quota_required:  { icon: <AlertTriangle size={16} />, label: "Subscription required", tone: "warn" },
  network_error:   { icon: <XCircle size={16} />,       label: "Network error",    tone: "err" },
  unknown:         { icon: <AlertTriangle size={16} />, label: "Unknown",          tone: "warn" },
};

export function ConnectionsStatus() {
  const [items, setItems] = useState<Connection[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      // Bust the 60s server-side cache by appending a timestamp.
      const r = await fetch(`${API}/connections?t=${Date.now()}`, { cache: "no-store" });
      if (!r.ok) throw new Error(`/api/connections ${r.status}`);
      setItems(await r.json());
    } catch (e) {
      setErr(e instanceof Error ? e.message : "load failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  return (
    <div className="page-shell">
      <header className="connections-header">
        <div>
          <h1 className="page-title">Connections</h1>
          <p className="page-subtitle">
            External APIs the dashboard uses, with live status.
          </p>
        </div>
        <button
          type="button"
          className="btn btn-ghost"
          onClick={reload}
          disabled={loading}
        >
          {loading ? <Loader2 size={14} className="spin" /> : <RefreshCw size={14} />}
          {loading ? "Checking…" : "Recheck"}
        </button>
      </header>

      {err && <div className="dialog-error">⚠️ {err}</div>}

      {items && (
        <div className="connections-list">
          {items.map((c) => (
            <ConnectionRow key={c.name} c={c} />
          ))}
        </div>
      )}

      {!items && !err && <div className="page-empty">Pinging providers…</div>}

      <p className="page-subtitle" style={{ marginTop: 32, fontSize: 12 }}>
        Status is cached server-side for 60s. To update credentials, edit the
        <code> .env </code>
        file at the project root and restart <code>start.command</code>.
      </p>
    </div>
  );
}

function ConnectionRow({ c }: { c: Connection }) {
  const meta = STATUS_META[c.status] ?? STATUS_META.unknown;
  return (
    <div className={cn("connection-row", `connection-row-${meta.tone}`)}>
      <div className="connection-row-head">
        <div className="connection-row-name">{c.name}</div>
        <div className={cn("connection-row-status", `connection-status-${meta.tone}`)}>
          {meta.icon}
          {meta.label}
        </div>
      </div>
      {c.detail && <div className="connection-row-detail">{c.detail}</div>}
      {c.env_vars.length > 0 && c.status !== "ok" && (
        <div className="connection-row-meta">
          Set in <code>.env</code>:&nbsp;
          {c.env_vars.map((v, i) => (
            <span key={v}>
              <code>{v}</code>
              {i < c.env_vars.length - 1 && ", "}
            </span>
          ))}
        </div>
      )}
      {c.docs_url && (
        <a
          className="connection-row-link"
          href={c.docs_url}
          target="_blank"
          rel="noopener noreferrer"
        >
          Docs <ExternalLink size={12} />
        </a>
      )}
    </div>
  );
}
