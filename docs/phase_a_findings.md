# Phase A findings — 2026-04-28

First end-to-end Mode 2 run on real Chartmetric data, against the three reference profiles (Feid, Ryan Castro, Blessd). The CLI [scripts/evaluate_artist.py](../scripts/evaluate_artist.py) wires `compute_prospect_score` → `estimate_revenue` → `generate_dossier` → `route_alert` on top of the saved profiles.

Headline scores (default profile):

| Artist | Score | Tier | Notable |
|---|---|---|---|
| Feid (cm_id 152776) | 61.4 | WATCH | Superstar/steady → timing capped at 10 |
| Ryan Castro (cm_id 1045417) | 71.7 | WARM | Same timing cap; momentum higher |
| Blessd (cm_id 1776209) | 66.0 | WATCH | Same |

All three are classified by Chartmetric as `career_stage = "superstar"`, which the timing scorer treats as "window has closed" (score = 10). That assumption is **A&R-correct** for FaroLatino's distribution-acquisition use case — they should not score signed superstars highly. But it suppresses score variance across the three artists, so this set isn't a useful calibration corpus on its own. Need at least one **rising** artist (career_stage = "rising" or "developing") for Phase C tuning.

---

## Hard failures (fixed inline in `evaluate_artist.py` adapter)

