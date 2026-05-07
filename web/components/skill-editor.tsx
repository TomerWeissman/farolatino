"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Plus, Trash2, Save, RotateCcw } from "lucide-react";
import { useT } from "@/lib/i18n/context";
import { cn } from "@/lib/utils";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

// "default" = original bundled, "update" = latest from a code-only update,
// "user" = customized or created by the user (immune to updates).
type SkillSource = "default" | "update" | "user";
type SkillSummary = { slug: string; name: string; description: string; source: SkillSource };
type SkillDetail = SkillSummary & { body: string; full_markdown: string };

function sourceBadgeLabel(s: SkillSource): string {
  if (s === "user") return "edited";
  if (s === "update") return "updated";
  return "default";
}

const API = "/api";

export function SkillEditor() {
  const t = useT();
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [detail, setDetail] = useState<SkillDetail | null>(null);
  const [editor, setEditor] = useState("");
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);

  const reload = useCallback(async () => {
    const r = await fetch(`${API}/skills`, { cache: "no-store" });
    if (!r.ok) return;
    const list: SkillSummary[] = await r.json();
    setSkills(list);
    if (list.length && !selectedSlug) setSelectedSlug(list[0].slug);
  }, [selectedSlug]);

  useEffect(() => {
    reload();
  }, [reload]);

  // Load detail whenever the selected skill changes.
  useEffect(() => {
    if (!selectedSlug) return;
    let cancelled = false;
    (async () => {
      const r = await fetch(`${API}/skills/${selectedSlug}`, { cache: "no-store" });
      if (!r.ok) return;
      const d: SkillDetail = await r.json();
      if (cancelled) return;
      setDetail(d);
      setEditor(d.full_markdown);
      setDirty(false);
      setStatus(null);
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedSlug]);

  async function save() {
    if (!detail) return;
    setSaving(true);
    setStatus(null);
    try {
      const r = await fetch(`${API}/skills/${detail.slug}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ full_markdown: editor }),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({ detail: r.statusText }));
        throw new Error(err.detail || "save failed");
      }
      const d: SkillDetail = await r.json();
      setDetail(d);
      setEditor(d.full_markdown);
      setDirty(false);
      setStatus({ kind: "ok", msg: "Saved." });
      // Re-pull list in case name/description changed.
      reload();
    } catch (e) {
      setStatus({ kind: "err", msg: e instanceof Error ? e.message : "save failed" });
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    if (!detail) return;
    if (detail.source !== "user") {
      // Defaults can't be deleted, only overridden. The user wants
      // "Reset to default" (which is no-op for an already-default skill).
      setStatus({ kind: "err", msg: "Default skills can't be deleted. Edit it to customize, or it's already the default." });
      return;
    }
    if (!confirm(`Delete @${detail.slug}?\n\nThis is a user-created skill — it'll be removed entirely.`)) return;
    const r = await fetch(`${API}/skills/${detail.slug}`, { method: "DELETE" });
    if (!r.ok && r.status !== 204) {
      const err = await r.json().catch(() => ({ detail: r.statusText }));
      setStatus({ kind: "err", msg: err.detail || "delete failed" });
      return;
    }
    setDetail(null);
    setSelectedSlug(null);
    setEditor("");
    await reload();
  }

  async function resetToDefault() {
    if (!detail) return;
    if (detail.source !== "user") return;
    if (!confirm(`Reset @${detail.slug} to default?\n\nYour customizations will be discarded and the original bundled version will be used.`)) return;
    const r = await fetch(`${API}/skills/${detail.slug}/reset`, { method: "POST" });
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: r.statusText }));
      setStatus({ kind: "err", msg: err.detail || "reset failed" });
      return;
    }
    const body = await r.json();
    if (body) {
      setDetail(body);
      setEditor(body.full_markdown);
      setDirty(false);
      setStatus({ kind: "ok", msg: "Reset to default." });
    } else {
      // Skill was user-only and has been removed entirely.
      setDetail(null);
      setSelectedSlug(null);
      setEditor("");
    }
    await reload();
  }

  return (
    <div className="page-shell skills-page">
      <header className="skills-header">
        <div>
          <h1 className="page-title">{t("skills.title")}</h1>
          <p className="page-subtitle">
            Edit, add, or delete the @-skills that drive the chat. Files live in <code>.claude/skills/</code>.
          </p>
        </div>
        <NewSkillDialog onCreated={async (slug) => {
          await reload();
          setSelectedSlug(slug);
        }} />
      </header>

      <div className="skills-grid">
        <aside className="skills-list">
          {skills.map((s) => (
            <button
              key={s.slug}
              type="button"
              className={cn("skills-list-item", selectedSlug === s.slug && "skills-list-item-active")}
              onClick={() => setSelectedSlug(s.slug)}
            >
              <div className="skills-list-slug">
                @{s.slug}
                {s.source !== "default" && (
                  <span
                    style={{
                      marginLeft: 8,
                      fontSize: 10,
                      padding: "1px 6px",
                      borderRadius: 8,
                      background: s.source === "user" ? "#fef3c7" : "#dbeafe",
                      color: s.source === "user" ? "#92400e" : "#1e40af",
                      fontWeight: 500,
                      textTransform: "uppercase",
                      letterSpacing: 0.4,
                    }}
                  >
                    {sourceBadgeLabel(s.source)}
                  </span>
                )}
              </div>
              <div className="skills-list-name">{s.name}</div>
            </button>
          ))}
          {skills.length === 0 && <div className="page-empty">Loading…</div>}
        </aside>

        <section className="skills-editor">
          {detail ? (
            <>
              <div className="skills-editor-meta">
                <strong>{detail.name}</strong> — {detail.description}
                {detail.source === "user" && (
                  <span style={{ marginLeft: 12, fontSize: 12, color: "#92400e" }}>
                    · You&apos;ve edited this. Updates won&apos;t overwrite your version.
                  </span>
                )}
                {detail.source === "update" && (
                  <span style={{ marginLeft: 12, fontSize: 12, color: "#1e40af" }}>
                    · Latest version from a recent update.
                  </span>
                )}
              </div>
              <textarea
                className="skills-editor-textarea"
                value={editor}
                onChange={(e) => {
                  setEditor(e.target.value);
                  setDirty(e.target.value !== detail.full_markdown);
                }}
                spellCheck={false}
                rows={28}
              />
              <div className="skills-editor-actions">
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={!dirty || saving}
                  onClick={save}
                >
                  <Save size={14} /> {saving ? "Saving…" : "Save"}
                </button>
                {detail.source === "user" && (
                  <button
                    type="button"
                    className="btn"
                    onClick={resetToDefault}
                    title="Discard your customization and use the bundled version again"
                  >
                    <RotateCcw size={14} /> Reset to default
                  </button>
                )}
                <button
                  type="button"
                  className="btn btn-danger"
                  onClick={remove}
                  disabled={detail.source !== "user"}
                  title={detail.source !== "user" ? "Default skills can't be deleted — use Reset instead" : "Delete this user-created skill"}
                >
                  <Trash2 size={14} /> Delete
                </button>
                {status && (
                  <span className={cn("skills-editor-status", status.kind === "err" && "skills-editor-status-err")}>
                    {status.msg}
                  </span>
                )}
              </div>
            </>
          ) : (
            <div className="page-empty">Pick a skill on the left.</div>
          )}
        </section>
      </div>
    </div>
  );
}

