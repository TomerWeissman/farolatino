"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { CheckCircle2, AlertTriangle, XCircle, RefreshCw, ExternalLink, Loader2, ChevronDown, ChevronUp, Save, Eye, EyeOff, Download } from "lucide-react";
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

type EnvVar = {
  name: string;
  populated: boolean;
  preview: string | null;
  length: number;
};

type EnvBundle = { vars: EnvVar[] };

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
  const [envVars, setEnvVars] = useState<Record<string, EnvVar>>({});
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      // Fire both reads in parallel.
      const [connRes, envRes] = await Promise.all([
        fetch(`${API}/connections?t=${Date.now()}`, { cache: "no-store" }),
        fetch(`${API}/env?t=${Date.now()}`, { cache: "no-store" }),
      ]);
      if (!connRes.ok) throw new Error(`/api/connections ${connRes.status}`);
      if (!envRes.ok) throw new Error(`/api/env ${envRes.status}`);
      const conns: Connection[] = await connRes.json();
      const envs: EnvBundle = await envRes.json();
      setItems(conns);
      setEnvVars(Object.fromEntries(envs.vars.map((v) => [v.name, v])));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "load failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const onSavedEnv = useCallback(async (newVars: EnvVar[]) => {
    // Update local env preview, then re-ping connections so the row's
    // status reflects the new credentials.
    setEnvVars((prev) => {
      const next = { ...prev };
      for (const v of newVars) next[v.name] = v;
      return next;
    });
    await reload();
  }, [reload]);

  return (
    <div className="page-shell">
      <header className="connections-header">
        <div>
          <h1 className="page-title">Connections</h1>
          <p className="page-subtitle">
            External APIs the dashboard uses. Click a row to view or edit its credentials.
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
            <ConnectionRow
              key={c.name}
              c={c}
              envVars={envVars}
              expanded={expanded === c.name}
              onToggle={() => setExpanded((e) => (e === c.name ? null : c.name))}
              onSavedEnv={onSavedEnv}
            />
          ))}
        </div>
      )}

      {!items && !err && <div className="page-empty">Pinging providers…</div>}

      <p className="page-subtitle" style={{ marginTop: 32, fontSize: 12 }}>
        Edits are written to the project&apos;s <code>.env</code> file. Status is
        cached server-side for 60s; saving credentials clears the cache so the
        next ping reflects your changes.
      </p>

      <UpdateSection />
    </div>
  );
}

function ConnectionRow({
  c,
  envVars,
  expanded,
  onToggle,
  onSavedEnv,
}: {
  c: Connection;
  envVars: Record<string, EnvVar>;
  expanded: boolean;
  onToggle: () => void;
  onSavedEnv: (vars: EnvVar[]) => void;
}) {
  const meta = STATUS_META[c.status] ?? STATUS_META.unknown;
  const hasEditable = c.env_vars.length > 0;
  return (
    <div className={cn("connection-row", `connection-row-${meta.tone}`)}>
      <button
        type="button"
        className="connection-row-head connection-row-head-button"
        onClick={onToggle}
        disabled={!hasEditable}
      >
        <div className="connection-row-name">{c.name}</div>
        <div className={cn("connection-row-status", `connection-status-${meta.tone}`)}>
          {meta.icon}
          {meta.label}
        </div>
        {hasEditable && (
          <span className="connection-row-chevron">
            {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </span>
        )}
      </button>
      {c.detail && <div className="connection-row-detail">{c.detail}</div>}
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
      {expanded && hasEditable && (
        <EnvEditor
          keys={c.env_vars}
          envVars={envVars}
          onSaved={onSavedEnv}
        />
      )}
    </div>
  );
}

// ─── Inline env editor ──────────────────────────────────────────────────

function EnvEditor({
  keys,
  envVars,
  onSaved,
}: {
  keys: string[];
  envVars: Record<string, EnvVar>;
  onSaved: (vars: EnvVar[]) => void;
}) {
  // Drafts: only fields the user has actually edited. Empty string = no
  // edit (we only PUT keys present in this map).
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [reveal, setReveal] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);

  const dirty = useMemo(() => Object.keys(drafts).length > 0, [drafts]);

  async function save() {
    if (!dirty) return;
    setSaving(true);
    setStatus(null);
    try {
      const r = await fetch(`${API}/env`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ updates: drafts }),
      });
      if (!r.ok) {
        const e = await r.json().catch(() => ({ detail: r.statusText }));
        throw new Error(e.detail || "save failed");
      }
      const updated: EnvBundle = await r.json();
      setDrafts({});
      setStatus({ kind: "ok", msg: "Saved. Rechecking…" });
      onSaved(updated.vars);
    } catch (e) {
      setStatus({ kind: "err", msg: e instanceof Error ? e.message : "save failed" });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="env-editor">
      {keys.map((k) => {
        const v = envVars[k];
        const draft = drafts[k];
        const isDirty = draft !== undefined;
        const showSecret = reveal[k];
        return (
          <label className="env-row" key={k}>
            <div className="env-row-label">
              <code className="env-row-key">{k}</code>
              {v && (
                <span className={cn("env-row-state", v.populated ? "env-row-state-set" : "env-row-state-empty")}>
                  {v.populated ? `set · ${v.length} chars` : "not set"}
                </span>
              )}
            </div>
            <div className="env-row-input">
              <input
                type={showSecret ? "text" : "password"}
                className="dialog-input"
                placeholder={v?.preview ?? "(empty)"}
                value={draft ?? ""}
                onChange={(e) => {
                  const val = e.target.value;
                  setDrafts((d) => {
                    const next = { ...d };
                    if (val === "") delete next[k];
                    else next[k] = val;
                    return next;
                  });
                }}
              />
              <button
                type="button"
                className="env-row-eye"
                onClick={() => setReveal((r) => ({ ...r, [k]: !r[k] }))}
                title={showSecret ? "Hide" : "Show"}
                aria-label={showSecret ? "Hide value" : "Show value"}
              >
                {showSecret ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
              {isDirty && <span className="env-row-dirty">edited</span>}
            </div>
          </label>
        );
      })}
      <div className="skills-editor-actions">
        <button
          type="button"
          className="btn btn-primary"
          disabled={!dirty || saving}
          onClick={save}
        >
          <Save size={14} /> {saving ? "Saving…" : "Save"}
        </button>
        {status && (
          <span className={cn("skills-editor-status", status.kind === "err" && "skills-editor-status-err")}>
            {status.msg}
          </span>
        )}
      </div>
    </div>
  );
}

