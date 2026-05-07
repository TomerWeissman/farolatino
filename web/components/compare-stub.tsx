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

export function CompareStub() {
  const searchParams = useSearchParams();
  const primary = searchParams.get("primary");
  const primaryCmId = searchParams.get("primary_cm_id");

  return (
    <div className="evaluate-shell">
      <header className="evaluate-header">
        <div className="evaluate-eyebrow">Compare</div>
      </header>
      <div className="evaluate-empty">
        <div className="evaluate-loading-title" style={{ marginBottom: 12 }}>
          Compare page — coming in v0.3.2
        </div>
        <p className="evaluate-empty-hint">
          {primary ? (
            <>
              Carrying <strong>{primary}</strong> across as the first artist. The full
              comparison flow (two text boxes, side-by-side graphs across reach,
              revenue, momentum and scoring) is being built next.
            </>
          ) : (
            <>The full comparison flow (two text boxes, side-by-side graphs) is being built next.</>
          )}
        </p>
        <div style={{ marginTop: 16 }}>
          <Link
            href={primary
              ? `/evaluate?artist=${encodeURIComponent(primary)}${primaryCmId ? `&cm_id=${primaryCmId}` : ""}`
              : "/evaluate"}
            className="evaluate-btn-link"
          >
            ← Back to {primary ? primary + "'s dossier" : "Evaluate"}
          </Link>
        </div>
      </div>
    </div>
  );
}