function NewSkillDialog({ onCreated }: { onCreated: (slug: string) => void }) {
  const [open, setOpen] = useState(false);
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const slugRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (open) setTimeout(() => slugRef.current?.focus(), 100);
  }, [open]);

  function reset() {
    setSlug("");
    setName("");
    setDescription("");
    setErr(null);
    setBusy(false);
  }

  async function submit() {
    setErr(null);
    setBusy(true);
    try {
      const r = await fetch(`${API}/skills`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slug, name, description, body: "" }),
      });
      if (!r.ok) {
        const e = await r.json().catch(() => ({ detail: r.statusText }));
        throw new Error(e.detail || "create failed");
      }
      onCreated(slug);
      setOpen(false);
      reset();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "create failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button type="button" className="btn btn-primary" onClick={() => setOpen(true)}>
        <Plus size={14} /> New skill
      </button>
      <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) reset(); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add a new skill</DialogTitle>
          <DialogDescription>
            Creates <code>.claude/skills/&lt;slug&gt;.md</code> with a starter template.
          </DialogDescription>
        </DialogHeader>
        <div className="dialog-form">
          <label className="dialog-label">
            <span>Slug</span>
            <input
              ref={slugRef}
              className="dialog-input"
              value={slug}
              onChange={(e) => setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ""))}
              placeholder="lowercase, no spaces (e.g. shortlist)"
              maxLength={32}
            />
          </label>
          <label className="dialog-label">
            <span>Name</span>
            <input
              className="dialog-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Shortlist Prospects"
            />
          </label>
          <label className="dialog-label">
            <span>Description</span>
            <input
              className="dialog-input"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="One-line tooltip in the picker"
            />
          </label>
          {err && <div className="dialog-error">⚠️ {err}</div>}
        </div>
        <DialogFooter>
          <button
            type="button"
            className="btn btn-primary"
            disabled={!slug || !name || busy}
            onClick={submit}
          >
            {busy ? "Creating…" : "Create"}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
    </>
  );
}
