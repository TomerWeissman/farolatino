---
name: Similar Artists
description: For any artist, return 5-10 comparable artists with quick stats. Use when Mariana wants to map a prospect's competitive landscape or find peer benchmarks.
---

# Similar Artists

When the user runs `/similar {artist name}`, return a ranked list of 5-10 artists comparable to the seed by genre, career stage, and audience scale.

## Steps

1. **Resolve seed.** Call `chartmetric_search` with the artist name to get their `cm_id`.
   - If multiple matches: present top 3 (name, sp_monthly_listeners, country) and ask the user to pick.
   - If no match: suggest checking spelling or try a Spotify URL.

2. **Pull profile.** Call `get_artist_data(cm_id, use_cache=True)`. The profile now includes a populated `neighboring_artists` field (Chartmetric clustering + a genre-search fallback for sparse cases — see [chartmetric_artist.py:_search_similar_artists_by_genre](../../mcp_server/tools/chartmetric_artist.py)).

3. **Format the list.** For each entry in `neighboring_artists`, surface:
   - Name + country code
   - Career stage (when known)
   - Spotify monthly listeners (band: tier-similar, smaller, larger)
   - Source label (`chartmetric_neighbors` or `genre_search`) so the user knows why we picked them
   - A quick "evaluate" link/instruction (`/evaluate {name}` to dive deeper on any one)

4. **Optional — score them.** If the user asks for "the best similar artists," loop through the top 5-10 and call `compute_prospect_score` + `estimate_revenue` on each, then sort by score. **Cost:** this triggers full `get_artist_data` calls for each — at 14 endpoints throttled at 1 req/s that's ~16s per artist. Confirm with the user before running on more than 3 candidates.

5. **Return.**
   - Markdown table with name, country, monthly_listeners, career_stage, source.
   - Text summary: "X of these are mid-level/growth (your prospect tier); Y are superstar (already established)."
   - Reminder: `/evaluate {name}` to score any one of them.

## When to use this skill

- **Mapping a competitive landscape**: "What other artists look like Hitomi Flor?" → drives roster strategy conversations with Julio.
- **Finding peer benchmarks**: when projecting revenue for a prospect, having 5 comparable artists' stats grounds the estimate.
- **Discovery seeding**: a known successful artist → similar candidates → potential signing targets.

## Failure modes

| Symptom | Likely cause | Fix |
|---|---|---|
| Empty list | Seed artist has no Chartmetric clustering AND no genre tags | Manually pick a representative track and search by feature artist |
| Off-genre results (e.g. French electronica when expecting reggaeton) | Chartmetric clustering is genre-agnostic for some artists | The genre-search fallback should fill in real-genre matches; if it's still off, the artist's `genres` field may be miscategorized in Chartmetric |
| All results in wrong tier | Listener band filter (3x) is too tight or too loose for outliers | Run `/evaluate` on a few manually instead |

## Output format example

```
Similar artists for Hitomi Flor (mid-level, Argentina)

| Artist | Country | Listeners | Stage | Source |
|---|---|---|---|---|
| Eugenia Quevedo | AR | 1.8M | mainstream/steady | neighbors |
| Sonora Siguaray | EC | 113K | developing/decline | neighbors |
| ... | | | | |

7 of 10 are mid-level/mainstream tier (similar to your prospect).
3 are superstar (established; not signing-relevant).

Run /evaluate {name} on any of the above for full revenue projections.
```
