"use client";

// Placeholder for the dedicated /compare page. v0.3.1 only ships the
// landing strip — the real comparison-graphs flow is planned for v0.3.2
// (separate plan; see user feedback 2026-05-07: "I want to have a
// separate compare page... two text boxes... it creates a set of
// graphs that show the comparison").
//
// In the meantime this page reads ?primary= and ?primary_cm_id= so the
// "Compare to another artist" button on /evaluate has a reasonable
// destination — the user can already see which artist they were
// comparing from, and a one-click route back to the dossier.

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useT } from "@/lib/i18n/context";

export function CompareStub() {
  const t = useT();
  const searchParams = useSearchParams();
  const primary = searchParams.get("primary");
  const primaryCmId = searchParams.get("primary_cm_id");

  return (
    <div className="evaluate-shell">
      <header className="evaluate-header">
        <div className="evaluate-eyebrow">{t("compare.eyebrow")}</div>
      </header>
      <div className="evaluate-empty">
        <div className="evaluate-loading-title" style={{ marginBottom: 12 }}>
          {t("compare.coming_soon")}
        </div>
        <p className="evaluate-empty-hint">
          {primary
            ? t("compare.body_with_primary", { artist: primary })
            : t("compare.body_no_primary")}
        </p>
        <div style={{ marginTop: 16 }}>
          <Link
            href={primary
              ? `/evaluate?artist=${encodeURIComponent(primary)}${primaryCmId ? `&cm_id=${primaryCmId}` : ""}`
              : "/evaluate"}
            className="evaluate-btn-link"
          >
            {primary ? t("compare.back_to_artist", { artist: primary }) : t("compare.back_to_evaluate")}
          </Link>
        </div>
      </div>
    </div>
  );
}
