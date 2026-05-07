"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { Dossier } from "@/lib/types";

// What the parent (evaluate.tsx) hands us per artist slot.
type LoadedDossier = {
  artist: string;
  cm_id: number;
  dossier: Dossier;
  rendered_markdown: string;
};

// Tier → accent color. Editorial palette: used minimally as accent on
// the score, tier label, recommendation border. Everything else is
// black/gray text on cream background.
const TIER_COLOR: Record<string, string> = {
  BUY: "#16a34a",
  PROSPECT: "#2563eb",
  WATCH: "#d97706",
  PASS: "#6b7280",
};

export function EvaluateDashboard({
  primary,
  onContinueInChat,
  onCompare,
}: {
  primary: LoadedDossier;
  onContinueInChat: () => void;
  onCompare: () => void;
}) {
  return (
    <div className="evaluate-dashboard">
      <ArtistColumn data={primary} />

      <div className="evaluate-cta-row">
        <button type="button" className="evaluate-btn evaluate-btn-primary" onClick={onContinueInChat}>
          Continue in chat about {primary.artist} →
        </button>
        <button type="button" className="evaluate-btn evaluate-btn-secondary" onClick={onCompare}>
          Compare to another artist
        </button>
      </div>
    </div>
  );
}


/**
 * Single-artist column. In single-artist mode this fills the whole
 * page; in compare mode there are two of these side-by-side.
 */
function ArtistColumn({ data }: { data: LoadedDossier }) {
  const { dossier } = data;
  const tier = dossier.prospect_score.tier?.toUpperCase() ?? "?";
  const accent = TIER_COLOR[tier] ?? "#1a1a1a";
  return (
    <article className="evaluate-column">
      <Hero data={data} accent={accent} />
      {/* Scoring distribution comes first — the user wants to see WHY
          the overall score landed where it did before the supporting
          metrics. Reach / Revenue / Markets are the evidence behind
          each dimension, not the headline. */}
      <Scoring score={dossier.prospect_score} />
      <Reach metrics={dossier.metrics} />
      <Revenue revenue={dossier.revenue_projection} />
      <Markets markets={dossier.geographic_profile?.top_markets} />
      <Milestones milestones={dossier.career_trajectory?.milestones} />
      <Catalog catalog={dossier.catalog} urls={dossier.identity.urls} />
      <Similar similar={dossier.competitive_context?.similar_artists} />
      <Risks risks={dossier.risk_signals} />
      <Recommendation tier={tier} accent={accent} ident={dossier.identity} />
    </article>
  );
}


// ─── Sections (each renders nothing if its data is empty) ────────────

