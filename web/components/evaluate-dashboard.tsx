"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useT, useLanguage } from "@/lib/i18n/context";
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
  const t = useT();
  return (
    <div className="evaluate-dashboard">
      <ArtistColumn data={primary} />

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
      <ContentVelocity velocity={dossier.content_velocity} />
      <Similar similar={dossier.competitive_context?.similar_artists} />
      <Risks risks={dossier.risk_signals} />
      <Recommendation tier={tier} accent={accent} ident={dossier.identity} />
    </article>
  );
}


// ─── Sections (each renders nothing if its data is empty) ────────────

function Hero({ data, accent }: { data: LoadedDossier; accent: string }) {
  const t = useT();
  const { dossier } = data;
  const ident = dossier.identity;
  const score = dossier.prospect_score;
  const sound = dossier.sound_profile;
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
  const cpp = metrics.cpp_score;
  const popularity = sp.popularity;

  return (
    <section className="ev-section">
      <h2 className="ev-h2">{t("eval.dashboard.reach")}</h2>
      <div className="ev-grid-4">
        <Stat
          big={sp.monthly_listeners ? formatInt(sp.monthly_listeners) : "—"}
          label={t("eval.dashboard.reach.spotify_monthly")}
          sub={[
            sp.monthly_listeners_change ?? null,
            sp.followers ? `${formatInt(sp.followers)} ${t("eval.dashboard.reach.followers_suffix")}` : null,
          ].filter(Boolean).join(" · ") || undefined}
        />
        <Stat
          big={yt.subscribers ? formatInt(yt.subscribers) : "—"}
          label={t("eval.dashboard.reach.youtube_subs")}
          sub={yt.views ? t("eval.dashboard.reach.youtube_total_views", { n: formatInt(yt.views) }) : undefined}
        />
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
      </div>
      {(other.shazam_count || other.deezer_fans || other.soundcloud_followers || popularity || cpp) && (
        <div className="ev-secondary-row">
          {other.shazam_count != null && <span>Shazam <strong>{formatInt(other.shazam_count)}</strong></span>}
          {other.deezer_fans != null && <span>Deezer <strong>{formatInt(other.deezer_fans)}</strong></span>}
          {other.soundcloud_followers != null && <span>SoundCloud <strong>{formatInt(other.soundcloud_followers)}</strong></span>}
          {popularity != null && <span>{t("eval.dashboard.reach.spotify_pop")} <strong>{popularity}/100</strong></span>}
          {cpp != null && <span>{t("eval.dashboard.reach.cpp")} <strong>{cpp.toFixed(2)}</strong></span>}
        </div>
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
      <h2 className="ev-h2">{t("eval.dashboard.revenue")}</h2>
      <div className="ev-revenue-grid">
        <Stat
          big={formatMoney(annual)}
          label={t("eval.dashboard.revenue.annual_gross")}
          sub={t("eval.dashboard.revenue.range", { lo: formatMoney(lo), hi: formatMoney(hi) })}
        />
        <Stat
          big={formatMoney(distributor)}
          label={t("eval.dashboard.revenue.distributor_cut")}
          sub={t("eval.dashboard.revenue.artist_payout", { amount: formatMoney(artist) })}
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
    <section className="ev-section">
      <h2 className="ev-h2">{t("eval.dashboard.scoring")}</h2>
      {/* Column headers — without these, the trailing "85%" / "20%"
          numbers each row ends with read as random noise. Spelling
          "Confidence" and "Weight" out costs one line and removes a
          chunk of cognitive load. */}
      <div className="ev-row ev-row-headers" aria-hidden="true">
        <div className="ev-row-label">{t("eval.dashboard.scoring.col.dimension")}</div>
        <div />
        <div className="ev-num-mono">{t("eval.dashboard.scoring.col.score")}</div>
        <div className="ev-num-mono">{t("eval.dashboard.scoring.col.confidence")}</div>
        <div className="ev-num-mono">{t("eval.dashboard.scoring.col.weight")}</div>
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
        <strong>{t("eval.dashboard.scoring.legend.score")}</strong> — {t("eval.dashboard.scoring.legend.score_desc")}{" "}
        <strong>{t("eval.dashboard.scoring.legend.confidence")}</strong> — {t("eval.dashboard.scoring.legend.confidence_desc")}{" "}
        <strong>{t("eval.dashboard.scoring.legend.weight")}</strong> — {t("eval.dashboard.scoring.legend.weight_desc")}
      </div>
      <div className="ev-help">{t("eval.dashboard.scoring.click_hint")}</div>
      <div className="ev-source">{t("eval.dashboard.source.scoring", { profile: "default", file: "config/profiles.yaml" })}</div>
    </section>
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
              <div className="ev-num-mono">
                {v.like_ratio != null ? `${v.like_ratio.toFixed(1)}%` : "—"}
              </div>
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

function formatDate(s: string, lang: string = "en"): string {
  // Tolerate ISO + free-form. ISO yyyy-mm-dd → "MMM d, yyyy" / "d MMM yyyy".
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
