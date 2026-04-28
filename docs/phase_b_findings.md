# Phase B findings — TOP 10 validation against FaroLatino's actual revenue

Date: 2026-04-28

## What the TOP 10 file actually is

The `TOP 10 (1).7z` archive Julio sent contains a single 2.6 GB CSV (`TOP 10 E.csv`) with **24 months of FaroLatino's actual royalty data** — March 2024 through March 2026, every track they distribute, every platform, every country.

| Metric | Value |
|---|---|
| Total rows | 10,178,385 |
| Unique artists | 1,441 |
| Total streams (24 months) | 8,219,903,817 |
| Total NETO (24 months) | $2,296,910.50 |
| Per-stream rate (NETO/streams) | $0.00028 |
| Months covered | 2024-03 through 2026-03 |
| Top platforms | YouTube Audio, Spotify, Apple/iTunes, Amazon, Deezer, TikTok, Facebook |

**Per-stream rate: $0.28 per 1000 streams.** This is FaroLatino's *net* margin after distribution split. Confirms the Phase A note that our CPM rates in [config/cpm_rates.yaml](../config/cpm_rates.yaml) are 5-10× too generous when modelling NETO (they're roughly correct if interpreted as gross streaming royalty before splits).

## What the data is NOT

It is not a "top 10" list, ranking, or pick set. The filename misleads — it's a transactional report. **None of our Phase A test artists (Feid, Ryan Castro, Blessd) appear in the dataset.** FaroLatino does not distribute them. FaroLatino's actual roster skews to regional Latin music: Argentine reggae (Dread Mar I), Latin reggae (Zona Ganjah), Chilean cumbia (Noche de Brujas), Argentine cumbia (Eugenia Quevedo), Bolivian/Peruvian salsa & folk (Edgar Gonzalon), Mexican corrido (Chalino Sanchez), Ecuadorian classics (Julio Jaramillo).

## Validation methodology

Picked **3 of FaroLatino's top 10 artists by NETO** to score through our Mode 2 pipeline; held the other 7 as a validation set for after Phase C tuning.

| Artist | NETO (24mo) | Segment |
|---|---|---|
| Dread Mar I | $1,172,278 | top performer |
| Noche de Brujas | $131,111 | mid-tier |
| Edgar Gonzalon | $65,660 | small/sparse |

Held-out validation set: Zona Ganjah, Eugenia Quevedo, Sonora Siguaray, Hitomi Flor, Julio Jaramillo, Margarita Lugue, Chalino Sanchez.

## Headline result: scoring is inverted vs. actual revenue