function Hero({ data, accent }: { data: LoadedDossier; accent: string }) {
  const { dossier } = data;
  const ident = dossier.identity;
  const score = dossier.prospect_score;
  const initials = ident.name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((s) => s[0]?.toUpperCase() ?? "")
    .join("");
  // Build social links from identity.urls. Falls back to actionable.social_links.
  const urls = (ident.urls && Object.keys(ident.urls).length > 0)
    ? ident.urls
    : (dossier.actionable?.social_links ?? {});
  const socialOrder: Array<[string, string]> = [
    ["spotify", "Spotify"],
    ["youtube", "YouTube"],
    ["instagram", "Instagram"],
    ["tiktok", "TikTok"],
  ];
  const socials = socialOrder
    .map(([k, label]) => [urls[k], label] as const)
    .filter(([url]) => !!url);

  return (
    <header className="ev-section ev-hero">
      <div className="ev-eyebrow">Artist · Prospect Dossier</div>
      <div className="ev-header-grid">
        {ident.image ? (
          <img
            className="ev-photo"
            src={ident.image}
            alt={ident.name}
            onError={(e) => {
              const target = e.target as HTMLImageElement;
              const fallback = document.createElement("div");
              fallback.className = "ev-photo-fallback";
              fallback.textContent = initials || ident.name[0]?.toUpperCase() || "?";
              target.replaceWith(fallback);
            }}
          />
        ) : (
          <div className="ev-photo-fallback">{initials || "?"}</div>
        )}
        <div>
          <h1 className="ev-name">{ident.name}</h1>
          <div className="ev-meta">
            {(ident.genres ?? []).slice(0, 5).join(" · ") || "—"}
            {ident.career_stage && (
              <>
                {" · "}<strong>{ident.career_stage}</strong>
                {ident.career_trend && ` / ${ident.career_trend}`}
              </>
            )}
            {ident.label && (
              <>
                {" · "}signed to <strong>{ident.label}</strong>
              </>
            )}
          </div>
          {socials.length > 0 && (
            <div className="ev-social-links">
              {socials.map(([url, label]) => (
                <a key={label} href={url} target="_blank" rel="noopener noreferrer" className="ev-social-link">
                  {label}<span className="ev-social-arrow">↗</span>
                </a>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="ev-hero-row">
        <div className="ev-score" style={{ color: accent }}>
          {Math.round(score.overall)}
          <span className="ev-score-suffix">/100</span>
        </div>
        <div className="ev-tier-block" style={{ color: accent }}>
          <div className="ev-tier-label" style={{ color: accent }}>{score.tier}</div>
          <div className="ev-tier-confidence">
            confidence {Math.round(score.confidence * 100)}%
            {score.data_completeness != null && ` · data ${Math.round(score.data_completeness * 100)}% complete`}
          </div>
        </div>
      </div>
    </header>
  );
}


function Reach({ metrics }: { metrics: Dossier["metrics"] }) {
  const sp = metrics.spotify ?? {};
  const yt = metrics.youtube ?? {};
  const ig = metrics.instagram ?? {};
  const tt = metrics.tiktok ?? {};
  const other = metrics.other ?? {};
  const cpp = metrics.cpp_score;
  const popularity = sp.popularity;

  return (
    <section className="ev-section">
      <h2 className="ev-h2">Reach</h2>
      <div className="ev-grid-4">
        <Stat
          big={sp.monthly_listeners ? formatInt(sp.monthly_listeners) : "—"}
          label="Spotify monthly"
          sub={[
            sp.monthly_listeners_change ?? null,
            sp.followers ? `${formatInt(sp.followers)} followers` : null,
          ].filter(Boolean).join(" · ") || undefined}
        />
        <Stat
          big={yt.subscribers ? formatInt(yt.subscribers) : "—"}
          label="YouTube subs"
          sub={yt.views ? `${formatInt(yt.views)} total views` : undefined}
        />
        <Stat
          big={ig.followers ? formatInt(ig.followers) : "—"}
          label="Instagram"
          sub={ig.engagement_rate ? `${ig.engagement_rate} engagement` : undefined}
        />
        <Stat
          big={tt.followers ? formatInt(tt.followers) : "—"}
          label="TikTok"
          sub={tt.likes ? `${formatInt(tt.likes)} total likes` : "no data"}
        />
      </div>
      {(other.shazam_count || other.deezer_fans || other.soundcloud_followers || popularity || cpp) && (
        <div className="ev-secondary-row">
          {other.shazam_count != null && <span>Shazam <strong>{formatInt(other.shazam_count)}</strong></span>}
          {other.deezer_fans != null && <span>Deezer <strong>{formatInt(other.deezer_fans)}</strong></span>}
          {other.soundcloud_followers != null && <span>SoundCloud <strong>{formatInt(other.soundcloud_followers)}</strong></span>}
          {popularity != null && <span>Spotify pop <strong>{popularity}/100</strong></span>}
          {cpp != null && <span>Chartmetric CPP <strong>{cpp.toFixed(2)}</strong></span>}
        </div>
      )}
      <div className="ev-source">Source: Chartmetric (aggregated from Spotify, YouTube, Instagram, TikTok, Shazam, Deezer, SoundCloud)</div>
    </section>
  );
}


function Revenue({ revenue }: { revenue: Dossier["revenue_projection"] }) {
  if (!revenue || revenue.note || !revenue.annual_projected) return null;
  const annual = revenue.annual_projected;
  // Same lo/hi multipliers the dossier_renderer uses for HIGH confidence.
  // Approximation since we don't have the artist_data here for the
  // confidence calc — use a wider band by default (0.6x – 1.7x).
  const lo = annual * 0.6;
  const hi = annual * 1.7;
  const distributor = annual * 0.26;
  const artist = annual * 0.74;
  const byPlatform = revenue.monthly_revenue_by_platform ?? {};
  const byPlatformAnnual: Array<[string, number]> = Object.entries(byPlatform)
    .map(([k, v]) => [k, (v ?? 0) * 12] as [string, number])
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1]);
  const totalAnnual = byPlatformAnnual.reduce((s, [, v]) => s + v, 0);

  return (
    <section className="ev-section">
      <h2 className="ev-h2">Revenue projection</h2>
      <div className="ev-revenue-grid">
        <Stat big={formatMoney(annual)} label="Annual gross (BRUTO)" sub={`Range ${formatMoney(lo)} – ${formatMoney(hi)} · all platforms`} />
        <Stat big={formatMoney(distributor)} label="Distributor cut if signed (~26%)" sub={`Artist payout (~74%): ${formatMoney(artist)}`} />
      </div>
      {byPlatformAnnual.length > 0 && totalAnnual > 0 && (
        <>
          <div className="ev-rev-platform-title">Per-platform breakdown (annual gross)</div>
          {byPlatformAnnual.slice(0, 6).map(([plat, amt]) => {
            const pct = (amt / totalAnnual) * 100;
            return (
              <div key={plat} className="ev-row ev-rev-platform">
                <div className="ev-row-label">{plat}</div>
                <div className="ev-bar"><span style={{ width: `${pct}%` }} /></div>
                <div className="ev-num-mono">{formatMoney(amt)}</div>
                <div className="ev-num-mono">{pct.toFixed(0)}%</div>
              </div>
            );
          })}
        </>
      )}
      <div className="ev-source">Source: revenue model · streams × per-platform RPM rates · see <code>mcp_server/tools/revenue_model.py</code></div>
    </section>
  );
}


function Scoring({ score }: { score: Dossier["prospect_score"] }) {
  const dims = score.dimensions ?? {};
  // Sort by score descending — strongest first, matches narrative.
  const rows = Object.entries(dims).sort((a, b) => b[1].score - a[1].score);
  const [openName, setOpenName] = useState<string | null>(null);

  if (rows.length === 0) return null;

  return (
    <section className="ev-section">
      <h2 className="ev-h2">Scoring · 7 dimensions</h2>
      {/* Column headers — without these, the trailing "85%" / "20%"
          numbers each row ends with read as random noise. Spelling
          "Confidence" and "Weight" out costs one line and removes a
          chunk of cognitive load. */}
      <div className="ev-row ev-row-headers" aria-hidden="true">
        <div className="ev-row-label">Dimension</div>
        <div />
        <div className="ev-num-mono">Score</div>
        <div className="ev-num-mono">Confidence</div>
        <div className="ev-num-mono">Weight</div>
      </div>
      {rows.map(([name, d]) => {
        const label = name.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
        const cls = d.score >= 80 ? "" : d.score >= 50 ? "warn" : "bad";
        const isOpen = openName === name;
        return (
          <div key={name}>
            <button
              type="button"
              className="ev-row ev-row-clickable"
              onClick={() => setOpenName(isOpen ? null : name)}
              aria-expanded={isOpen}
            >
              <div className="ev-row-label">{label}</div>
              <div className="ev-bar"><span className={cls} style={{ width: `${Math.min(100, d.score)}%` }} /></div>
              <div className="ev-num-mono ev-score-num">{Math.round(d.score)}</div>
              <div className="ev-num-mono ev-conf-num">{Math.round((d.confidence ?? 0) * 100)}%</div>
              <div className="ev-num-mono ev-weight-num">{Math.round((d.weight ?? 0) * 100)}%</div>
            </button>
            {isOpen && d.rationale && (
              <div className="ev-rationale">{d.rationale}</div>
            )}
          </div>
        );
      })}
      <div className="ev-legend">
        <strong>Score</strong> — 0–100 per dimension, blended into the overall by Weight.{" "}
        <strong>Confidence</strong> — how complete the data is for that dimension.{" "}
        <strong>Weight</strong> — share of the overall score this dimension contributes (sums to 100%).
      </div>
      <div className="ev-help">Click any row to see the rationale.</div>
      <div className="ev-source">Source: scoring profile <code>default</code> · weights and dimension definitions from <code>config/profiles.yaml</code></div>
    </section>
  );
}


function Markets({ markets }: { markets?: Dossier["geographic_profile"] extends infer T ? T extends { top_markets?: infer U } ? U : never : never }) {
  if (!markets || markets.length === 0) return null;
  const max = Math.max(...markets.map((m) => m.listeners ?? 0));
  return (
    <section className="ev-section">
      <h2 className="ev-h2">Top markets</h2>
      <div className="ev-row ev-market-row ev-row-headers" aria-hidden="true">
        <span />
        <div />
        <div />
        <div className="ev-num-mono">Listeners</div>
        <div className="ev-num-mono">90-day Δ</div>
      </div>
      <div className="ev-markets">
        {markets.slice(0, 6).map((m, i) => {
          const cc = m.country_code ?? m.country ?? "—";
          const listeners = m.listeners ?? 0;
          const pct = max > 0 ? (listeners / max) * 100 : 0;
          const flag = countryFlag(cc);
          return (
            <div key={`${cc}-${i}`} className="ev-row ev-market-row">
              <span className="ev-market-flag">{flag}</span>
              <div>{countryName(cc)}</div>
              <div className="ev-bar"><span style={{ width: `${pct}%` }} /></div>
              <div className="ev-num-mono">{formatInt(listeners)}</div>
              <div className="ev-num-mono">{m.growth ?? "—"}</div>
            </div>
          );
        })}
      </div>
      <div className="ev-legend">
        Bars are sized relative to this artist&apos;s top market — they show country share, not population share.
      </div>
      <div className="ev-source">Source: Chartmetric · Spotify monthly listeners by country</div>
    </section>
  );
}


function Milestones({ milestones }: { milestones?: Array<{ text: string; date?: string; platform?: string }> }) {
  if (!milestones || milestones.length === 0) return null;
  return (
    <section className="ev-section">
      <h2 className="ev-h2">Career milestones</h2>
      <div className="ev-milestones">
        {milestones.slice(0, 5).map((m, i) => (
          <div key={i} className="ev-milestone-row">
            <span className="ev-milestone-date">{m.date ? formatDate(m.date) : "—"}</span>
            <span className="ev-milestone-text">{m.text}</span>
            {m.platform && <span className="ev-milestone-platform">{m.platform}</span>}
          </div>
        ))}
      </div>
      <div className="ev-source">Source: Chartmetric · platform-tagged events (Spotify editorial adds, YouTube views milestones, chart entries)</div>
    </section>
  );
}


function Catalog({
  catalog,
  urls,
}: {
  catalog?: Dossier["catalog"];
  urls?: Record<string, string>;
}) {
  if (!catalog) return null;
  const r6 = catalog.releases_6m ?? 0;
  const r12 = catalog.releases_12m ?? 0;
  const total = catalog.total_tracks ?? 0;
  const editorial = catalog.editorial_playlists ?? 0;
  const tracks = catalog.latest_tracks ?? [];
  const spotifyArtistUrl = urls?.spotify;
  return (
    <section className="ev-section">
      <h2 className="ev-h2">Catalog</h2>
      <div className="ev-catalog-stats">
        <strong>{r6}</strong> releases · last 6 months · <strong>{r12}</strong> in last 12 months · <strong>{total}</strong> total tracks
        {editorial > 0 && (<> · <strong>{editorial}</strong> editorial playlists</>)}
      </div>
      {tracks.length > 0 && (
        <>
          <div className="ev-catalog-subtitle">Latest releases</div>
          {tracks.slice(0, 5).map((t, i) => {
            const trackUrl = spotifyArtistUrl ? buildSpotifySearchUrl(t.name) : null;
            return (
              <div key={i} className="ev-track-row">
                {trackUrl ? (
                  <a href={trackUrl} target="_blank" rel="noopener noreferrer" className="ev-track-link">
                    {t.name}<span className="ev-social-arrow">↗</span>
                  </a>
                ) : (
                  <span className="ev-track-name">{t.name}</span>
                )}
                <span className="ev-track-date">{t.release_date ? formatDate(t.release_date) : ""}</span>
              </div>
            );
          })}
        </>
      )}
      <div className="ev-source">Source: Chartmetric catalog · release dates and ISRCs from rights holders via DSPs</div>
    </section>
  );
}


function Similar({ similar }: { similar?: Dossier["competitive_context"] extends infer T ? T extends { similar_artists?: infer U } ? U : never : never }) {
  const router = useRouter();
  if (!similar || similar.length === 0) return null;
  return (
    <section className="ev-section">
      <h2 className="ev-h2">Similar artists</h2>
      <div className="ev-similar-grid">
        {similar.slice(0, 6).map((s, i) => {
          const cc = s.country_code ?? "—";
          return (
            <div key={i} className="ev-similar-card">
              <div className="ev-similar-name">{s.name}</div>
              <div className="ev-similar-meta">
                {countryFlag(cc)} {cc}
                {s.sp_monthly_listeners != null && ` · ${formatInt(s.sp_monthly_listeners)} monthly`}
                {s.signed === true && " · ✓ signed"}
                {s.signed === false && " · unsigned"}
              </div>
              <button
                type="button"
                className="evaluate-btn-link ev-similar-link"
                onClick={() => {
                  // Navigate to /evaluate with the artist name in URL — page
                  // re-mounts and runs the evaluation. Simpler than passing
                  // state through a query param: just trigger a fresh search.
                  router.push(`/evaluate?artist=${encodeURIComponent(s.name)}`);
                  // Fallback: if the page doesn't re-mount on same-route nav,
                  // dispatch a custom event the page can listen for.
                  window.dispatchEvent(new CustomEvent("faroai-evaluate-artist", { detail: { name: s.name } }));
                }}
              >
                Evaluate →
              </button>
            </div>
          );
        })}
      </div>
      <div className="ev-source">
        Source: Chartmetric &ldquo;related artists&rdquo; · audience overlap + collab graph (planned: tighter genre weighting in v0.3.2)
      </div>
    </section>
  );
}


function Risks({ risks }: { risks?: Record<string, string> }) {
  if (!risks) return null;
  const flagged = Object.entries(risks).filter(([, v]) => v && v !== "N/A" && v.trim() !== "");
  if (flagged.length === 0) return null;
  return (
    <section className="ev-section">
      <h2 className="ev-h2">Risk signals</h2>
      {flagged.map(([k, v]) => (
        <div key={k} className="ev-risk-row">
          <span className="ev-risk-warn">⚠</span>
          <strong>{k.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase())}</strong> — {v}
        </div>
      ))}
      <div className="ev-source">Source: rule-based heuristics over Chartmetric streaming and engagement data</div>
    </section>
  );
}


function Recommendation({ tier, accent, ident }: { tier: string; accent: string; ident: Dossier["identity"] }) {
  const body = recommendationBody(tier, ident);
  return (
    <section className="ev-section">
      <h2 className="ev-h2">Recommendation</h2>
      <div className="ev-reco" style={{ borderLeftColor: accent, background: tintFor(tier) }}>
        <div className="ev-reco-tier" style={{ color: accent }}>{tier}</div>
        <div className="ev-reco-body">{body}</div>
      </div>
    </section>
  );
}


// ─── Reusable bits ────────────────────────────────────────────────

function Stat({ big, label, sub }: { big: string; label: string; sub?: string }) {
  return (
    <div className="ev-stat">
      <div className="ev-stat-num">{big}</div>
      <div className="ev-stat-lbl">{label}</div>
      {sub && <div className="ev-stat-sub">{sub}</div>}
    </div>
  );
}


// ─── Helpers ──────────────────────────────────────────────────────

function formatInt(n: number): string {
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)}B`;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return n.toLocaleString();
}

function formatMoney(n: number): string {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(0)}K`;
  return `$${Math.round(n).toLocaleString()}`;
}

