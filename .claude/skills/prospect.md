---
name: Prospect Market
description: Use Case 2 — Given a target country, identify and rank the best unsigned artist prospects using public data only.
---

# Prospect Market

When the user runs `/prospect {country}` (e.g., `/prospect Peru` or `/prospect PE`), run a market-specific prospecting scan:

## Steps

1. **Resolve country**: Map the input to an ISO 3166-1 alpha-2 code (e.g., "Peru" → "PE", "Colombia" → "CO"). If ambiguous, ask for clarification.

2. **Load config**: Call `load_config("search_criteria")` as the base, then override `countries` with just the target country. Load the active profile weights.

3. **Discovery**: Call `chartmetric_discovery` with the country-specific filters:
   - `code2` = target country
   - All other filters from search_criteria (genres, unsigned_only, career_stages, etc.)
   - Also run `artist/anr/by/social-index` and `artist/anr/by/playlists` filtered to the target country

4. **Score and rank**: For each candidate:
   - Pull full data via `chartmetric_artist`
   - Call `compute_prospect_score` — D2 Geographic Fit will naturally favor this market since we're looking at artists whose audience IS in this country
   - Cache results

5. **Top prospects**: Take the top 15, run `estimate_revenue` and `generate_dossier` for each.

6. **Market report**: Present results as a market prospecting report:
   - Market overview: how many unsigned artists found, score distribution
   - Top 10 ranked prospects with mini-summaries
   - Genre breakdown (which genres dominate in this market)
   - Revenue opportunity (aggregate projected revenue across top prospects)
   - Comparison to other FaroLatino markets (if data is available)

7. **Offer drill-down**: Offer to run `/evaluate` on any specific artist for the full dossier.

## Notes
- This is public-data-only — no internal FaroLatino data needed
- Country can be specified as name or ISO code
- Can be combined with a profile: `/prospect Peru revenue_focus`
- Results show what's available in that market — useful for planning expansion into new territories
