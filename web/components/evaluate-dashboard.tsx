"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronDown, ChevronUp, Info } from "lucide-react";
import { searchArtists } from "@/lib/api";
import { useT, useLanguage } from "@/lib/i18n/context";
import {
  TIER_COLOR,
  countryFlag,
  countryName,
  dimensionDescription,
  dimensionLabel,
  formatDate,
  formatInt,
  formatMoney,
  tintFor,
} from "@/lib/format";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { Dossier } from "@/lib/types";

// What the parent (evaluate.tsx) hands us per artist slot.
type LoadedDossier = {
  artist: string;
  cm_id: number;
  dossier: Dossier;
  rendered_markdown: string;
};

export function EvaluateDashboard({
  primary,
  onContinueInChat,
  onCompare,
  onPickOther,
}: {
  primary: LoadedDossier;
  onContinueInChat: () => void;
  onCompare: () => void;
  // v0.5.3 — "See other matches" callback. When the user picks a
  // different Chartmetric candidate from the panel, the parent
  // (evaluate.tsx) re-runs the pipeline with the new cm_id.
  onPickOther?: (name: string, cmId: number) => void;
}) {
  const t = useT();
  return (
    <div className="evaluate-dashboard">
      <ArtistColumn data={primary} onPickOther={onPickOther} />

      <div className="evaluate-cta-row">
        <button type="button" className="evaluate-btn evaluate-btn-primary" onClick={onContinueInChat}>
          {t("eval.dashboard.continue_in_chat", { artist: primary.artist })}
        </button>
        <button type="button" className="evaluate-btn evaluate-btn-secondary" onClick={onCompare}>
          {t("eval.dashboard.compare")}
        </button>
      </div>
    </div>
  );
}


/**
 * Single-artist column. In single-artist mode this fills the whole
 * page; in compare mode there are two of these side-by-side.
 */
function ArtistColumn({
  data,
  onPickOther,
}: {
  data: LoadedDossier;
  onPickOther?: (name: string, cmId: number) => void;
}) {
  const { dossier } = data;
  const tier = dossier.prospect_score.tier?.toUpperCase() ?? "?";
  const accent = TIER_COLOR[tier] ?? "#1a1a1a";
  return (
    <article className="evaluate-column">
      <Hero data={data} accent={accent} />
      {/* Escape hatch: if Chartmetric returned the wrong artist for the
          query, the user can expand this panel to see the next 9 hits
          and pick a different one without re-typing. */}
      {onPickOther && <OtherMatchesPanel artist={data.artist} onPick={onPickOther} />}
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
      <ContentVelocity velocity={dossier.content_velocity} />
      <Similar similar={dossier.competitive_context?.similar_artists} />
      <Risks risks={dossier.risk_signals} />
      <Recommendation tier={tier} accent={accent} ident={dossier.identity} />
    </article>
  );
}