function formatDate(s: string): string {
  // Tolerate ISO + free-form. ISO yyyy-mm-dd → "MMM d, yyyy".
  try {
    const d = new Date(s);
    if (!isNaN(d.getTime())) {
      return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
    }
  } catch {
    /* fallthrough */
  }
  return s;
}

/**
 * Country code → flag emoji. ISO 3166-1 alpha-2 codes map to two
 * regional indicator symbols (each letter + 0x1F1A5 offset).
 */
function countryFlag(cc: string): string {
  if (!cc || cc.length !== 2) return "🌐";
  const upper = cc.toUpperCase();
  // Map A-Z to regional indicator code points (offset 0x1F1A5).
  // Avoiding spread on a string to keep TS happy without
  // --downlevelIteration on the older target.
  return (
    String.fromCodePoint(upper.charCodeAt(0) + 127397) +
    String.fromCodePoint(upper.charCodeAt(1) + 127397)
  );
}

const COUNTRY_NAMES: Record<string, string> = {
  US: "United States", MX: "Mexico", AR: "Argentina", BR: "Brazil",
  CO: "Colombia", CL: "Chile", PE: "Peru", VE: "Venezuela",
  EC: "Ecuador", BO: "Bolivia", PY: "Paraguay", UY: "Uruguay",
  ES: "Spain", PT: "Portugal", FR: "France", DE: "Germany",
  IT: "Italy", GB: "United Kingdom", NL: "Netherlands", PR: "Puerto Rico",
  DO: "Dominican Rep.", CA: "Canada", JP: "Japan", KR: "Korea",
  AU: "Australia", ZA: "South Africa", IN: "India", CN: "China",
};
function countryName(cc: string): string {
  return COUNTRY_NAMES[cc.toUpperCase()] ?? cc;
}