- **`Insight.__init__()` got an unexpected keyword argument 'platform'** (all three artists). The collection-layer builder `_build_noteworthy_insights` ([chartmetric_artist.py:_build_noteworthy_insights](../mcp_server/tools/chartmetric_artist.py)) emits `{type, platform, date, text}` but the `Insight` dataclass ([models/artist.py:74-80](../mcp_server/models/artist.py#L74-L80)) accepts `{text, type, date, metric, value}`. Phase A workaround: `_DATACLASS_FIELD_WHITELIST` in `evaluate_artist.py` strips unknown keys before `build_artist()`. **Phase C decision needed:** drop `platform` from the builder, or extend `Insight` to include `platform` (and `value` since the API returns it). The builder also doesn't extract `metric` / `value` from the live response even though both fields are present.

## Data-collection gaps surfaced (defer to Phase C / new fetcher work)

- **`neighboring_artists` is empty for all 3 artists.** The endpoint payload at [data/cache/{cm_id}/neighboring.json](../data/cache/152776/neighboring.json) is `{"data": []}` for Feid, Ryan Castro, and Blessd. Either: (a) the response shape doesn't match what `_fetch_neighboring_artists` expects (it looks for `obj.cluster_artists`), (b) the endpoint requires different query params, or (c) the endpoint is genuinely empty. **Action:** hit the endpoint live with curl and see what comes back. This affects D4 Timing (uses `neighboring_artists`) and the Dossier `competitive_context.similar_artists` section.

- **`editorial_playlists` is always 0.** All `profile.playlists[].is_editorial` flags are `False` because Chartmetric's `/spotify/current/playlists` endpoint returns user-curated playlists by default. To get editorial placements, the fetcher likely needs a different param or a different endpoint (e.g., `/spotify/playlists?editorial=true`). This affects D4 Timing (Editorial Playlist Add signal) and the Alert Router's "Editorial Playlist Add" signal.

- **`tracks[].release_date` includes future-scheduled releases.** Ryan Castro's "Last release: -10 days ago" suggests a release date in the future. Chartmetric returns scheduled releases as part of the catalog. `_count_recent_releases` should filter to `release_date <= today` to avoid inflating the velocity score. Minor.

## Score quality issues (defer to Phase C)

- **D1 Momentum feels low.** Feid scored 20.3 ("Avg cross-platform growth: +1.4%/month"); Blessd 31.4 ("+0.9%/month"). For artists pulling 25-37M monthly Spotify listeners, this looks too punishing. Likely the scorer treats ~1%/month as basically flat, but for an artist already at the ceiling, +1%/month *is* growth. Worth re-examining the score-vs-growth curve in [d1_momentum.py](../mcp_server/tools/scoring/d1_momentum.py).

- **D4 Timing capped at 10 for all "superstar" career_stage values.** This is the dominant reason the three artists cluster in the 60s-low-70s range. The cap is *intentionally* harsh for superstars (the A&R thesis: don't score signed superstars highly). Revisit only if the rising-artist set in a future calibration run produces too-low scores; the asymmetry might still be correct.

- **Revenue projection of $13M-18M/year for all three.** Feels plausibly high. The CPMs in [config/cpm_rates.yaml](../config/cpm_rates.yaml) carry the `"Uses placeholder CPMs — recalibrate with FaroLatino actuals"` warning. Specifically for distribution revenue (FaroLatino's actual margin), divide by ~10x. **Action item with Julio:** get FaroLatino's actual per-stream rate by platform/region.

- **D2 Geographic Fit growth bonus only fires partially.** Feid: "0 target market(s) growing." Ryan Castro: "3 target market(s) growing." Blessd: "2 target market(s) growing." The discrepancy is real (Feid is declining in MX/CO/US, Ryan Castro is growing in CO/CL/etc.), so the scorer is working — but the Top-3-markets summary in the CLI shows declines (-2.8%, -2.4%, -33.6%) yet the geographic_fit score is still 87.2 because Tier-1 concentration carries most of the weight. That's defensible but worth flagging.

## Dossier issues

- **`identity.urls` is empty `{}`.** The profile doesn't expose platform URLs (Spotify URL, Instagram handle, etc.) and the dossier just passes through. For the sales conversation, having direct links matters. Either: (a) extract URLs from Chartmetric's `metadata.cm_statistics` or `metadata.url` fields, (b) construct from known IDs (`https://open.spotify.com/artist/{spotify_id}`).

- **`actionable.social_links` is empty `{}`.** Same root cause as above.

- **`competitive_context.similar_artists` is `[]`** for all 3. Downstream of the empty `neighboring_artists` problem. Major dossier section is hollow.

- **`identity.distributor` is `null`.** Chartmetric doesn't expose distributor info reliably. For an A&R distributor pitching a deal, the prospect's *current* distributor is critical context. **Action item with Julio:** confirm whether they verify distributor manually or want this surfaced from Chartmetric.

- **Dossier prose is purely structured (no narrative).** The four prompt templates in [prompts/](../prompts/) (`scoring_rationale.txt`, `dossier_narrative.txt`, etc.) are not used by `dossier_generator.py` — they're meant to be invoked by the Claude Code skill (`.claude/skills/evaluate.md`) after the dossier dict is returned. CLI output is dict-only. **Decision needed:** does the CLI need to invoke the LLM for narrative, or is this strictly the Claude-Code-skill's job?

## Alert issues

- **No signal_alerts fire on any of the three.** All three artists have plausible diff_pct values that are nowhere near the alert thresholds (Shazam +200%, TikTok +300%, Listener Surge +150%). Thresholds are tuned for early-career breakouts, which is correct — the three superstars don't deserve alerts. Confirms the routing logic; doesn't validate the thresholds (we'd need a small artist mid-spike to do that).

- **Tier classification is consistent between engine (`compute_prospect_score`) and alert router (`route_alert`).** Both use the same `score_min` thresholds from [config/alerts.yaml](../config/alerts.yaml). No drift.

## Open questions for Julio / Mariana

1. **Distributor field:** do you want Chartmetric's best-effort distributor surfaced, or do you verify this manually?
2. **CPM calibration:** what's FaroLatino's actual per-stream margin by platform and country? Current revenue numbers are 5-10x too high for distribution-only revenue.
3. **Editorial playlist tracking:** do you care about *new* editorial adds (signal alert) or *current* placements (dossier section), or both? Drives whether we need a snapshot diff or just a list.
4. **Career stage thresholds:** Chartmetric tags Ryan Castro and Blessd as "superstar" — do you agree, or would you classify either as "rising"? The timing scorer's behaviour pivots hard on this label.

---

## Conclusion

**Pipeline shape works.** All four downstream layers (score, revenue, dossier, alert) consume real Chartmetric data and produce reasonable output, with one inline-patched shape mismatch.

**Three things need fixing before May 5:**
1. Reconcile `Insight` shape — drop `_DATACLASS_FIELD_WHITELIST` workaround.
2. Diagnose `neighboring_artists` empty payload (probably a parser issue).
3. Fix `editorial_playlists = 0` (probably a query-param issue) and surface platform URLs in `identity.urls` / `actionable.social_links`.

**Two things need calibration with Julio:**
1. CPM rates (revenue is order-of-magnitude off).
2. Distributor field (manual vs. Chartmetric-derived).

**One thing needs more data:**
- Run on at least 2-3 *rising* (not superstar) artists so the timing scorer can vary. Without that, Phase C tuning is guesswork.