| Artist | Actual NETO/yr | Our Score | Our Tier | Our Annual Revenue |
|---|---|---|---|---|
| **Dread Mar I** (#1 by revenue) | **$586,139** | **54.8** | **PASS** | $3,704,396 (6.3× too high) |
| Noche de Brujas | $65,556 | 60.2 | WATCH | $265,051 (4.0× too high) |
| Edgar Gonzalon (#10 by revenue) | $32,830 | 64.6 | WATCH | $142,383 (4.3× too high) |

The artist generating **the most actual revenue** (Dread Mar I, $586K/year) gets the **worst** prospect score (54.8 PASS). The artist generating **the least** of the three ($33K/year) gets the **best** score (64.6 WATCH). The other dimensions:

| Artist | Mom | Geo | Rev | Tim | Vel | Eng | Plt |
|---|---|---|---|---|---|---|---|
| Dread Mar I | 9.2 | 100 | 100 | 10 | 15 | 68.8 | 100 |
| Noche de Brujas | 19.2 | 75.2 | 100 | 65 | 15 | 62.5 | 100 |
| Edgar Gonzalon | 16.2 | 100 | 98.5 | 65 | 35 | 47.5 | 100 |

Dread Mar I scores low on **Momentum**, **Timing**, and **Content Velocity** — exactly the dimensions weighted toward "is this artist a *future* breakout?" His established/mature profile loses on all three. Edgar Gonzalon scores higher on Timing (mid-level + growth = sweet spot) and Velocity, even though his *actual* commercial output is one-twentieth of Dread's.

## What this tells us

The Prospect Score is built around a **prospective A&R thesis**: find rising artists before they're famous, sign them while there's still upside. That model penalises established artists ("the window has closed; you can't sign them") and rewards mid-level momentum signals.

But FaroLatino's actual revenue book is **established-catalog distribution**, not new-artist signing. They earn $0.28 per 1000 streams on tracks that already exist; their economic interest is in *which catalogs will keep streaming*, not *which artists will hit*. Under that lens:

- "Superstar / steady" should be a strong signal, not a 10-point penalty.
- Content velocity matters less (the existing catalog is already there).
- Momentum matters less (established artists with stable streams are the bedrock).
- Geographic fit and engagement quality (= are these real listeners?) still matter.
- Revenue potential matters most.

This is the most important Phase B finding and it is a question for Julio, not a code change. **We have to know which problem he wants the system to solve before we tune anything in Phase C.**

## Two possible interpretations — both worth presenting to Julio

**Interpretation 1: The system is solving the wrong problem.**
FaroLatino is a distributor, not a record label. The Mode 2 use case as built will under-rank exactly the artists who actually generate FaroLatino revenue. We need either: (a) a new scoring profile (`distribution_value`) that re-weights toward established/steady artists, or (b) a re-scoping of Mode 2 itself.

**Interpretation 2: The system is solving the right problem, just measured against the wrong benchmark.**
Mode 1 (weekly discovery) and Mode 2 (on-demand A&R evaluation) are intentionally about *new* signings. The existing TOP 10 catalog is FaroLatino's legacy book that runs on autopilot. Our scoring would correctly *not* recommend Dread Mar I as a signing target — he's already established and probably already locked into a long-term distribution deal. To validate Mode 2 properly we'd need a list of artists FaroLatino has *recently signed or evaluated*, not their existing royalty book.

Either interpretation is plausible. **Both should go to Julio in writing.**

## Other findings

### Revenue model multiplier is consistent across the three artists (4-6×)

Even though our score ordering is inverted, the *revenue projection* directionally tracks (Dread > Noche > Edgar, just like NETO). The 4-6× over-projection is consistent enough that a single calibration constant (~0.2× current values, or properly: split the model output by an average distribution share) would land us in the right ballpark for NETO. This is fixable.

### Edgar Gonzalon's profile is suspicious
510,775 monthly Spotify listeners but only **5,215 Spotify followers** (a 98:1 listener-to-follower ratio). For comparison, healthy ratios are typically 1-5×. This level of asymmetry is usually one of:
- Fake/bot streams
- A purely playlist-driven catalog (no fan base; algorithmic plays only)
- Old/classic catalog being rediscovered by Spotify's recommendations

The engagement_quality scorer **didn't flag this**, scoring it 47.5 (mid-range). Likely the threshold isn't tight enough for the regional-catalog tier. Worth a Phase C look.

### Career-stage tagging from Chartmetric is not consistent
Chartmetric tagged Dread Mar I as "superstar" (correct — 9.5M monthly listeners), Noche de Brujas as "mid-level" (~870K, plausible), and Edgar Gonzalon as "mid-level" (~510K monthly listeners but a tiny social footprint). The "mid-level" classification of Edgar Gonzalon is a stretch — his fundamentals look more like "rising / playlist-driven" than "mid-level". The scorer treats `mid-level + growth` as the timing sweet spot, which is what gave him the high score. Worth flagging.

### Dread Mar I has empty `genres` and missing `career_trend`
The Chartmetric metadata for Dread Mar I returned an empty `genres` list and `career_trend` as `''`. We don't have the trend signal for him at all. This impacted his Momentum score directly. Either the metadata endpoint genuinely doesn't have it, or our parser is dropping it for this artist — worth a 5-minute investigation in Phase C.

## Recommendation for next step

Stop coding until Julio answers two questions:

1. **Is the Mode 2 use case "find new signings" (current build) or "evaluate existing/upcoming catalog acquisition" (which the TOP 10 data implies you actually do)?**
2. **CPM calibration: confirm that NETO ≈ 0.2× gross streaming royalty for FaroLatino's deals, or give us the actual per-stream by platform/country.**

If answer to (1) is "find new signings," we don't need Phase C tuning yet — instead we need a list of artists FaroLatino has actually evaluated recently (signed, declined, or watching) to use as a calibration set. The TOP 10 isn't that list.

If answer to (1) is "evaluate distribution catalog," we add a `distribution_value` profile in [config/profiles.yaml](../config/profiles.yaml) with re-balanced weights and re-run all 10 TOP 10 artists to validate.

Either way the held-out 7-artist validation set ([data/internal/top10_cm_ids.json](../data/internal/top10_cm_ids.json)) can be used for the after-tuning check.

## Files produced this phase

- `data/internal/TOP 10 E.csv` (extracted, 2.6 GB, gitignored)
- `data/internal/top10_summary.json` — aggregate stats, top-50 by NETO and streams (gitignored)
- `data/internal/top10_cm_ids.json` — Chartmetric IDs for the top 10 (gitignored)
- `data/internal/calibration_scored.json` — full pipeline output for the 3 calibration artists (gitignored)
- `docs/phase_b_findings.md` — this document (committed)
