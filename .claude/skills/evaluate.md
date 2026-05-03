---
name: Evaluate Artist
description: Full scored A&R dossier for one artist via the composite tool.
---

# Evaluate Artist

When the user runs `@evaluate {artist}`, the entire pipeline (search → data
pull → score → revenue → dossier → alert) runs server-side in one tool call.
Your only job is to invoke it and present the result.

## Steps

1. Call `mcp__farolatino__evaluate_artist(artist="<the artist name or URL>")`.

2. If the response has `needs_disambiguation`, the artist name was ambiguous.
   List the 3 candidates with name + Spotify monthly listeners and ask the
   user which one. Then call again with `cm_id=<chosen cm_id>`.

3. Otherwise the response is `{"dossier": {...}, "alert": {...}, "cm_id": ...}`.
   Present it in this order:
   - **Tier badge** (HOT / WARM / WATCH / PASS) and **Prospect Score**
   - One-line summary from `dossier.identity.career_stage` + top genres
   - **Dimension breakdown** (`dossier.prospect_score.dimensions`): score,
     weight, and one-line rationale per dimension
   - **Revenue projection** (`dossier.revenue_projection`): 12-month figure +
     per-platform breakdown
   - **Top markets** (`dossier.geographic_profile`)
   - **Recommended next steps** based on tier (from `alert`)

## Rules

- The composite tool is the only data source you need.
- Do **not** Read internal files. Do **not** use the Agent tool. Do **not** Bash.
- If the composite returns `error`, surface it to the user verbatim — don't
  try to work around it manually.
