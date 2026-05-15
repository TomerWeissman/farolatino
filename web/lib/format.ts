// Shared formatters used by both /evaluate and /compare dashboards.
//
// Pulled out of evaluate-dashboard.tsx in v0.5.2 so the compare page
// can reuse the same money / int / country-flag conventions without
// importing a giant component file just for the helpers.

const COUNTRY_NAMES: Record<string, string> = {
  US: "United States", MX: "Mexico", AR: "Argentina", BR: "Brazil",
  CO: "Colombia", CL: "Chile", PE: "Peru", VE: "Venezuela",
  EC: "Ecuador", BO: "Bolivia", PY: "Paraguay", UY: "Uruguay",
  ES: "Spain", PT: "Portugal", FR: "France", DE: "Germany",
  IT: "Italy", GB: "United Kingdom", NL: "Netherlands", PR: "Puerto Rico",
  DO: "Dominican Rep.", CA: "Canada", JP: "Japan", KR: "Korea",
  AU: "Australia", ZA: "South Africa", IN: "India", CN: "China",
};

// Tier accent color. Editorial palette — minimal accent on score,
// tier label, recommendation border. Mirrored on /compare so
// Artist A's column uses the same color the dashboard would.
export const TIER_COLOR: Record<string, string> = {
  BUY: "#16a34a",
  PROSPECT: "#2563eb",
  WATCH: "#d97706",
  PASS: "#6b7280",
};

export function formatInt(n: number): string {
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)}B`;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return n.toLocaleString();
}

export function formatMoney(n: number): string {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(0)}K`;
  return `$${Math.round(n).toLocaleString()}`;
}

export function formatDate(s: string, lang: string = "en"): string {
  try {
    const d = new Date(s);
    if (!isNaN(d.getTime())) {
      const locale = lang === "es" ? "es-ES" : "en-US";
      return d.toLocaleDateString(locale, { year: "numeric", month: "short", day: "numeric" });
    }
  } catch {
    /* fallthrough */
  }
  return s;
}

/** ISO 3166-1 alpha-2 country code → flag emoji. */
export function countryFlag(cc: string): string {
  if (!cc || cc.length !== 2) return "🌐";
  const upper = cc.toUpperCase();
  return (
    String.fromCodePoint(upper.charCodeAt(0) + 127397) +
    String.fromCodePoint(upper.charCodeAt(1) + 127397)
  );
}

export function countryName(cc: string): string {
  return COUNTRY_NAMES[cc.toUpperCase()] ?? cc;
}

type Tfn = (key: string, vars?: Record<string, string | number>) => string;

/**
 * Localized label for a scoring dimension (`momentum`, `geographic_fit`, …).
 *
 * Reads `dimension.<name>.label` from the i18n catalog. If the key is
 * missing (new dimension shipped from the backend that we haven't
 * translated yet), falls back to the snake_case → "Title Case" rule
 * the dashboards used before v0.5.3 — so a missing translation reads
 * sensibly in English rather than rendering `⟦missing:…⟧`.
 */
export function dimensionLabel(t: Tfn, name: string): string {
  const v = t(`dimension.${name}.label`);
  if (v.startsWith("⟦missing:")) {
    return name.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
  }
  return v;
}

/** Companion to dimensionLabel for the info-tooltip body. Returns null
 *  when no description is wired up, so the caller can omit the tooltip. */
export function dimensionDescription(t: Tfn, name: string): string | null {
  const v = t(`dimension.${name}.description`);
  if (v.startsWith("⟦missing:")) return null;
  return v;
}

/** Subtle off-white tint behind the recommendation block per tier. */
export function tintFor(tier: string): string {
  switch (tier) {
    case "BUY": return "#f0f7f0";
    case "PROSPECT": return "#f0f4fa";
    case "WATCH": return "#f5f3ed";
    case "PASS": return "#f5f5f5";
    default: return "#f5f3ed";
  }
}
