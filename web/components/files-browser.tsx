"use client";

import { useEffect, useState } from "react";
import { Save, FileText, Database, Lock } from "lucide-react";
import { cn } from "@/lib/utils";
import { useT } from "@/lib/i18n/context";

const API = "/api";

type CalibrationFile = { name: string; size: number; mtime: number; content: string };
type CacheArtistRow = { cm_id: number; name: string | null; country_code: string | null; n_endpoints: number; last_modified: number };
type InternalFile = { name: string; size: number; mtime: number };

type Tab = "calibration" | "cache" | "internal";

export function FilesBrowser() {
  const t = useT();
  const [tab, setTab] = useState<Tab>("calibration");
  return (
    <div className="page-shell">
      <header style={{ marginBottom: 24 }}>
        <h1 className="page-title">{t("files.title")}</h1>
        <p className="page-subtitle">{t("files.subtitle")}</p>
      </header>

      <div className="files-tabs">
        <TabButton active={tab === "calibration"} onClick={() => setTab("calibration")} icon={<FileText size={14} />} label={t("files.tab.calibration")} hint={t("files.tag.editable")} />
        <TabButton active={tab === "cache"}       onClick={() => setTab("cache")}       icon={<Database size={14} />} label={t("files.tab.cached")} hint={t("files.tag.readonly")} />
        <TabButton active={tab === "internal"}    onClick={() => setTab("internal")}    icon={<Lock size={14} />}     label={t("files.tab.internal")} hint={t("files.tag.readonly")} />
      </div>

      {tab === "calibration" && <CalibrationTab />}
      {tab === "cache" && <CacheTab />}
      {tab === "internal" && <InternalTab />}
    </div>
  );
}

function TabButton({
  active, onClick, icon, label, hint,
}: { active: boolean; onClick: () => void; icon: React.ReactNode; label: string; hint: string }) {
  return (
    <button type="button" className={cn("files-tab", active && "files-tab-active")} onClick={onClick}>
      {icon}
      <span>{label}</span>
      <span className="files-tab-hint">{hint}</span>
    </button>
  );
}

// ─── Calibration tab ─────────────────────────────────────────────────────
function CalibrationTab() {
  const t = useT();
  const [files, setFiles] = useState<CalibrationFile[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [editor, setEditor] = useState("");
  const [original, setOriginal] = useState("");
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);

  useEffect(() => {
    (async () => {
      const r = await fetch(`${API}/files/calibration`, { cache: "no-store" });
      if (!r.ok) return;
      const list: CalibrationFile[] = await r.json();
      setFiles(list);
      if (list.length) {
        setSelected(list[0].name);
        setEditor(list[0].content);
        setOriginal(list[0].content);
      }
    })();
  }, []);

  function pick(name: string) {
    const f = files.find((x) => x.name === name);
    if (!f) return;
    setSelected(name);
    setEditor(f.content);
    setOriginal(f.content);
    setStatus(null);
  }

  async function save() {
    if (!selected) return;
    setSaving(true);
    setStatus(null);
    try {
      const r = await fetch(`${API}/files/calibration/${selected}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: editor }),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({ detail: r.statusText }));
        throw new Error(err.detail || "save failed");
      }
      const updated: CalibrationFile = await r.json();
      setFiles((prev) => prev.map((f) => (f.name === updated.name ? updated : f)));
      setOriginal(updated.content);
      setStatus({ kind: "ok", msg: "Saved." });
    } catch (e) {
      setStatus({ kind: "err", msg: e instanceof Error ? e.message : "save failed" });
    } finally {
      setSaving(false);
    }
  }

  const dirty = editor !== original;

  return (
    <div className="files-grid">
      <aside className="files-list">
        {files.map((f) => (
          <button
            key={f.name}
            type="button"
            className={cn("files-list-item", selected === f.name && "files-list-item-active")}
            onClick={() => pick(f.name)}
          >
            <div className="files-list-name">{f.name}</div>
            <div className="files-list-meta">{Math.round(f.size / 1024 * 10) / 10} KB</div>
          </button>
        ))}
      </aside>
      <section className="files-content">
        {selected ? (
          <>
            <textarea
              className="skills-editor-textarea"
              value={editor}
              onChange={(e) => setEditor(e.target.value)}
              spellCheck={false}
              rows={28}
            />
            <div className="skills-editor-actions">
              <button type="button" className="btn btn-primary" disabled={!dirty || saving} onClick={save}>
                <Save size={14} /> {saving ? t("ui.saving") : t("ui.save")}
              </button>
              {status && (
                <span className={cn("skills-editor-status", status.kind === "err" && "skills-editor-status-err")}>
                  {status.msg}
                </span>
              )}
            </div>
          </>
        ) : (
          <div className="page-empty">{t("ui.loading")}</div>
        )}
      </section>
    </div>
  );
}

// ─── Cache tab ───────────────────────────────────────────────────────────
function CacheTab() {
  const t = useT();
  const [rows, setRows] = useState<CacheArtistRow[]>([]);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    fetch(`${API}/files/cache`, { cache: "no-store" })
      .then((r) => r.json())
      .then(setRows)
      .catch(() => {});
  }, []);

  const filtered = filter
    ? rows.filter((r) => (r.name || "").toLowerCase().includes(filter.toLowerCase())
                       || String(r.cm_id).includes(filter))
    : rows;

  return (
    <div>
      <input
        className="dialog-input files-filter"
        placeholder={t("files.filter_placeholder", { n: rows.length })}
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
      />
      <div className="files-cache-list">
        <table className="files-cache-table">
          <thead>
            <tr>
              <th>cm_id</th>
              <th>Name</th>
              <th>Country</th>
              <th>Endpoints</th>
              <th>Last fetched</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r) => (
              <tr key={r.cm_id}>
                <td><code>{r.cm_id}</code></td>
                <td>{r.name || "—"}</td>
                <td>{r.country_code || "—"}</td>
                <td>{r.n_endpoints}</td>
                <td className="files-cache-mtime">{formatTimestamp(r.last_modified)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && rows.length > 0 && (
          <div className="page-empty">No matches.</div>
        )}
      </div>
    </div>
  );
}

// ─── Internal tab ────────────────────────────────────────────────────────
function InternalTab() {
  const [files, setFiles] = useState<InternalFile[]>([]);

  useEffect(() => {
    fetch(`${API}/files/internal`, { cache: "no-store" })
      .then((r) => r.json())
      .then(setFiles)
      .catch(() => {});
  }, []);

  return (
    <div>
      <p className="page-subtitle" style={{ marginBottom: 12 }}>
        FaroLatino&apos;s historical royalty data + calibration training sets. Read-only — edit these on disk via your code editor.
      </p>
      <table className="files-cache-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Size</th>
            <th>Last modified</th>
          </tr>
        </thead>
        <tbody>
          {files.map((f) => (
            <tr key={f.name}>
              <td>{f.name}</td>
              <td>{formatSize(f.size)}</td>
              <td className="files-cache-mtime">{formatTimestamp(f.mtime)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatTimestamp(epoch: number): string {
  if (!epoch) return "—";
  const d = new Date(epoch * 1000);
  return d.toLocaleString();
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
}