// v0.5.3 — "See other matches" panel. Collapsed by default with a
// small toggle link sitting right under the hero header. When the
// user opens it the first time, we fire /api/search to fetch the
// top 10 candidates. Subsequent opens reuse the cached list to
// avoid re-hitting Chartmetric. Picking a candidate calls the
// onPick callback so the parent re-runs the pipeline with that
// artist's cm_id.
export function OtherMatchesPanel({
  artist,
  onPick,
}: {
  artist: string;
  onPick: (name: string, cmId: number) => void;
}) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [candidates, setCandidates] = useState<
    Array<{ cm_id: number | null; name: string | null; image_url?: string | null; sp_followers?: number | null; code2?: string | null }>
  >([]);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    if (loaded) return;
    setLoading(true);
    setError(null);
    try {
      const r = await searchArtists(artist, 10);
      if (r.error) {
        setError(r.error);
      } else {
        // Filter to candidates we actually have a cm_id for — the
        // URL fallback occasionally returns a partial record.
        const cs = (r.artists || []).filter((a) => a.cm_id != null);
        setCandidates(
          cs as Array<{
            cm_id: number | null;
            name: string | null;
            image_url?: string | null;
            sp_followers?: number | null;
            code2?: string | null;
          }>,
        );
      }
      setLoaded(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "search failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="ev-other-matches">
      <button
        type="button"
        className="ev-other-matches-toggle"
        onClick={toggle}
        aria-expanded={open}
      >
        {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        {open ? t("eval.dashboard.other_matches_close") : t("eval.dashboard.other_matches_open")}
      </button>
      {open && (
        <div className="ev-other-matches-panel">
          {loading && (
            <div className="ev-other-matches-empty">{t("eval.dashboard.other_matches_loading")}</div>
          )}
          {!loading && error && (
            <div className="ev-other-matches-empty">
              {t("eval.dashboard.other_matches_error", { message: error })}
            </div>
          )}
          {!loading && !error && loaded && candidates.length === 0 && (
            <div className="ev-other-matches-empty">{t("eval.dashboard.other_matches_none")}</div>
          )}
          {!loading && !error && candidates.length > 0 && (
            <ul className="ev-other-matches-list">
              {candidates.map((c) => (
                <li key={c.cm_id ?? c.name}>
                  <button
                    type="button"
                    className="ev-other-matches-row"
                    onClick={() => c.cm_id && c.name && onPick(c.name, c.cm_id)}
                    disabled={!c.cm_id || !c.name}
                  >
                    {c.image_url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img className="ev-other-matches-photo" src={c.image_url} alt="" />
                    ) : (
                      <span className="ev-other-matches-photo ev-other-matches-photo-fallback">
                        {(c.name ?? "?").slice(0, 1).toUpperCase()}
                      </span>
                    )}
                    <span className="ev-other-matches-name">{c.name ?? "—"}</span>
                    {c.code2 && <span className="ev-other-matches-meta">{c.code2}</span>}
                    {c.sp_followers != null && (
                      <span className="ev-other-matches-meta ev-other-matches-meta-num">
                        {formatInt(c.sp_followers)}
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}


// ─── Sections (each renders nothing if its data is empty) ────────────

function Hero({ data, accent }: { data: LoadedDossier; accent: string }) {
  const t = useT();
  const { dossier } = data;
  const ident = dossier.identity;
  const score = dossier.prospect_score;
  const sound = dossier.sound_profile;
  const signing = dossier.signing;
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
      <div className="ev-eyebrow">{t("eval.dashboard.eyebrow")}</div>
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
          {sound && (sound.danceability != null || sound.energy != null || sound.tempo != null) && (
            <div className="ev-sound-profile">
              {t("eval.dashboard.hero.sound_profile.title")}
              {sound.danceability != null && (
                <>
                  {" — "}{t("eval.dashboard.hero.sound_profile.danceability")} <strong>{sound.danceability.toFixed(2)}</strong>
                </>
              )}
              {sound.energy != null && (
                <>
                  {" · "}{t("eval.dashboard.hero.sound_profile.energy")} <strong>{sound.energy.toFixed(2)}</strong>
                </>
              )}
              {sound.tempo != null && (
                <>
                  {" · "}<strong>{Math.round(sound.tempo)}</strong> {t("eval.dashboard.hero.sound_profile.tempo_bpm")}
                </>
              )}
            </div>
          )}
          {/* v0.5.2 redesign — two-row meta with a prominent signing
              pill aligned right of row 1. Trims genres to top 3 so the
              row stays scannable. Stage gets a small label prefix so
              it isn't visually ambiguous with the genre list. */}
          <div className="ev-meta">
            <div className="ev-meta-row1">
              <span className="ev-meta-genres">
                {(ident.genres ?? []).slice(0, 3).join(" · ") || "—"}
              </span>
              {signing?.verified_status ? (
                <SigningPill signing={signing} fallbackLabel={ident.label ?? undefined} />
              ) : ident.label ? (
                <SigningPill
                  signing={{ verified_status: "signed_indie", label_display: ident.label }}
                  fallbackLabel={ident.label}
                />
              ) : null}
            </div>
            {ident.career_stage && (
              <div className="ev-meta-row2">
                <span className="ev-meta-prefix">{t("eval.dashboard.hero.stage_label")}</span>
                <strong>{ident.career_stage}</strong>
                {ident.career_trend && <span className="ev-meta-trend">{" / "}{ident.career_trend}</span>}
              </div>
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
            {t("eval.dashboard.confidence_prefix")} {Math.round(score.confidence * 100)}%
            {score.data_completeness != null && (
              ` · ${t("eval.dashboard.data_complete_label")} ${Math.round(score.data_completeness * 100)}% ${t("eval.dashboard.data_complete_suffix")}`
            )}
          </div>
        </div>
      </div>
    </header>
  );
}


function Reach({ metrics }: { metrics: Dossier["metrics"] }) {
  const t = useT();
  const sp = metrics.spotify ?? {};
  const yt = metrics.youtube ?? {};
  const ig = metrics.instagram ?? {};
  const tt = metrics.tiktok ?? {};
  const other = metrics.other ?? {};
  const popularity = sp.popularity;

  // v0.5.3 — split into two narratives:
  //   Group A (plays): YouTube views + Spotify monthly listeners.
  //   Group B (audience): Instagram / TikTok / YouTube subs / Spotify followers.
  // Both groups live in the SAME 4-column grid so the cell edges
  // align vertically — the plays row uses span-2 tiles so its
  // featured numbers read bigger without breaking column alignment.
  // Spotify popularity + Shazam / Deezer / SoundCloud move to the
  // secondary chip row: they're either derived scores or follower-
  // shaped counts that don't deserve a hero tile of their own.
  // CPP dropped from Reach — it's a Chartmetric composite score,
  // not a Reach metric.
  return (
    <section className="ev-section">
      <h2 className="ev-h2">{t("eval.dashboard.reach")}</h2>
      <div className="ev-reach-grid">
        <h3 className="ev-h3 ev-reach-group-header">{t("eval.dashboard.reach.plays_title")}</h3>
        <Stat
          big={yt.views ? formatInt(yt.views) : "—"}
          label={t("eval.dashboard.reach.yt_views")}
          sub={t("eval.dashboard.reach.yt_views_sub")}
        />
        <Stat
          big={sp.monthly_listeners ? formatInt(sp.monthly_listeners) : "—"}
          label={t("eval.dashboard.reach.sp_listeners")}
          sub={[
            t("eval.dashboard.reach.sp_listeners_sub"),
            sp.monthly_listeners_change ?? null,
          ].filter(Boolean).join(" · ") || undefined}
        />
        {/* Cols 3 + 4 of the plays row stay empty on purpose — keeps
            YouTube views above Instagram and Spotify listeners above
            TikTok. */}
        <div className="ev-reach-spacer" aria-hidden="true" />
        <div className="ev-reach-spacer" aria-hidden="true" />
        <h3 className="ev-h3 ev-reach-group-header ev-reach-group-header-spaced">
          {t("eval.dashboard.reach.audience_title")}
        </h3>
        <Stat
          big={ig.followers ? formatInt(ig.followers) : "—"}
          label={t("eval.dashboard.reach.instagram")}
          sub={ig.engagement_rate ? `${ig.engagement_rate} ${t("eval.dashboard.reach.engagement_suffix")}` : undefined}
        />
        <Stat
          big={tt.followers ? formatInt(tt.followers) : "—"}
          label={t("eval.dashboard.reach.tiktok")}
          sub={tt.likes ? `${formatInt(tt.likes)} ${t("eval.dashboard.reach.likes_suffix")}` : t("eval.dashboard.reach.no_data")}
        />
        <Stat
          big={yt.subscribers ? formatInt(yt.subscribers) : "—"}
          label={t("eval.dashboard.reach.youtube_subs")}
        />
        <Stat
          big={sp.followers ? formatInt(sp.followers) : "—"}
          label={t("eval.dashboard.reach.sp_followers")}
        />
      </div>
      {(other.shazam_count || other.deezer_fans || other.soundcloud_followers || popularity != null) && (
        <TooltipProvider delay={0}>
        <div className="ev-secondary-row">
          {other.shazam_count != null && (
            <ReachChip
              label={t("eval.dashboard.reach.shazam")}
              value={formatInt(other.shazam_count)}
              info={t("eval.dashboard.reach.shazam.info")}
            />
          )}
          {other.deezer_fans != null && (
            <ReachChip
              label={t("eval.dashboard.reach.deezer")}
              value={formatInt(other.deezer_fans)}
              info={t("eval.dashboard.reach.deezer.info")}
            />
          )}
          {other.soundcloud_followers != null && (
            <ReachChip
              label={t("eval.dashboard.reach.soundcloud")}
              value={formatInt(other.soundcloud_followers)}
              info={t("eval.dashboard.reach.soundcloud.info")}
            />
          )}
          {popularity != null && (
            <ReachChip
              label={t("eval.dashboard.reach.spotify_pop")}
              value={`${popularity}/100`}
              info={t("eval.dashboard.reach.spotify_pop.info")}
            />
          )}
        </div>
        </TooltipProvider>
      )}
      <div className="ev-source">{t("eval.dashboard.source.reach")}</div>
    </section>
  );
}


function Revenue({ revenue }: { revenue: Dossier["revenue_projection"] }) {
  const t = useT();
  if (!revenue || revenue.note || !revenue.annual_projected) return null;
  const annual = revenue.annual_projected;
  // Same lo/hi multipliers the dossier_renderer uses for HIGH confidence.
  // Approximation since we don't have the artist_data here for the
  // confidence calc — use a wider band by default (0.6x – 1.7x).
  const lo = annual * 0.6;
  const hi = annual * 1.7;
  // Monthly gross is annual ÷ 12 (not `monthly_total` from the backend,
  // which is pre-growth-factor — the three numbers would no longer add
  // up consistently). The annual figure is what the user sees first, so
  // monthly + Faro share are derived from it for honesty.
  const monthly = annual / 12;
  // Artist / Faro split sourced from config/revenue_share.yaml via the
  // dossier. Falls back to 70/30 if the backend didn't attach it (e.g.
  // older overlay still in the wild).
  const share = revenue.share ?? { artist_pct: 0.70, faro_pct: 0.30 };
  const faroMonthly = monthly * share.faro_pct;
  const artistMonthly = monthly * share.artist_pct;
  const faroPctLabel = Math.round(share.faro_pct * 100);
  const artistPctLabel = Math.round(share.artist_pct * 100);
  const byPlatform = revenue.monthly_revenue_by_platform ?? {};
  const byPlatformAnnual: Array<[string, number]> = Object.entries(byPlatform)
    .map(([k, v]) => [k, (v ?? 0) * 12] as [string, number])
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1]);
  const totalAnnual = byPlatformAnnual.reduce((s, [, v]) => s + v, 0);

  return (
    <section className="ev-section">
      <h2 className="ev-h2">{t("eval.dashboard.revenue")}</h2>
      <div className="ev-revenue-grid ev-revenue-grid-3">
        <Stat
          big={formatMoney(annual)}
          label={t("eval.dashboard.revenue.annual_gross")}
          sub={t("eval.dashboard.revenue.range", { lo: formatMoney(lo), hi: formatMoney(hi) })}
        />
        <Stat
          big={formatMoney(monthly)}
          label={t("eval.dashboard.revenue.monthly_gross")}
          sub={t("eval.dashboard.revenue.monthly_gross_sub")}
        />
        <Stat
          big={formatMoney(faroMonthly)}
          label={t("eval.dashboard.revenue.faro_share", { pct: faroPctLabel })}
          sub={t("eval.dashboard.revenue.artist_share_sub", {
            pct: artistPctLabel,
            amount: formatMoney(artistMonthly),
          })}
        />
      </div>
      {byPlatformAnnual.length > 0 && totalAnnual > 0 && (
        <>
          <div className="ev-rev-platform-title">{t("eval.dashboard.revenue.per_platform_title")}</div>
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
      <div className="ev-source">{t("eval.dashboard.source.revenue", { file: "mcp_server/tools/revenue_model.py" })}</div>
    </section>
  );
}


function Scoring({ score }: { score: Dossier["prospect_score"] }) {
  const t = useT();
  const dims = score.dimensions ?? {};
  // Sort by score descending — strongest first, matches narrative.
  const rows = Object.entries(dims).sort((a, b) => b[1].score - a[1].score);
  const [openName, setOpenName] = useState<string | null>(null);

  if (rows.length === 0) return null;

  return (
    <TooltipProvider delay={0}>
    <section className="ev-section">
      <h2 className="ev-h2">{t("eval.dashboard.scoring")}</h2>
      {/* Column headers — without these, the trailing "85%" / "20%"
          numbers each row ends with read as random noise. Each header
          now carries a tooltip with the same prose that used to live
          in the legend block below the table, so the explanation is
          reachable from the column the user is actually looking at. */}
      <div className="ev-row ev-row-headers">
        <ScoringHeaderCell t={t} className="ev-row-label" headerKey="dimension" />
        <div />
        <ScoringHeaderCell t={t} className="ev-num-mono" headerKey="score" />
        <ScoringHeaderCell t={t} className="ev-num-mono" headerKey="confidence" />
        <ScoringHeaderCell t={t} className="ev-num-mono" headerKey="weight" />
      </div>
      {rows.map(([name, d]) => {
        const label = dimensionLabel(t, name);
        const description = dimensionDescription(t, name);
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
              <div className="ev-row-label">
                <span className="ev-row-label-text">{label}</span>
                {description && (
                  <Tooltip>
                    {/* `render={<span ... />}` makes base-ui render the
                        trigger as a span instead of its default button —
                        crucial here, because we're already inside a
                        <button className="ev-row-clickable"> and nested
                        buttons are invalid HTML. stopPropagation keeps
                        the icon's click from toggling the row's rationale. */}
                    <TooltipTrigger
                      delay={0}
                      render={
                        <span
                          role="img"
                          tabIndex={0}
                          aria-label={t("eval.dashboard.scoring.info_aria")}
                          className="ev-row-info"
                          onClick={(e: React.MouseEvent) => e.stopPropagation()}
                        />
                      }
                    >
                      <Info size={13} strokeWidth={1.75} />
                    </TooltipTrigger>
                    <TooltipContent>{description}</TooltipContent>
                  </Tooltip>
                )}
              </div>
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
      <div className="ev-help">{t("eval.dashboard.scoring.click_hint")}</div>
      <div className="ev-source">{t("eval.dashboard.source.scoring", { profile: "default", file: "config/profiles.yaml" })}</div>
    </section>
    </TooltipProvider>
  );
}

// One column header. The visible label is the existing translated
// string; the tooltip body comes from the same key family the legend
// used pre-v0.5.3, just attached to the header so the explanation
// is reachable from where the column lives.
function ScoringHeaderCell({
  t,
  className,
  headerKey,
}: {
  t: (key: string, vars?: Record<string, string | number>) => string;
  className: string;
  headerKey: "dimension" | "score" | "confidence" | "weight";
}) {
  return (
    <Tooltip>
      {/* Same render-as-span trick as the info icon — the headers
          live inside `.ev-row` (a grid) and don't need to be buttons. */}
      <TooltipTrigger
        delay={0}
        render={
          <span
            tabIndex={0}
            className={className + " ev-row-header-trigger"}
          />
        }
      >
        {t(`eval.dashboard.scoring.col.${headerKey}`)}
      </TooltipTrigger>
      <TooltipContent>
        {t(`eval.dashboard.scoring.col.${headerKey}.tooltip`)}
      </TooltipContent>
    </Tooltip>
  );
}


function Markets({ markets }: { markets?: Dossier["geographic_profile"] extends infer T ? T extends { top_markets?: infer U } ? U : never : never }) {
  const t = useT();
  if (!markets || markets.length === 0) return null;
  const max = Math.max(...markets.map((m) => m.listeners ?? 0));
  return (
    <section className="ev-section">
      <h2 className="ev-h2">{t("eval.dashboard.markets")}</h2>
      <div className="ev-row ev-market-row ev-row-headers" aria-hidden="true">
        <span />
        <div />
        <div />
        <div className="ev-num-mono">{t("eval.dashboard.markets.col.listeners")}</div>
        <div className="ev-num-mono">{t("eval.dashboard.markets.col.delta")}</div>
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
      <div className="ev-legend">{t("eval.dashboard.markets.legend")}</div>
      <div className="ev-source">{t("eval.dashboard.source.markets")}</div>
    </section>
  );
}


function Milestones({ milestones }: { milestones?: Array<{ text: string; date?: string; platform?: string }> }) {
  const t = useT();
  const { lang } = useLanguage();
  if (!milestones || milestones.length === 0) return null;
  return (
    <section className="ev-section">
      <h2 className="ev-h2">{t("eval.dashboard.milestones")}</h2>
      <div className="ev-milestones">
        {milestones.slice(0, 5).map((m, i) => (
          <div key={i} className="ev-milestone-row">
            <span className="ev-milestone-date">{m.date ? formatDate(m.date, lang) : "—"}</span>
            <span className="ev-milestone-text">{m.text}</span>
            {m.platform && <span className="ev-milestone-platform">{m.platform}</span>}
          </div>
        ))}
      </div>
      <div className="ev-source">{t("eval.dashboard.source.milestones")}</div>
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
  const t = useT();
  const { lang } = useLanguage();
  if (!catalog) return null;
  const r6 = catalog.releases_6m ?? 0;
  const r12 = catalog.releases_12m ?? 0;
  const total = catalog.total_tracks ?? 0;
  const editorial = catalog.editorial_playlists ?? 0;
  const tracks = catalog.latest_tracks ?? [];
  const topTracks = catalog.top_tracks ?? [];
  const spotifyArtistUrl = urls?.spotify;

  return (
    <section className="ev-section">
      <h2 className="ev-h2">{t("eval.dashboard.catalog")}</h2>
      <div className="ev-catalog-stats">
        {t("eval.dashboard.catalog.summary", { r6, r12, total })}
        {editorial > 0 && (<> · <strong>{editorial}</strong> {t("eval.dashboard.catalog.editorial_suffix")}</>)}
      </div>
      {tracks.length > 0 && (
        <>
          <div className="ev-catalog-subtitle">{t("eval.dashboard.catalog.latest_releases")}</div>
          {tracks.slice(0, 5).map((tr, i) => {
            const trackUrl = spotifyArtistUrl ? buildSpotifySearchUrl(tr.name) : null;
            return (
              <div key={i} className="ev-track-row">
                {trackUrl ? (
                  <a href={trackUrl} target="_blank" rel="noopener noreferrer" className="ev-track-link">
                    {tr.name}<span className="ev-social-arrow">↗</span>
                  </a>
                ) : (
                  <span className="ev-track-name">{tr.name}</span>
                )}
                <span className="ev-track-date">{tr.release_date ? formatDate(tr.release_date, lang) : ""}</span>
              </div>
            );
          })}
        </>
      )}
      {topTracks.length > 0 && (
        <>
          <div className="ev-catalog-subtitle">{t("eval.dashboard.catalog.top_tracks_title")}</div>
          {topTracks.slice(0, 5).map((tr, i) => {
            const trackUrl = spotifyArtistUrl ? buildSpotifySearchUrl(tr.name) : null;
            const pop = tr.popularity ?? 0;
            return (
              <div key={i} className="ev-row ev-track-stats-row">
                {trackUrl ? (
                  <a href={trackUrl} target="_blank" rel="noopener noreferrer" className="ev-track-link">
                    {tr.name}<span className="ev-social-arrow">↗</span>
                  </a>
                ) : (
                  <span className="ev-track-name">{tr.name}</span>
                )}
                <span className="ev-track-date">{tr.release_date ? formatDate(tr.release_date, lang) : ""}</span>
                <div className="ev-bar"><span style={{ width: `${Math.min(100, pop)}%` }} /></div>
                <div className="ev-num-mono">{pop}/100</div>
              </div>
            );
          })}
          <div className="ev-help">{t("eval.dashboard.catalog.popularity_label")}</div>
        </>
      )}
      <div className="ev-source">{t("eval.dashboard.source.catalog")}</div>
    </section>
  );
}


function ContentVelocity({ velocity }: { velocity?: Dossier["content_velocity"] }) {
  const t = useT();
  if (!velocity) return null;
  const sp = velocity.spotify;
  const yt = velocity.youtube;
  if (!sp && !yt) return null;

  const trendLabel = (
    trend: "accelerating" | "steady" | "decelerating" | null | undefined,
  ): string => (trend ? t(`eval.dashboard.catalog.trend.${trend}`) : "—");

  return (
    <section className="ev-section">
      <h2 className="ev-h2">{t("eval.dashboard.content_velocity")}</h2>
      <div className="ev-content-velocity">
        {sp && (
          <div className="ev-velocity-block">
            <div className="ev-velocity-subhead">{t("eval.dashboard.content_velocity.spotify")}</div>
            {sp.days_since_latest != null && (
              <div className="ev-velocity-row">
                <span className="ev-velocity-label">{t("eval.dashboard.content_velocity.last_release")}</span>
                <strong>{t("eval.dashboard.content_velocity.days_ago", { n: sp.days_since_latest })}</strong>
              </div>
            )}
            {sp.cadence_days != null && (
              <div className="ev-velocity-row">
                <span className="ev-velocity-label">{t("eval.dashboard.content_velocity.cadence")}</span>
                <strong>
                  {t("eval.dashboard.content_velocity.cadence_value", {
                    days: sp.cadence_days,
                    trend: trendLabel(sp.trend),
                  })}
                </strong>
              </div>
            )}
          </div>
        )}
        {yt && (
          <div className="ev-velocity-block">
            <div className="ev-velocity-subhead">{t("eval.dashboard.content_velocity.youtube")}</div>
            {yt.days_since_latest != null && (
              <div className="ev-velocity-row">
                <span className="ev-velocity-label">{t("eval.dashboard.content_velocity.last_upload")}</span>
                <strong>{t("eval.dashboard.content_velocity.days_ago", { n: yt.days_since_latest })}</strong>
              </div>
            )}
            {yt.cadence_days != null && (
              <div className="ev-velocity-row">
                <span className="ev-velocity-label">{t("eval.dashboard.content_velocity.cadence")}</span>
                <strong>
                  {t("eval.dashboard.content_velocity.cadence_value", {
                    days: yt.cadence_days,
                    trend: trendLabel(yt.trend),
                  })}
                </strong>
              </div>
            )}
            {(yt.avg_views_recent_3 != null
              || yt.avg_like_ratio_pct != null
              || yt.avg_comments_per_view_pct != null) && (
              <div className="ev-velocity-scope">
                {t("eval.dashboard.content_velocity.recent3_scope")}
              </div>
            )}
            {yt.avg_views_recent_3 != null && (
              <div className="ev-velocity-row">
                <span className="ev-velocity-label">{t("eval.dashboard.content_velocity.avg_views")}</span>
                <strong>{formatInt(yt.avg_views_recent_3)}</strong>
              </div>
            )}
            {yt.avg_like_ratio_pct != null && (
              <div className="ev-velocity-row">
                <span className="ev-velocity-label">{t("eval.dashboard.content_velocity.like_ratio")}</span>
                <strong>{yt.avg_like_ratio_pct.toFixed(1)}%</strong>
              </div>
            )}
            {yt.avg_comments_per_view_pct != null && (
              <div className="ev-velocity-row">
                <span className="ev-velocity-label">{t("eval.dashboard.content_velocity.comments_per_view")}</span>
                <strong>{yt.avg_comments_per_view_pct.toFixed(2)}%</strong>
              </div>
            )}
          </div>
        )}
      </div>
      {/* v0.5.2 — top videos by lifetime views, rendered below the
          two-column cadence block. Shows the artist's biggest hits on
          YouTube, distinct from the latest-uploads view above. */}
      {yt && yt.top_videos && yt.top_videos.length > 0 && (
        <div className="ev-top-videos">
          <div className="ev-velocity-subhead">
            {t("eval.dashboard.content_velocity.top_videos_title")}
          </div>
          {yt.top_videos.slice(0, 3).map((v) => (
            <a
              key={v.id}
              href={v.url ?? `https://www.youtube.com/watch?v=${v.id}`}
              target="_blank"
              rel="noopener noreferrer"
              className="ev-top-videos-row"
            >
              {v.thumbnail_url ? (
                <img
                  className="ev-top-video-thumb"
                  src={v.thumbnail_url}
                  alt={v.title}
                  loading="lazy"
                />
              ) : (
                <div className="ev-top-video-thumb ev-top-video-thumb-fallback" />
              )}
              <div className="ev-top-video-title">{v.title}</div>
              <div className="ev-num-mono">{formatInt(v.view_count)}</div>
            </a>
          ))}
        </div>
      )}
      <div className="ev-source">{t("eval.dashboard.source.content_velocity")}</div>
    </section>
  );
}


function Similar({ similar }: { similar?: Dossier["competitive_context"] extends infer T ? T extends { similar_artists?: infer U } ? U : never : never }) {
  const t = useT();
  const router = useRouter();
  if (!similar || similar.length === 0) return null;
  return (
    <section className="ev-section">
      <h2 className="ev-h2">{t("eval.dashboard.similar")}</h2>
      <div className="ev-similar-grid">
        {similar.slice(0, 6).map((s, i) => {
          const initials = s.name
            .split(" ")
            .filter(Boolean)
            .slice(0, 2)
            .map((p) => p[0]?.toUpperCase() ?? "")
            .join("") || "?";
          return (
            <button
              key={i}
              type="button"
              className="ev-similar-card ev-similar-card-clickable"
              onClick={() => {
                // Navigate to /evaluate with the artist name in URL — page
                // re-mounts and runs the evaluation. Simpler than passing
                // state through a query param: just trigger a fresh search.
                router.push(`/evaluate?artist=${encodeURIComponent(s.name)}`);
                // Fallback: if the page doesn't re-mount on same-route nav,
                // dispatch a custom event the page can listen for.
                window.dispatchEvent(new CustomEvent("faroai-evaluate-artist", { detail: { name: s.name } }));
              }}
              aria-label={`${t("eval.dashboard.similar.evaluate_btn")} — ${s.name}`}
            >
              {s.image_url ? (
                <img
                  src={s.image_url}
                  alt={s.name}
                  className="ev-similar-photo"
                  onError={(e) => {
                    const target = e.currentTarget;
                    const fallback = document.createElement("div");
                    fallback.className = "ev-similar-photo ev-similar-photo-fallback";
                    fallback.textContent = initials;
                    target.replaceWith(fallback);
                  }}
                />
              ) : (
                <div className="ev-similar-photo ev-similar-photo-fallback">{initials}</div>
              )}
              <div className="ev-similar-name">{s.name}</div>
              <span className="ev-similar-link">{t("eval.dashboard.similar.evaluate_btn")}</span>
            </button>
          );
        })}
      </div>
      <div className="ev-source">{t("eval.dashboard.source.similar")}</div>
    </section>
  );
}


function Risks({ risks }: { risks?: Record<string, string> }) {
  const t = useT();
  if (!risks) return null;
  const flagged = Object.entries(risks).filter(([, v]) => v && v !== "N/A" && v.trim() !== "");
  if (flagged.length === 0) return null;
  return (
    <section className="ev-section">
      <h2 className="ev-h2">{t("eval.dashboard.risks")}</h2>
      {flagged.map(([k, v]) => (
        <div key={k} className="ev-risk-row">
          <span className="ev-risk-warn">⚠</span>
          <strong>{k.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase())}</strong> — {v}
        </div>
      ))}
      <div className="ev-source">{t("eval.dashboard.source.risks")}</div>
    </section>
  );
}


function Recommendation({ tier, accent, ident }: { tier: string; accent: string; ident: Dossier["identity"] }) {
  const t = useT();
  const body = recommendationBody(tier, ident, t);
  return (
    <section className="ev-section">
      <h2 className="ev-h2">{t("eval.dashboard.recommendation")}</h2>
      <div className="ev-reco" style={{ borderLeftColor: accent, background: tintFor(tier) }}>
        <div className="ev-reco-tier" style={{ color: accent }}>{tier}</div>
        <div className="ev-reco-body">{body}</div>
      </div>
    </section>
  );
}


// ─── Reusable bits ────────────────────────────────────────────────

// Small chip in the Reach secondary row (Shazam / Deezer / SoundCloud
// / Spotify popularity). Each chip is its own tooltip trigger so the
// user can hover the platform name to see what the number actually
// means — these metrics are non-obvious (Shazam isn't a follow count,
// popularity isn't streams, etc.).
function ReachChip({
  label,
  value,
  info,
}: {
  label: string;
  value: string;
  info: string;
}) {
  return (
    <Tooltip>
      <TooltipTrigger
        delay={0}
        render={<span tabIndex={0} className="ev-reach-chip" />}
      >
        <span className="ev-reach-chip-label">{label}</span>{" "}
        <strong>{value}</strong>
        <Info size={11} strokeWidth={1.75} className="ev-reach-chip-info" />
      </TooltipTrigger>
      <TooltipContent>{info}</TooltipContent>
    </Tooltip>
  );
}


function Stat({
  big,
  label,
  sub,
  className,
}: {
  big: string;
  label: string;
  sub?: string;
  className?: string;
}) {
  return (
    <div className={className ? `ev-stat ${className}` : "ev-stat"}>
      <div className="ev-stat-num">{big}</div>
      <div className="ev-stat-lbl">{label}</div>
      {sub && <div className="ev-stat-sub">{sub}</div>}
    </div>
  );
}


function SigningPill({
  signing,
  fallbackLabel,
}: {
  signing: NonNullable<Dossier["signing"]>;
  fallbackLabel?: string;
}) {
  const t = useT();
  const labelText = signing.label_display || fallbackLabel || "—";
  const tooltip = (signing.evidence ?? []).join(" · ");
  const status = signing.verified_status;
  const isWarn = signing.discrepancy;

  // Pick variant class for color-tinted background. "warn" overrides
  // all when Chartmetric and label evidence disagree.
  let variant = "unknown";
  if (isWarn) variant = "warn";
  else if (status === "signed_major") variant = "major";
  else if (status === "signed_indie") variant = "indie";
  else if (status === "self_released") variant = "self";

  // Compact two-token form: "STATUS · Label", where STATUS is the
  // uppercase keyword. Discrepancy adds a leading ⚠️.
  let statusWord: string;
  if (isWarn) statusWord = `⚠ ${t("eval.dashboard.hero.signing.unclear")}`;
  else if (status === "signed_major") statusWord = t("eval.dashboard.hero.signing.signed");
  else if (status === "signed_indie") statusWord = t("eval.dashboard.hero.signing.indie");
  else if (status === "self_released") statusWord = t("eval.dashboard.hero.signing.self_released");
  else statusWord = t("eval.dashboard.hero.signing.unknown");

  // For self-released / unknown there's no meaningful label to append.
  const showLabel = status !== "self_released" && status !== "unknown";

  return (
    <span
      className={`ev-signing-pill ev-signing-pill-${variant}`}
      title={tooltip || undefined}
    >
      <span className="ev-signing-pill-status">{statusWord.toUpperCase()}</span>
      {showLabel && (
        <>
          <span className="ev-signing-pill-sep">·</span>
          <span className="ev-signing-pill-label">{labelText}</span>
        </>
      )}
      {status === "signed_major" && !isWarn && (
        <span className="ev-signing-pill-check" aria-hidden="true">✓</span>
      )}
    </span>
  );
}


// ─── Helpers ──────────────────────────────────────────────────────
// Most formatters moved to web/lib/format.ts in v0.5.2 so /compare
// can re-use them. Only file-local helpers stay here.

function buildSpotifySearchUrl(track: string): string {
  return `https://open.spotify.com/search/${encodeURIComponent(track)}`;
}

function recommendationBody(
  tier: string,
  ident: Dossier["identity"],
  t: (key: string, vars?: Record<string, string | number>) => string,
): string {
  const lockedNote = (() => {
    const stage = (ident.career_stage ?? "").toLowerCase();
    if (ident.label && (stage === "superstar" || stage === "mainstream")) {
      return t("eval.dashboard.reco.locked_suffix", { label: ident.label });
    }
    return "";
  })();
  let key: string;
  switch (tier.toUpperCase()) {
    case "BUY": key = "eval.dashboard.reco.buy"; break;
    case "PROSPECT": key = "eval.dashboard.reco.prospect"; break;
    case "WATCH": key = "eval.dashboard.reco.watch"; break;
    case "PASS": key = "eval.dashboard.reco.pass"; break;
    default: key = "eval.dashboard.reco.default"; break;
  }
  return `${t(key)}${lockedNote}`;
}
