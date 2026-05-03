---
name: Discover Prospects
description: Automatic discovery scan — Mode 1. Run a filtered scan to find the top 10-20 unsigned Latin artists worth evaluating.
---

# Discover Prospects

When the user runs `/discover` (optionally with a profile name like `/discover latam_expansion`), run a full discovery scan:

## Steps

1. **Load config**: Call `mcp__farolatino__load_config("search_criteria")` and `mcp__farolatino__get_profile(profile_name)` (or "default" if none specified). Merge any filter_overrides from the profile into the base search criteria.

2. **Discovery queries**: Call `mcp__farolatino__discover_artists` with the merged filters. This runs:
   - `artist/list/filter` with career_stage, career_trend, code2, sp_monthly_listeners range, tagId
   - `artist/:type/list` with unsigned=true and metric ranges
   - `artist/anr/by/social-index` and `artist/anr/by/playlists` for momentum-based discovery
   - Deduplicate results by CM artist ID

3. **Filter**: Apply local filters from search_criteria (excluded_artists, excluded_labels, excluded_distributors, dismissed_suppression_days).

4. **Score all candidates**: For each candidate (up to 50):
   a. Check `mcp__farolatino__cache_get` — skip full pull if recently scored and data is fresh
   b. Call `mcp__farolatino__get_artist_data` for full data
   c. Call `mcp__farolatino__compute_prospect_score` with the active profile
   d. Call `mcp__farolatino__cache_set` to store results

5. **Rank**: Sort all scored candidates by prospect_score descending. Take the top 20.

6. **Enrich top prospects**: For the top 20, call `mcp__farolatino__estimate_revenue` and `mcp__farolatino__generate_dossier`.

7. **Alert routing**: Call `mcp__farolatino__route_alert` for each top prospect. Collect all HOT and WARM alerts, plus any signal alerts.

8. **Discovery report**: Use the prompt from `prompts/discovery_analysis.txt` to generate a weekly discovery report covering:
   - Summary stats (scanned, filtered, scored, per-tier counts)
   - Top 5 highlights
   - Emerging patterns
   - Signal alerts
   - Recommended actions

9. **Present**: Display the ranked list with mini-summaries. Offer to show the full dossier for any artist.

## Notes
- Available profiles: default, emerging_momentum, revenue_focus, latam_expansion (or run `mcp__farolatino__list_profiles` to see all)
- If Chartmetric tools are not yet connected, explain what the scan would do and which API endpoints it would call
- For large batches, prioritize Mode 2 (on-demand) requests if they come in during a scan
