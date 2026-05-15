"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle2, ArrowRight, ExternalLink, Eye, EyeOff, Loader2 } from "lucide-react";
import { useT } from "@/lib/i18n/context";

const API = "/api";

// localStorage flag — set when the user clicks "Skip for now" so we
// don't redirect them back to /onboarding on every relaunch. Cleared
// automatically the moment they actually save an LLM key.
const SKIP_KEY = "faroai-onboarding-skipped";

type OnboardingStatus = {
  needs_onboarding: boolean;
  has_llm_key: boolean;
  has_chartmetric: boolean;
  has_spotify: boolean;
  has_youtube: boolean;
  detected_provider: "anthropic" | "openai" | "gemini" | "none";
};

type SaveStatus = "idle" | "saving" | "saved" | "error";

export function OnboardingWizard() {
  const t = useT();
  const router = useRouter();
  const [status, setStatus] = useState<OnboardingStatus | null>(null);

  const reload = useCallback(async () => {
    try {
      const r = await fetch(`${API}/onboarding/status`, { cache: "no-store" });
      if (r.ok) setStatus(await r.json());
    } catch {
      // Backend down — show the form anyway. Save will retry.
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const handleDone = () => {
    // The Continue button is only enabled after the LLM key is saved,
    // so unset the skip flag — they're not skipping anymore.
    localStorage.removeItem(SKIP_KEY);
    router.push("/");
  };

  const handleSkip = () => {
    if (confirm(t("onboarding.skip_confirm"))) {
      localStorage.setItem(SKIP_KEY, "1");
      router.push("/");
    }
  };

  if (!status) {
    return (
      <div className="page-shell" style={{ padding: 48 }}>
        <Loader2 className="spin" size={20} /> {t("onboarding.loading")}
      </div>
    );
  }

  return (
    <div className="page-shell" style={{ maxWidth: 720, margin: "0 auto", paddingTop: 32 }}>
      <header style={{ marginBottom: 32, textAlign: "center" }}>
        <h1 style={{ fontSize: 28, fontWeight: 600, marginBottom: 8 }}>{t("onboarding.title")}</h1>
        <p style={{ fontSize: 14, color: "#6b7280", lineHeight: 1.5 }}>{t("onboarding.subtitle")}</p>
      </header>

      <KeyCard
        title={t("onboarding.section.llm")}
        subtitle={t("onboarding.section.llm.subtitle")}
        envVar="LLM_API_KEY"
        placeholder="sk-ant-… (Claude) · sk-… (OpenAI) · AIza… (Gemini)"
        helpText={
          status.detected_provider !== "none"
            ? t("onboarding.detected", { provider: displayProvider(status.detected_provider) })
            : t("onboarding.section.llm.help")
        }
        getKeyLinks={[
          { label: "Get an Anthropic key (sk-ant-…)", url: "https://console.anthropic.com/settings/keys" },
          { label: "Get an OpenAI key (sk-…)", url: "https://platform.openai.com/api-keys" },
          { label: "Get a Gemini key (AIza…) — free tier", url: "https://aistudio.google.com/apikey" },
        ]}
        configured={status.has_llm_key}
        onSaved={reload}
        required
      />

      <KeyCard
        title={t("onboarding.section.chartmetric")}
        subtitle={t("onboarding.section.chartmetric.subtitle")}
        envVar="CHARTMETRIC_REFRESH_TOKEN"
        placeholder="Long token from your Chartmetric account…"
        helpText={t("onboarding.section.chartmetric.help")}
        getKeyLinks={[
          { label: "Chartmetric API docs", url: "https://chartmetric.com/api" },
        ]}
        configured={status.has_chartmetric}
        onSaved={reload}
      />

      <KeyCard
        title={t("onboarding.section.spotify")}
        subtitle={t("onboarding.section.spotify.subtitle")}
        envVar="SPOTIFY_CLIENT_ID"
        placeholder="Client ID (32 chars)…"
        helpText={t("onboarding.section.spotify.help")}
        getKeyLinks={[
          { label: "Spotify developer dashboard", url: "https://developer.spotify.com/dashboard" },
        ]}
        configured={status.has_spotify}
        onSaved={reload}
        secondaryEnvVar="SPOTIFY_CLIENT_SECRET"
        secondaryPlaceholder="Client Secret (32 chars)…"
      />

      <KeyCard
        title={t("onboarding.section.youtube")}
        subtitle={t("onboarding.section.youtube.subtitle")}
        envVar="YOUTUBE_API_KEY"
        placeholder="YouTube Data API v3 key…"
        helpText={t("onboarding.section.youtube.help")}
        getKeyLinks={[
          { label: "Google Cloud — enable YouTube Data API", url: "https://console.cloud.google.com/apis/library/youtube.googleapis.com" },
        ]}
        configured={status.has_youtube}
        onSaved={reload}
      />

      <div style={{ display: "flex", gap: 16, alignItems: "center", marginTop: 32, justifyContent: "center" }}>
        <button
          type="button"
          className="btn btn-primary"
          onClick={handleDone}
          disabled={!status.has_llm_key}
          title={status.has_llm_key ? t("onboarding.start_chatting") : t("onboarding.need_llm_first")}
          style={{ padding: "10px 24px", fontSize: 15 }}
        >
          {status.has_llm_key ? <>{t("onboarding.continue_to_chat")} <ArrowRight size={14} /></> : t("onboarding.add_llm_first")}
        </button>
        {!status.has_llm_key && (
          <button
            type="button"
            onClick={handleSkip}
            style={{
              background: "transparent",
              border: "none",
              color: "#9ca3af",
              cursor: "pointer",
              fontSize: 13,
              textDecoration: "underline",
            }}
          >
            {t("onboarding.skip")}
          </button>
        )}
      </div>

      <p style={{ marginTop: 32, textAlign: "center", fontSize: 12, color: "#9ca3af" }}>
        {t("onboarding.footer")}
      </p>
    </div>
  );
}

function displayProvider(p: string) {
  return {
    anthropic: "Anthropic (Claude)",
    openai: "OpenAI (GPT)",
    gemini: "Google (Gemini)",
    none: "—",
  }[p] ?? p;
}


// ─── KeyCard ───────────────────────────────────────────────────────────
//
// One row per service. Designed to read top-to-bottom: title + status
// indicator → why you need it → "Get a key here →" link → input field
// + Save button. Same shape regardless of whether it's required or
// optional; status pill carries the urgency.

function KeyCard({
  title,
  subtitle,
  envVar,
  placeholder,
  helpText,
  getKeyLinks,
  configured,
  onSaved,
  required = false,
  secondaryEnvVar,
  secondaryPlaceholder,
}: {
  title: string;
  subtitle: string;
  envVar: string;
  placeholder: string;
  helpText: string;
  getKeyLinks: { label: string; url: string }[];
  configured: boolean;
  onSaved: () => void;
  required?: boolean;
  secondaryEnvVar?: string;
  secondaryPlaceholder?: string;
}) {
  const [primary, setPrimary] = useState("");
  const [secondary, setSecondary] = useState("");
  const [reveal, setReveal] = useState(false);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  async function save() {
    if (!primary && !secondary) return;
    setSaveStatus("saving");
    setErrorMsg(null);
    try {
      const updates: Record<string, string> = {};
      if (primary) updates[envVar] = primary;
      if (secondary && secondaryEnvVar) updates[secondaryEnvVar] = secondary;
      const r = await fetch(`${API}/env`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ updates }),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({ detail: r.statusText }));
        throw new Error(err.detail || "save failed");
      }
      setPrimary("");
      setSecondary("");
      setSaveStatus("saved");
      onSaved();
      setTimeout(() => setSaveStatus("idle"), 2500);
    } catch (e) {
      setSaveStatus("error");
      setErrorMsg(e instanceof Error ? e.message : "save failed");
    }
  }

  return (
    <div
      style={{
        border: configured ? "1px solid #d1fae5" : required ? "1px solid #fde68a" : "1px solid #e5e7eb",
        background: configured ? "#f0fdf4" : "#fff",
        borderRadius: 12,
        padding: 20,
        marginBottom: 16,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
        <h3 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>
          {title}
          {required && !configured && (
            <span style={{ marginLeft: 8, fontSize: 11, padding: "2px 8px", borderRadius: 8, background: "#fef3c7", color: "#92400e", fontWeight: 500 }}>
              REQUIRED
            </span>
          )}
        </h3>
        {configured && (
          <span style={{ display: "flex", alignItems: "center", gap: 4, color: "#059669", fontSize: 13, fontWeight: 500 }}>
            <CheckCircle2 size={14} /> Connected
          </span>
        )}
      </div>
      <p style={{ fontSize: 13, color: "#6b7280", margin: "0 0 12px" }}>{subtitle}</p>

      {/* "Get a key here" links — small but visible */}
      {!configured && (
        <div style={{ marginBottom: 12, display: "flex", flexDirection: "column", gap: 4 }}>
          {getKeyLinks.map((l) => (
            <a
              key={l.url}
              href={l.url}
              target="_blank"
              rel="noopener noreferrer"
              style={{ fontSize: 12, color: "#2563eb", textDecoration: "underline", display: "inline-flex", alignItems: "center", gap: 4 }}
            >
              {l.label} <ExternalLink size={11} />
            </a>
          ))}
        </div>
      )}

      <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: secondaryEnvVar ? 8 : 0 }}>
        <input
          type={reveal ? "text" : "password"}
          className="dialog-input"
          value={primary}
          onChange={(e) => setPrimary(e.target.value)}
          placeholder={configured ? "(already set — paste new key to replace)" : placeholder}
          style={{ flex: 1 }}
        />
        <button
          type="button"
          onClick={() => setReveal((r) => !r)}
          style={{ background: "transparent", border: "1px solid #e5e7eb", borderRadius: 6, padding: "6px 10px", cursor: "pointer" }}
          aria-label={reveal ? "Hide" : "Show"}
        >
          {reveal ? <EyeOff size={14} /> : <Eye size={14} />}
        </button>
      </div>

      {secondaryEnvVar && (
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input
            type={reveal ? "text" : "password"}
            className="dialog-input"
            value={secondary}
            onChange={(e) => setSecondary(e.target.value)}
            placeholder={secondaryPlaceholder}
            style={{ flex: 1 }}
          />
        </div>
      )}

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 12 }}>
        <p style={{ fontSize: 11, color: "#9ca3af", margin: 0 }}>{helpText}</p>
        <button
          type="button"
          className="btn btn-primary"
          onClick={save}
          disabled={(!primary && !secondary) || saveStatus === "saving"}
          style={{ padding: "6px 14px", fontSize: 13 }}
        >
          {saveStatus === "saving" ? "Saving…" : saveStatus === "saved" ? "Saved ✓" : "Save"}
        </button>
      </div>
      {errorMsg && (
        <p style={{ fontSize: 12, color: "#7f1d1d", marginTop: 8, marginBottom: 0 }}>⚠️ {errorMsg}</p>
      )}
    </div>
  );
}
