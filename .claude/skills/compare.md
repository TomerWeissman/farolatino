---
name: Compare Artists
description: Use Case 3 — Side-by-side comparison of a prospect (public data) against a managed FaroLatino artist (public + internal data).
---

# Compare Artists

When the user runs `/compare {prospect name} vs {managed artist name}`, run a comparative analysis:

## Steps

1. **Resolve both artists**: Call `chartmetric_search` for each artist name. Confirm both are found.

2. **Data pull**: Call `chartmetric_artist` for both artists.

3. **Internal data**: For the managed artist, load internal data from `data/internal/` (revenue, deal terms).

4. **Score both**: Call `compute_prospect_score` for each artist using the same profile.

5. **Revenue for both**: Call `estimate_revenue` for both. For the managed artist, include actual revenue comparison if internal data is available.

6. **Generate dossiers**: Call `generate_dossier` for both artists.

7. **Comparative analysis**: Use the prompt from `prompts/comparison.txt` to generate a side-by-side analysis covering:
   - Metric comparison (listeners, followers, growth rates)
   - Score comparison (per-dimension breakdown)
   - Geographic overlap vs. complementarity
   - Revenue benchmark (prospect projected vs. managed actual)
   - Risk differential
   - Portfolio value assessment

8. **Present**: Display the comparison with:
   - Side-by-side metric table
   - Score comparison chart
   - LLM-generated comparative narrative
   - Clear recommendation: pursue, monitor, or pass

## Notes
- The managed artist serves as a concrete benchmark — the comparison answers "Is this prospect at least as good as what we already signed?"
- If the managed artist's internal data isn't available, compare on public data only and note the limitation
- The `similar-artists/by-configurations` endpoint can provide additional context on how CM sees these artists relative to each other
