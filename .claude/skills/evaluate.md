---
name: Evaluate Artist
description: On-demand artist evaluation — Mode 2. Enter an artist name, get a full scored dossier in under 60 seconds.
---

# Evaluate Artist

When the user runs `/evaluate {artist name}`, perform a full on-demand evaluation:

## Steps

1. **Search**: Call `chartmetric_search` with the artist name to resolve their Chartmetric ID.
   - If multiple results, present the top 3 candidates showing name, Spotify monthly listeners, and followers. Ask the user to pick.
   - If no results, suggest checking the spelling or trying a social/streaming URL with `chartmetric_search_by_url`.

2. **Data pull**: Call `chartmetric_artist` with the selected CM artist ID to pull all data (metadata, cmStats, career, where-people-listen, social audience, tracks, albums, playlists, charts, milestones, insights, neighboring artists, URLs).

3. **Cache**: Call `cache_set` for each data type to store the raw responses.

4. **Score**: Call `compute_prospect_score` with the assembled artist data dict and the user's active profile (ask which profile or default to "default"). This runs all 7 dimensions.

5. **Revenue**: Call `estimate_revenue` with the artist data to project 12-month earnings.

6. **Dossier**: Call `generate_dossier` with the artist data, score result, and revenue result.

7. **Alert check**: Call `route_alert` with the scored result to determine tier and any signal alerts.

8. **Present**: Display the dossier to the user in a clear, readable format:
   - Lead with the Prospect Score, tier badge (HOT/WARM/WATCH/PASS), and one-line summary
   - Show the dimension breakdown with scores and rationales
   - Show key metrics, geographic profile, revenue projection
   - End with recommended next steps based on tier

9. **LLM narrative**: Use the prompt from `prompts/scoring_rationale.txt` to generate a human-readable scoring rationale, and `prompts/dossier_narrative.txt` for the executive summary.

## Notes
- Target: complete evaluation in under 60 seconds
- If Chartmetric tools are not yet connected, report which tools are missing and show what the output would look like using cached/mock data if available
- Always show confidence level — flag if data is incomplete
