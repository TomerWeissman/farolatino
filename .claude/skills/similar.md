---
name: Similar Artists
description: 5-10 artists comparable to a seed by genre, career stage, and scale.
---

# Similar Artists

When the user runs `@similar {artist}`, return a ranked list of comparable
artists. The full pipeline (search → data → neighbors with tier banding)
runs server-side in one tool call.

## Steps

1. Call `mcp__farolatino__find_similar_artists(artist="<name or URL>")`.

2. If the response has `needs_disambiguation`, list the 3 candidates with
   name + monthly listeners and ask the user which one. Then call again
   with `cm_id=<chosen>`.

3. Otherwise the response is `{"seed": {...}, "neighbors": [...], "tier_distribution": {...}, "summary": "..."}`.
   Present it as:
   - **Header**: seed's name, country, career stage, monthly listeners
   - **Neighbors table**: name, country, monthly listeners, career stage,
     tier band (`tier-similar` / `smaller` / `larger`), source (`neighbors`
     or `genre_search`)
   - **One-line summary**: use the `summary` field verbatim
   - **Hint**: "Run `@evaluate {name}` on any of these for the full dossier."

## Rules

- The composite tool is the only data source you need.
- Do **not** Read internal files. Do **not** use the Agent tool. Do **not** Bash.
- If the composite returns `error`, surface it verbatim — don't work around it.
