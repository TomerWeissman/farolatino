---
name: Calibrate Revenue Model
description: Recalibrate streams-per-listener multipliers using FaroLatino royalty data. Run quarterly or after expanding the Chartmetric profile sample.
---

# Calibrate Revenue Model

When the user runs `/calibrate {N}` (default N=60), expand the calibration sample by N book artists, then refit the revenue model's per-bucket multipliers.

## When to invoke

- A new royalty CSV arrives from FaroLatino (replace `data/internal/TOP 10 E.csv`).
- Quarterly maintenance — current sample drift may have been corrected by recent platform CPM changes.
- The `evaluate` skill has been producing visibly off projections on real prospects.

## Prerequisites

- `data/internal/TOP 10 E.csv` exists (the royalty book).
- `.env` has a working `CHARTMETRIC_REFRESH_TOKEN`.
- Activate the venv: `source venv/bin/activate`.

## Steps

The calibration is a 5-stage pipeline. Each stage has its own standalone script — running them in order is the skill's job.

### 1. Expand the sample (if needed)

**Recommended (stratified):**

```bash
python scripts/expand_calibration_sample.py --add 30 --stratify
```

`--stratify` filters new artists by Chartmetric career_stage AND career_trend, keeping only mid-level / mainstream / superstar with growth or steady trend (the actual prospect tier). Skips developing / undiscovered / declining artists, which were over-sampled by NETO-ordered expansion in the past and pulled the global multiplier toward unrealistic values.

You can also target specific buckets:

```bash
python scripts/expand_calibration_sample.py \
  --add 40 --stratify \
  --target-bucket mid-level__growth=10 \
  --target-bucket mainstream__growth=10
```

**Lesson from prior runs:** FaroLatino's book is heavily skewed to developing/legacy tiers. A stratified expansion of the next-30-by-NETO yielded only ~6 actual prospect-tier artists (~20% pass rate). To meaningfully grow the prospect-tier training set, future expansions should reach further down the NETO list AND consider searching Chartmetric for known Latin artists *not yet in the book* (out of scope for this skill but worth noting).

**Plain (non-stratified, NOT recommended):**

```bash
python scripts/expand_calibration_sample.py --add 60
```

Use only when you specifically want to grow the developing-tier bucket-fitted multipliers.

**Time:** ~16 seconds per artist at the throttle. Stratified mode scans up to 4× the target before keeping enough — for `--add 30 --stratify` expect ~25-35 minutes wall time. Run in the background; the orchestrator writes results at completion only.

**Skip this step** if N=0 or if you only want to recompute on an existing sample.

### 2. Compute per-artist catalog coverage via ISRC matching

```bash
python scripts/compute_catalog_coverage.py
```

Matches FaroLatino's distributed ISRCs against each artist's Chartmetric `/tracks` payload to compute `track_coverage` per artist. Output: `data/internal/coverage_per_artist.json`.

Inspect the coverage histogram. Expect roughly 30-40% of artists at coverage ≥ 30% (these become the training set).

### 3. Build the reverse-engineered training dataset

```bash
python scripts/build_training_dataset.py
```

For each artist with `track_coverage ≥ 0.3`, scales their per-platform FaroLatino streams up by `1/track_coverage` to estimate total artist streams. Output: `data/internal/training_dataset.json`. Pairs with each artist's Chartmetric features so the next stage can fit multipliers.

### 4. Fit per-bucket multipliers

```bash
python scripts/fit_multipliers.py
```

Computes median Chartmetric → total-stream multipliers per `(career_stage, coarse_trend, platform)` bucket. Writes a **proposed** YAML to `config/stream_multipliers_proposed.yaml`. The production `config/stream_multipliers.yaml` is **not** overwritten — review the proposal and selectively merge buckets you trust.

**Critical review step:** the auto-fit overwrites the YAML wholesale. Compare the new platform defaults to the existing values:

- Spotify default: should land between 3-7 (book full-catalog median ≈ 4.4).
- YouTube default (subscriber fallback): should land between 3-15. Anything above 15 likely means too few rows had `yt_subscribers > 0`.
- Bucket-specific multipliers should only be kept when ≥3 training rows back them.

If the fit looks noisy (rare bucket combinations, outlier multipliers), revert to the last-known-good defaults using git. **Don't ship multipliers from a sample of <30 high-coverage artists — variance is too high.**

### 5. Validate against the right ground truth

```bash
python scripts/validate_total_revenue.py
```

Measures error against `(FaroLatino_NETO / track_coverage)` — the artist's *total* annual NETO scaled up from the partial book share. Outputs:

- All-eligible MAE
- Active-artist MAE (excluding legacy detector hits)
- Realistic-prospect subset MAE (the 5 active mid-level Latin acts: Dread Mar I, Eugenia Quevedo, Edgar Gonzalon, Noche de Brujas, Hitomi Flor)

**Pass criterion:** realistic-prospect MAE ≤ current production value (currently ~32%). If the new fit makes it worse, roll back the YAML changes.

### 6. Run pytest

```bash
pytest tests/ -q
```

Must be 42/42 green. The model code is unchanged; only the YAML coefficients moved. If tests fail, something else broke.

### 7. Commit

If steps 5-6 pass:

```bash
git add config/stream_multipliers.yaml data/internal/coverage_per_artist.json data/internal/training_dataset.json data/internal/sample_50_cm_ids.json data/internal/sample_45_profiles.json
git commit -m "Recalibrate revenue model multipliers (N artists; MAE X%)"
git push
```

The `data/internal/*.json` files are gitignored (intentional — they contain artist-level data). The YAML is the only public output that changes.

## Outputs

- **Updated:** `config/stream_multipliers.yaml` (production coefficients)
- **Updated (gitignored):** `coverage_per_artist.json`, `training_dataset.json`, `sample_50_cm_ids.json`, `sample_45_profiles.json`
- **Cache (gitignored):** `data/cache/<cm_id>/*.json` (per-endpoint Chartmetric responses, reused on next calibration)

## Failure modes & fixes

| Symptom | Likely cause | Fix |
|---|---|---|
| `expand_calibration_sample.py` fails with HTTP 401 | Chartmetric refresh token expired | Regenerate in Chartmetric dashboard, update `.env` |
| Many search results return wrong artist | Common Latin name with multiple matches | Edit `sample_50_cm_ids.json` manually to set the correct cm_id |
| Coverage histogram skews very low (<30% match for everyone) | ISRC normalization issue (case/whitespace) | Verify `_load_chartmetric_isrcs` and `_clean` strip both |
| Fitted YouTube multiplier > 15 | Too few rows with non-zero `yt_subscribers` | Don't ship — keep last-known-good default. Add more high-coverage YouTube-active artists to the sample. |
| Validation MAE worse than before | Sample bias or too small | Roll back YAML; rerun `expand_calibration_sample.py` with a higher `--add` |

## Known limitations

This calibration cannot fix:
- **Sparse-Chartmetric artists** (Margarita Lugue style — Chartmetric has near-zero `yt_subscribers` but real YouTube streams). Needs YouTube Data API integration.
- **Time mismatch** (24-month average royalty vs current Chartmetric snapshot). Needs Chartmetric historical time-series.
- **Premium-vs-free CPM split** within a country. Implicit in book CPMs but not separately exposed.

Document these in the dossier when projecting; don't try to fix at calibration time.