function buildSpotifySearchUrl(track: string): string {
  return `https://open.spotify.com/search/${encodeURIComponent(track)}`;
}

function tintFor(tier: string): string {
  // Subtle off-white tints behind the recommendation block. Editorial
  // aesthetic — barely-there color, just enough to distinguish from
  // body bg.
  switch (tier) {
    case "BUY": return "#f0f7f0";
    case "PROSPECT": return "#f0f4fa";
    case "WATCH": return "#f5f3ed";
    case "PASS": return "#f5f5f5";
    default: return "#f5f3ed";
  }
}

function recommendationBody(tier: string, ident: Dossier["identity"]): string {
  const lockedNote = (() => {
    const stage = (ident.career_stage ?? "").toLowerCase();
    if (ident.label && (stage === "superstar" || stage === "mainstream")) {
      return ` Currently signed to ${ident.label}; no signing window unless contract status shifts.`;
    }
    return "";
  })();
  switch (tier.toUpperCase()) {
    case "BUY":
      return `Active outreach. Lead profile in this tier — push to PROSPECT pipeline.${lockedNote}`;
    case "PROSPECT":
      return `Schedule a deeper look this week. Strong signals, watching for momentum confirmation.${lockedNote}`;
    case "WATCH":
      return `Re-check quarterly. Holding pattern — signals not yet strong enough to chase.${lockedNote}`;
    case "PASS":
      return `Skip. Not a fit on current criteria.${lockedNote}`;
    default:
      return `Re-check next cycle.${lockedNote}`;
  }
}
