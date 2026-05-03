---
name: Analyze Internal Artist
description: Use Case 1 — Analyze an artist already managed by FaroLatino using both public Chartmetric data and internal distribution data.
---

# Analyze Internal Artist

When the user runs `/analyze {artist name}`, run an internal artist analysis:

## Steps

1. **Search**: Call `mcp__farolatino__search_artists` to resolve the artist's CM ID (same as /evaluate step 1).

2. **Public data pull**: Call `mcp__farolatino__get_artist_data` to get all public data.

3. **Internal data**: Look for matching internal data in `data/internal/` (revenue reports, CPM actuals, deal terms). Match by artist name or internal ID.

4. **Score**: Call `mcp__farolatino__compute_prospect_score` — even for managed artists, scoring shows where they stand relative to the market.

5. **Revenue comparison**: Call `mcp__farolatino__estimate_revenue` for the projected revenue, then compare against actual internal revenue data:
   - Show projected vs. actual, with % deviation
   - Identify which markets/platforms have the biggest gap between projected and actual
   - Flag optimization opportunities (e.g., "Growing audience in Brazil but no Deezer distribution")

6. **Generate dossier**: Call `mcp__farolatino__generate_dossier` with the enriched data.

7. **Present**: Display the analysis with a focus on:
   - Public metrics health check (are they growing, stable, declining?)
   - Revenue model accuracy for this artist (projected vs. actual)
   - Untapped opportunities (markets where audience is growing but distribution is weak)
   - Comparison to when the artist was first signed (if deal history is available)

## Notes
- This use case requires FaroLatino internal data files in `data/internal/`
- If internal data is not available, fall back to public-only analysis and note what's missing
- The revenue comparison is key for calibrating the model — flag large deviations for investigation
