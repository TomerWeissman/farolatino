"use client";

// React context provider for the language preference.
//
// Read order on mount:
//   1. localStorage.faroai-language — the snapshot from the last
//      session, applied immediately so the UI doesn't flash English
//      while waiting for the API.
//   2. GET /api/preferences — authoritative source, reconciles the
//      cached value if the server has a different one.
//
// On `setLang`:
//   1. Update local state + localStorage instantly (UI flips).
//   2. PUT /api/preferences in the background to persist + so the
//      server-rendered Markdown / LLM persona pick up the new value
//      on the next chat or evaluate call.

import {
  ReactNode,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import {
  DEFAULT_LANGUAGE,
  Language,
  SUPPORTED_LANGUAGES,
  tFor,
} from "./messages";

const LS_KEY = "faroai-language";

type I18nValue = {
  lang: Language;
  setLang: (next: Language) => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
};

const I18nContext = createContext<I18nValue | null>(null);

function readCachedLang(): Language {
  if (typeof window === "undefined") return DEFAULT_LANGUAGE;
  try {
    const v = window.localStorage.getItem(LS_KEY);
    if (v && (SUPPORTED_LANGUAGES as string[]).includes(v)) {
      return v as Language;
    }
  } catch {
    /* localStorage not available in some contexts */
  }
  return DEFAULT_LANGUAGE;
}

export function I18nProvider({ children }: { children: ReactNode }) {
  // Lazy initial state so SSR returns the default but the first
  // client render picks up the cached value.
  const [lang, setLangState] = useState<Language>(() => readCachedLang());

  // Reconcile with the server on mount — if the user changed language
  // on a different device / window, we pick that up here.
  useEffect(() => {
    let cancelled = false;
    fetch("/api/preferences", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((data: { language?: Language } | null) => {
        if (cancelled || !data?.language) return;
        if ((SUPPORTED_LANGUAGES as string[]).includes(data.language)) {
          setLangState(data.language);
          try {
            window.localStorage.setItem(LS_KEY, data.language);
          } catch {
            /* ignore */
          }
        }
      })
      .catch(() => {
        // Backend down — fall back to whatever we cached.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const setLang = useCallback((next: Language) => {
    setLangState(next);
    try {
      window.localStorage.setItem(LS_KEY, next);
    } catch {
      /* ignore */
    }
    // Persist server-side so the LLM persona + dossier renderer pick
    // up the change on the next call. Fire-and-forget — the UI has
    // already flipped, server reconciliation is async.
    fetch("/api/preferences", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ language: next }),
    }).catch(() => {
      /* swallow — the localStorage cache covers the offline case */
    });
  }, []);

  const t = useCallback(
    (key: string, vars?: Record<string, string | number>) =>
      tFor(lang, key, vars),
    [lang],
  );

  return (
    <I18nContext.Provider value={{ lang, setLang, t }}>
      {children}
    </I18nContext.Provider>
  );
}

/** Returns the current `t(key, vars?)` translation function. */
export function useT(): I18nValue["t"] {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    // Defensive fallback for anything rendered outside the provider
    // (e.g. early static-export pages). English everywhere.
    return (key, vars) => tFor(DEFAULT_LANGUAGE, key, vars);
  }
  return ctx.t;
}

/** Returns the current language + setter for the Settings toggle. */
export function useLanguage(): { lang: Language; setLang: (next: Language) => void } {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    return { lang: DEFAULT_LANGUAGE, setLang: () => {} };
  }
  return { lang: ctx.lang, setLang: ctx.setLang };
}