// ─── Update section ─────────────────────────────────────────────────────
//
// Sits at the bottom of the Connections page. Shows the running version
// + a manual "Check for updates" button. We don't poll automatically —
// per the V2 plan, the FaroLatino team is small enough that you'll just
// notify them when an update is ready and they click here.

type UpdateCheck = {
  current_version: string;
  latest_version: string;
  update_available: boolean;
  can_apply_in_app: boolean;
  download_url: string | null;
  release_notes: string | null;
  error: string | null;
};

function UpdateSection() {
  const [version, setVersion] = useState<string | null>(null);
  const [check, setCheck] = useState<UpdateCheck | null>(null);
  const [busy, setBusy] = useState<"idle" | "checking" | "applying">("idle");
  const [applyMsg, setApplyMsg] = useState<string | null>(null);

  // Pull the running version once on mount.
  useEffect(() => {
    fetch(`${API}/version`, { cache: "no-store" })
      .then((r) => r.ok ? r.json() : null)
      .then((d) => d && setVersion(d.version))
      .catch(() => {});
  }, []);

  async function checkUpdates() {
    setBusy("checking");
    setApplyMsg(null);
    try {
      const r = await fetch(`${API}/updates/check`, { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d: UpdateCheck = await r.json();
      setCheck(d);
    } catch (e) {
      setCheck({
        current_version: version ?? "?",
        latest_version: "?",
        update_available: false,
        can_apply_in_app: false,
        download_url: null,
        release_notes: null,
        error: e instanceof Error ? e.message : "check failed",
      });
    } finally {
      setBusy("idle");
    }
  }

  async function applyUpdate() {
    if (!check?.can_apply_in_app) return;
    if (!confirm(
      `Update from v${check.current_version} to v${check.latest_version}?\n\n` +
      "FaroAI will close + relaunch automatically. Conversations + credentials are preserved."
    )) return;
    setBusy("applying");
    setApplyMsg("Downloading update…");
    try {
      const r = await fetch(`${API}/updates/apply`, { method: "POST" });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "apply failed");
      setApplyMsg(d.message || "Restarting…");
      // The app will exec itself; this UI session won't get a clean
      // close. The user sees the window relaunch with the new version.
    } catch (e) {
      setApplyMsg(`⚠️ ${e instanceof Error ? e.message : "apply failed"}`);
      setBusy("idle");
    }
  }

  return (
    <div style={{ marginTop: 48, paddingTop: 24, borderTop: "1px solid #e5e7eb" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
        <div>
          <div style={{ fontSize: 13, color: "#6b7280" }}>FaroAI version</div>
          <div style={{ fontSize: 16, fontWeight: 500 }}>{version ? `v${version}` : "loading…"}</div>
        </div>
        <button
          type="button"
          className="btn btn-ghost"
          onClick={checkUpdates}
          disabled={busy !== "idle"}
        >
          {busy === "checking" ? <Loader2 size={14} className="spin" /> : <RefreshCw size={14} />}
          {busy === "checking" ? "Checking…" : "Check for updates"}
        </button>
        {check?.update_available && check.can_apply_in_app && (
          <button
            type="button"
            className="btn btn-primary"
            onClick={applyUpdate}
            disabled={busy !== "idle"}
          >
            <Download size={14} /> Update to v{check.latest_version}
          </button>
        )}
      </div>

      {check && !check.error && check.update_available && !check.can_apply_in_app && (
        <p className="page-subtitle" style={{ marginTop: 12, fontSize: 12 }}>
          v{check.latest_version} is available, but this update needs a new
          installer. Download the latest .dmg from the Releases page.
        </p>
      )}
      {check && !check.error && !check.update_available && (
        <p className="page-subtitle" style={{ marginTop: 12, fontSize: 12 }}>
          You&apos;re on the latest version (v{check.current_version}).
        </p>
      )}
      {check?.error && (
        <p className="page-subtitle" style={{ marginTop: 12, fontSize: 12, color: "#7f1d1d" }}>
          ⚠️ {check.error}
        </p>
      )}
      {applyMsg && (
        <p className="page-subtitle" style={{ marginTop: 12, fontSize: 12 }}>
          {applyMsg}
        </p>
      )}
    </div>
  );
}
