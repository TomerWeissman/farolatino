# FaroLatino A&R Pipeline — Product Requirements Document (v1)

**Version:** 1.0
**Date:** April 13, 2026
**Author:** Tomer Weissman (External Technology Consultant)
**Client:** FaroLatino

---

## 1. Executive Summary

This document specifies the v1 deliverable of FaroLatino's A&R scouting pipeline: an AI-powered system that filters ~106K daily Latin music DSP releases to surface unsigned artists worth signing. The system operates in two modes — weekly automatic discovery and on-demand real-time evaluation — producing scored artist dossiers across 7 dimensions. v1 uses Chartmetric as the primary external data source, with a data-source-agnostic architecture that allows FaroLatino to independently add sources post-handoff.

**Primary deliverable:** Claude Code Skills + MCP tools (not a web app). Can be wrapped in a frontend later.

**May 5 milestone:** On-demand evaluation (Mode 2) must be functional for live field-testing during the Colombia trip.

---

## 2. System Modes

### 2.1 Mode 1 — Automatic Discovery ("The System Proposes")

**Trigger:** Scheduled weekly scan (cadence configurable).

**Flow:**
1. Query Chartmetric discovery endpoints with configured search profile filters
2. Filter to unsigned/independent artists only
3. For each candidate, pull full artist data and compute Prospect Score
4. Rank and return top 10-20 prospects
5. Generate dossiers for qualifying artists
6. Route alerts based on score tier

**Primary API endpoints:**

- **`GET /api/artist/list/filter`** — Filter by career_stage, career_trend, country (code2), sp_monthly_listeners range, genre (tagId)
- **`GET /api/artist/:type/list`** — Filter by metric ranges + `unsigned=true` flag
- **`GET /api/artist/anr/by/social-index`** — Surface artists with strong social momentum
- **`GET /api/artist/anr/by/playlists`** — Surface artists with playlist momentum
- **`GET /api/track/list/filter`** — Track-level discovery via shazam_count, tiktok_posts, spotify_plays thresholds
- All artist deep-dive endpoints (see Section 5) for scoring

### 2.2 Mode 2 — On-Demand Evaluation ("The A&R Proposes")

**Trigger:** A&R team member inputs an artist name.
**SLA:** Complete dossier + Prospect Score in under 60 seconds.

**Flow:**
1. Search Chartmetric for the artist by name
2. Resolve to Chartmetric artist ID
3. Pull full artist data from all relevant endpoints
4. Compute Prospect Score across all 7 dimensions
5. Generate and deliver structured dossier

**Primary API endpoints:**

- **`GET /api/search?q={name}&type=artists`** — Text search returns artist candidates with CM ID, sp_followers, sp_monthly_listeners
- **`GET /api/search/social?url={url}`** — Resolve artist from a social/streaming URL (alternate entry point)
- All artist deep-dive endpoints (see Section 5) for scoring + dossier

**Disambiguation:** When search returns multiple results, present the top candidates (with listeners/followers counts) for human selection before proceeding.

---

## 3. Data Sources

### 3.1 What Chartmetric Provides (v1 Primary Source)

Chartmetric is the single external API for v1. It covers the following data categories:

**Artist Identity & Metadata**
- Name, image, genres, tags, career status, social/streaming URLs
- Record label, distributor (enables unsigned/independent filtering)
- Cross-platform ID mapping (Spotify, YouTube, Apple Music, Deezer, etc.)
- Endpoints: `GET /api/artist/:id`, `GET /api/artist/:id/urls`, `GET /api/artist/:type/:id/get-ids`

**Streaming & Social Metrics (All Platforms)**
- Spotify: monthly listeners, followers, popularity, listeners-to-followers ratio
- YouTube: subscribers, views, daily views
- TikTok: followers, likes
- Instagram: followers
- Deezer, Shazam, Soundcloud, Bandsintown, Songkick, Wikipedia, Line Music, Melon
- Weekly and monthly diffs + diff_percent for all metrics
- Endpoint: `GET /api/artist/:id/cmStats`

**Growth & Career Trajectory**
- Career stage classification: undiscovered, developing, mid-level, mainstream, superstar, legendary
- Career momentum: decline, losing, stable, gaining, rising, explosive growth (with numeric score)
- Endpoint: `GET /api/artist/:id/career`

**Geographic Data**
- Spotify where-people-listen: city-level and country-level listener counts with previous-period comparisons
- YouTube market coverage: geographic view distribution
- Instagram/TikTok/YouTube audience stats: top countries, top cities, demographic breakdowns
- Endpoints: `GET /api/artist/:id/where-people-listen`, `GET /api/artist/:id/market-coverage-views/youtube`, `GET /api/artist/:id/social-audience-stats`, `GET /api/artist/:id/instagram-audience-stats`, `GET /api/artist/:id/tiktok-audience-stats`, `GET /api/artist/:id/youtube-audience-stats`

**Playlist Intelligence**
- All playlist placements (Spotify, Apple Music, Deezer, Amazon)
- Editorial vs. algorithmic vs. user-generated classification
- Playlist reach (follower count), track position within playlist
- Historical playlist additions/removals
- Endpoint: `GET /api/artist/:id/:platform/:status/playlists`

**Chart Performance**
- Chart appearances across platforms and countries
- Endpoint: `GET /api/artist/:id/:type/charts`

**Catalog & Release History**
- Full track catalog with ISRC codes, release dates, album labels, version types (remix, live, etc.)
- Album discography with timeline
- Endpoints: `GET /api/artist/:id/tracks`, `GET /api/artist/:id/albums`

**Milestones & Signals**
- Platform milestones with star ratings (e.g., "reached 1M Spotify streams")
- Daily/weekly noteworthy insights (metric spikes, anomalies)
- Endpoints: `GET /api/artist/:id/milestones`, `GET /api/artist/:id/noteworthy-insights`

**Network & Similarity**
- Neighboring artists (genre-similar, includes `signed` field)
- Related artists (fan overlap)
- Similar artists by configurable dimensions (audience, mood, genre, musicality) with career_stage and recent_momentum
- Endpoints: `GET /api/artist/:id/neighboring-artists`, `GET /api/artist/:id/relatedartists`, `GET /api/artist/:id/similar-artists/by-configurations`

**Cross-Platform Performance**
- Unified 0-1 CPP (Cross-Platform Performance) score
- Endpoint: `GET /api/artist/:id/cpp`

**Fan Metrics Time Series**
- Historical metric data per platform with geographic filtering
- Endpoint: `GET /api/artist/:id/stat/:source`

**Live Events & Venues**
- Upcoming/past events and venue data
- Endpoints: `GET /api/artist/:id/:status/events`, `GET /api/artist/:id/venues`

### 3.2 What Chartmetric Does NOT Provide (External Sources Required)

**Critical (blocks core functionality):**

- **CPM rates by country/platform** — Source: FaroLatino internal. Used for D3 Revenue Potential, core of the revenue estimation model.
- **Revenue by platform (historical)** — Source: FaroLatino internal. Used for revenue model calibration and Use Case 1 (internal artist analysis).
- **Release performance (managed artists)** — Source: FaroLatino internal. Used for model calibration — target ~10% deviation.
- **Tier 1/2/3 market classification** — Source: FaroLatino internal. Used for D2 Geographic Fit — weight markets by FaroLatino's priorities.

**High priority:**

- **Deal history** — Source: FaroLatino internal. Used for Use Case 3 (comparative analysis), benchmark terms.

**Medium priority:**

- **Save-to-stream ratios** — Source: Spotify API. Used for D6 Engagement Quality — best bot detection signal.
- **Press coverage & media mentions** — Source: Web scraping (Google). Used for dossier enrichment and D4 Timing context.
- **Artist contact information** — Source: Web scraping. Used for actionable outreach info in dossiers.

**Low priority:**

- **Premium vs. ad-supported listener ratio** — Source: Not available externally. Used for D3 Revenue Potential — use FaroLatino estimates as constants.
- **Artist age estimation** — Source: Web scraping. Used for search filter and dossier metadata.
- **Language detection** — Source: Web scraping / inference from metadata. Used for search filter.
- **Deep Instagram engagement data** — Source: Meta API or web scraping. Used for D6 Engagement Quality — evaluate CM social-audience-stats first.

### 3.3 FaroLatino Internal Data (Format TBD)

Requires coordination with Javier/Agustin (Finance) and Mariana (CTO). Needed before scoring calibration:

1. **CPM table** — Country x Platform matrix of actual cost-per-mille rates
2. **Revenue reports** — Historical earnings by artist, platform, territory
3. **Roster performance** — At least 5 managed artists with known revenue for calibration runs
4. **Market tier table** — FaroLatino's Tier 1/2/3 country classification
5. **Deal terms** (optional for v1) — Historical signing terms for comparative analysis

**Format requirements:** CSV, JSON, or any structured format. The ingestion layer will normalize.

---

## 4. Configuration System

All configuration is stored in external config files (YAML/JSON). No hardcoded business logic.

### 4.1 Search Criteria

```yaml
# Example: search_criteria.yaml
filters:
  countries: ["CO", "MX", "AR", "CL", "PE"]    # ISO 3166-1 alpha-2
  genres: ["reggaeton", "latin pop", "cumbia"]    # Chartmetric tag IDs
  monthly_listeners:
    min: 1000
    max: 200000
  unsigned_only: true                             # Maps to unsigned=true API param
  career_stages: ["developing", "mid-level"]      # CM career stage values
  career_trends: ["gaining", "rising", "explosive growth"]
  min_momentum_score: 40                          # CM career momentum threshold
  released_within_months: 6                       # Activity recency requirement
  excluded_artists: []                            # CM artist IDs to skip
  excluded_labels: []                             # Label names to exclude
  excluded_distributors: []                       # Distributor names to exclude
  dismissed_suppression_days: 90                  # Re-evaluate after N days
```

**Mapping to Chartmetric API:**
- `countries` → `code2` param on `artist/list/filter`
- `genres` → `tagId` param on `artist/list/filter`
- `monthly_listeners` → `sp_ml_min`/`sp_ml_max` or metric range on `artist/:type/list`
- `unsigned_only` → `unsigned=true` on `artist/:type/list`
- `career_stages` → `career_stage` param on `artist/list/filter`
- `career_trends` → `career_trend` param on `artist/list/filter`

### 4.2 Search Profiles

Named profiles that adjust scoring weights for specific business intents:

```yaml
# Example: profiles.yaml
profiles:
  emerging_momentum:
    name: "Emerging Artist with Momentum"
    description: "Find fast-growing unsigned artists in developing stage"
    weights:
      momentum: 0.35          # Boosted from default 0.25
      geographic_fit: 0.20
      revenue_potential: 0.15  # Reduced — growth matters more than revenue here
      timing: 0.15
      content_velocity: 0.05
      engagement_quality: 0.05
      platform_diversification: 0.05
    filter_overrides:
      career_stages: ["undiscovered", "developing"]
      career_trends: ["rising", "explosive growth"]

  revenue_focus:
    name: "Revenue Focus"
    description: "Prioritize artists with high projected revenue"
    weights:
      momentum: 0.15
      geographic_fit: 0.20
      revenue_potential: 0.35  # Boosted
      timing: 0.10
      content_velocity: 0.05
      engagement_quality: 0.10
      platform_diversification: 0.05

  latam_expansion:
    name: "LATAM Expansion"
    description: "Find artists with strong regional presence in target LATAM markets"
    weights:
      momentum: 0.20
      geographic_fit: 0.35    # Boosted
      revenue_potential: 0.15
      timing: 0.10
      content_velocity: 0.08
      engagement_quality: 0.07
      platform_diversification: 0.05
    filter_overrides:
      countries: ["CO", "PE", "EC", "BO", "PY"]  # Expansion markets
```

**Minimum 3 preset profiles ship with v1** (the three above).

### 4.3 Alert Rules

```yaml
# Example: alerts.yaml
tiers:
  hot:
    score_range: [85, 100]
    action: "immediate_contact"
    channels: ["email", "whatsapp"]
    priority: "real_time"
  warm:
    score_range: [70, 84]
    action: "weekly_review"
    channels: ["email"]
    priority: "daily_digest"
  watch:
    score_range: [55, 69]
    action: "passive_tracking"
    channels: ["email"]
    priority: "weekly_digest"
  pass:
    score_range: [0, 54]
    action: "archive"
    channels: []
    reevaluate_after_days: 90

# Signal-based alerts (trigger regardless of overall score)
signal_alerts:
  - name: "Shazam Spike"
    condition: "shazam_count_diff_percent > 200"
    source: "cmStats"
    channels: ["email", "whatsapp"]
  - name: "Editorial Playlist Add"
    condition: "playlist.is_editorial == true && playlist.added_recently"
    source: "playlists"
    channels: ["email"]
  - name: "TikTok Virality"
    condition: "tiktok_posts_diff_percent > 300 || track.tiktok_posts > 50000"
    source: "cmStats, track/list/filter"
    channels: ["email", "whatsapp"]
  - name: "Career Momentum Surge"
    condition: "career_trend changed to explosive_growth"
    source: "career"
    channels: ["email", "whatsapp"]
```

### 4.4 Data Source Registry (Extensibility)

```yaml
# Example: data_sources.yaml
sources:
  chartmetric:
    type: api
    base_url: "https://api.chartmetric.com"
    auth:
      method: refresh_token
      token_endpoint: "/api/token"
      token_ttl_seconds: 3600
    rate_limit:
      type: sliding_window
      # CM uses sliding window rate limiting — specific limits per plan
    enabled: true
    
  farolatino_internal:
    type: file
    path: "./data/internal/"
    formats: ["csv", "json"]
    enabled: true

  # Future sources — disabled by default, ready to plug in
  spotify_api:
    type: api
    enabled: false
    
  luminate:
    type: api
    enabled: false
    
  viberate:
    type: api
    enabled: false
```

---

## 5. Scoring Engine — Prospect Score (0-100)

### 5.1 Dimension Specifications

#### D1 — Momentum Score (Default Weight: 25%)

**What it measures:** Growth velocity, not absolute size. An artist at 5K listeners growing 40% MoM outscores a stagnant 500K-listener artist.

**Chartmetric data sources:**

- `GET /api/artist/:id/cmStats` — `sp_monthly_listeners_diff_percent`, `sp_followers_diff_percent`, `youtube_channel_subscribers_diff_percent`, `tiktok_followers_diff_percent` (weekly + monthly diffs for all platforms)
- `GET /api/artist/:id/career` — `momentum` score (numeric), `trend` classification (decline through explosive growth)
- `GET /api/artist/:id/noteworthy-insights` — Recent metric spikes and anomalies
- `GET /api/artist/:id/stat/:source` — Historical time series for trend analysis

**Scoring logic:**
- Primary signal: CM career momentum score + trend classification
- Secondary signals: cross-platform listener/follower growth rates (monthly diffs)
- Boost: noteworthy-insights flagging recent acceleration
- Penalty: declining metrics on any major platform

**External data needed:** None. Fully covered by Chartmetric.

---

#### D2 — Geographic Fit (Default Weight: 20%)

**What it measures:** Alignment between the artist's audience geography and FaroLatino's distribution infrastructure and market priorities.

**Chartmetric data sources:**

- `GET /api/artist/:id/where-people-listen` — `listeners` and `prev_listeners` per city and country (Spotify)
- `GET /api/artist/:id/market-coverage-views/youtube` — YouTube views by country
- `GET /api/artist/:id/social-audience-stats` — Instagram/YouTube/TikTok audience by country and city
- `GET /api/artist/:id/instagram-audience-stats` — IG top_countries, top_cities
- `GET /api/artist/:id/tiktok-audience-stats` — TikTok top_countries
- `GET /api/artist/:id/youtube-audience-stats` — YT top_countries

**Scoring logic:**
- Cross-reference artist's audience countries with FaroLatino's Tier 1/2/3 market table
- Tier 1 market concentration scores highest
- Multi-platform geographic consistency (same markets across Spotify + YT + social) is a positive signal
- Listener growth in target markets (via `prev_listeners` comparison) boosts score

**External data needed:**
- **FaroLatino market tier table** (Critical — defines what "fit" means)
- Apple Music geographic data is not available from CM — gap accepted for v1

---

#### D3 — Revenue Potential (Default Weight: 20%)

**What it measures:** Projected 12-month income based on streams, audience geography, and platform distribution.

**Chartmetric data sources:**

- `GET /api/artist/:id/cmStats` — `sp_monthly_listeners`, `youtube_channel_views`, platform-level metrics
- `GET /api/artist/:id/where-people-listen` — Country-level listener distribution (for CPM weighting)
- `GET /api/artist/:id/stat/:source` — Historical streaming trends for projection

**Scoring logic:**
- Estimate monthly streams per platform from CM metrics
- Weight streams by country using FaroLatino's CPM table
- Apply platform-specific CPM rates (Spotify vs. YouTube vs. Apple Music etc.)
- Project forward 12 months using growth trajectory from D1
- Calibrate against FaroLatino's actual revenue data for managed artists (target ~10% deviation)

**External data needed:**
- **FaroLatino CPM table** (Critical — country x platform CPM rates)
- **FaroLatino revenue reports** (Critical — calibration data)
- **Premium vs. ad-supported ratio** (Low priority — use FaroLatino estimates as constants)

---

#### D4 — Timing (Default Weight: 15%)

**What it measures:** Whether the artist is in the "sweet spot" — post-viralization but pre-major-label interest. The window where signing delivers maximum ROI.

**Chartmetric data sources:**

- `GET /api/artist/:id/career` — `stage` (undiscovered through legendary), `trend`
- `GET /api/artist/:id/:type/charts` — Chart appearances (official charts = may be too late)
- `GET /api/artist/:id/milestones` — Recent platform milestones with star ratings
- `GET /api/artist/:id/noteworthy-insights` — Breakout signals
- `GET /api/artist/:id/neighboring-artists` — `signed` field shows if similar artists are getting signed (market heat)
- `GET /api/track/list/filter` — `shazam_count` for Shazam spikes = early virality signal

**Scoring logic:**
- Ideal timing: career_stage = "developing" or "mid-level" AND career_trend = "rising" or "explosive growth"
- Positive signals: Shazam spikes, regional radio traction, editorial playlist adds, social virality
- Negative signals: official chart placements in major markets (majors likely already circling), record_label already populated with a major
- Context: if neighboring artists in the same genre/market are getting signed (`signed=true`), the window may be closing

**External data needed:**
- Web scraping: press coverage mentioning major label interest (Medium priority)

---

#### D5 — Content Velocity (Default Weight: 8%)

**What it measures:** Release frequency as a signal of an active, committed project. One track/month = commitment; one isolated hit 6 months ago = risk.

**Chartmetric data sources:**

- `GET /api/artist/:id/tracks` — Full catalog with `release_date` per track, `version_type` (original, remix, live)
- `GET /api/artist/:id/albums` — Album timeline and track counts

**Scoring logic:**
- Count original releases (exclude remixes, live versions) in last 6 and 12 months
- Ideal: 1+ releases per month over last 6 months
- Penalty for long gaps (>3 months with no release)
- Bonus for consistent release cadence (low variance in release intervals)

**External data needed:** None. Fully covered by Chartmetric.

---

#### D6 — Engagement Quality (Default Weight: 7%)

**What it measures:** Whether the artist's metrics are organic or artificially inflated. The "lie detector."

**Chartmetric data sources:**

- `GET /api/artist/:id/cmStats` — `sp_followers_to_listeners_ratio` (abnormally low ratio signals bot streams)
- `GET /api/artist/:id/instagram-audience-stats` — `engagement_rate`
- `GET /api/artist/:id/social-audience-stats` — Cross-platform engagement patterns
- `GET /api/artist/:id/stat/:source` — Time series for suspicious spike/drop detection

**Scoring logic:**
- Primary signal: `sp_followers_to_listeners_ratio` — healthy range indicates organic audience
- Instagram engagement rate as cross-validation
- Time series analysis: organic growth is gradual; bot-inflated metrics show sudden spikes and drops
- Cross-platform consistency: real audiences show correlated growth across platforms

**External data needed:**
- **Spotify API save-to-stream ratios** (Medium priority — best bot detection signal, not available from CM)
- If Spotify API is not integrated in v1, the CM-based signals above provide reasonable coverage

---

#### D7 — Platform Diversification (Default Weight: 5%)

**What it measures:** Risk mitigation through multi-platform presence. An artist dependent on a single platform is riskier than one with balanced presence across Spotify + YouTube + TikTok + Apple Music.

**Chartmetric data sources:**

- `GET /api/artist/:id/cmStats` — Presence/absence + metric levels across all platforms (Spotify, YouTube, TikTok, Instagram, Deezer, Shazam, Soundcloud, Apple Music, etc.)
- `GET /api/artist/:id/cpp` — Cross-Platform Performance score (0-1), direct measure of platform balance

**Scoring logic:**
- Primary signal: CM's CPP score — already measures cross-platform performance
- Secondary: count platforms with meaningful presence (above threshold) and measure distribution evenness
- Bonus for presence on regionally important platforms (e.g., Deezer in Brazil)

**External data needed:** None. Fully covered by Chartmetric.

---

### 5.2 Score Computation

```
Prospect Score = Sum(Di_score * Di_weight) for i in 1..7

Where:
  - Each Di_score is normalized to 0-100
  - Di_weight values come from the active search profile (or defaults)
  - Sum of all weights = 1.0
```

Each dimension scorer is an independent module that:
1. Receives raw data from the data layer
2. Applies dimension-specific logic
3. Returns a normalized 0-100 score with a confidence level and reasoning text

The LLM synthesizes dimension scores into the final Prospect Score and generates human-readable scoring rationale.

### 5.3 Scoring Coverage Summary

| Dimension                      | CM Coverage | External Data Needed                          | Confidence   |
|--------------------------------|-------------|-----------------------------------------------|--------------|
| D1 Momentum (25%)             | Full        | None                                          | High         |
| D2 Geographic Fit (20%)       | High        | FaroLatino market tier table                  | High         |
| D3 Revenue Potential (20%)    | Partial     | FaroLatino CPMs + revenue data (critical)     | Medium*      |
| D4 Timing (15%)               | Full        | Web scraping for label interest (optional)    | High         |
| D5 Content Velocity (8%)      | Full        | None                                          | High         |
| D6 Engagement Quality (7%)    | High        | Spotify save-to-stream ratios (nice-to-have)  | Medium-High  |
| D7 Platform Diversification (5%) | Full     | None                                          | High         |

*Medium until calibrated against FaroLatino internal data.

---

## 6. Revenue Estimation Model

Standalone module within D3 that converts public streaming data into projected earnings.

### 6.1 Model Inputs

**From Chartmetric:**
- Monthly stream counts per platform (from cmStats)
- Geographic listener distribution (from where-people-listen, social-audience-stats)
- Growth trajectory (from career momentum, historical stat time series)

**From FaroLatino (Critical):**
- CPM rates: Country x Platform matrix (e.g., US Spotify = $X, Mexico Spotify = $Y)
- Premium vs. ad-supported ratio estimates per market (can be constants initially)
- Historical revenue reports for calibration

### 6.2 Model Logic

```
Projected Monthly Revenue =
  Sum over platforms(
    Sum over countries(
      monthly_streams_platform_country * CPM_platform_country / 1000
    )
  )

Projected Annual Revenue = Monthly * 12 * growth_adjustment_factor
```

Where `growth_adjustment_factor` accounts for the artist's momentum trajectory.

### 6.3 Calibration

- Run model against minimum 5 FaroLatino-managed artists with known revenue
- Target: ~10% deviation between projected and actual
- Iterate CPM assumptions and growth modeling until calibration target is met
- Document calibration results and assumptions

---

## 7. Artist Dossier Output

Each evaluated artist produces a structured dossier containing:

### 7.1 Identity
- Artist name, image, genres
- Social/streaming URLs (from `GET /api/artist/:id/urls`)
- Record label / distributor status
- Career stage and momentum classification

### 7.2 Metrics Overview
- Monthly listeners and followers: Spotify, YouTube, TikTok, Instagram
- Week-over-week and month-over-month changes for each
- Cross-Platform Performance (CPP) score

### 7.3 Prospect Score Breakdown
- Overall Prospect Score (0-100) with tier classification (HOT/WARM/WATCH/PASS)
- Per-dimension scores (D1-D7) with brief rationale per dimension
- Confidence level (based on data completeness)

### 7.4 Geographic Profile
- Top 3-5 markets by listener concentration (from where-people-listen)
- Market tier classification per FaroLatino's table
- Geographic growth trends (which markets are growing fastest)

### 7.5 Revenue Projection
- Estimated monthly revenue by platform
- Estimated annual revenue (with growth projection)
- Key revenue drivers (which markets/platforms contribute most)

### 7.6 Career Trajectory
- Classification: explosive growth / sustained growth / stagnation / decline
- Historical metrics chart (last 6-12 months)
- Key milestones achieved

### 7.7 Catalog & Activity
- Release count (last 6 and 12 months)
- Latest releases with performance metrics
- Playlist placements (editorial highlights)

### 7.8 Risk Signals
- Engagement quality assessment (bot detection)
- Platform concentration risk
- Single-hit dependency risk
- Label interest signals (if available)

### 7.9 Competitive Context
- Similar/neighboring artists with their career stages
- Audience overlap artists
- Benchmarking against comparable signed artists

### 7.10 Actionable Information
- Contact info (if available from web scraping)
- Social media links
- Recommended next steps based on score tier

---

## 8. Processing Pipeline

### 8.1 Stage 1 — Ingestion

**Scheduled tasks:**
- Pull data from all configured sources on a per-artist basis
- Cache responses to avoid redundant API calls (Chartmetric rate limits use sliding window)
- Cache TTL: configurable, default 24 hours for most data, 1 hour for real-time evaluation (Mode 2)

**Rate limit management:**
- Chartmetric uses sliding window rate limiting
- Implement request queuing with backoff
- Prioritize Mode 2 (on-demand) requests over Mode 1 (batch) requests

### 8.2 Stage 2 — Normalization

- Standardize date formats
- Normalize country codes to ISO 3166-1 alpha-2
- Resolve artist name variants
- Handle missing fields gracefully (score with available data, report confidence)
- Deduplicate records across sources

### 8.3 Stage 3 — Enrichment

- Join data across endpoints by Chartmetric artist ID
- Build unified artist profile object containing all data needed for scoring
- Cross-reference with FaroLatino internal data (when available)
- Flag data freshness (how recently each data point was updated)

### 8.4 Caching Strategy

**What to cache:**
- Artist metadata and cmStats (changes daily)
- Where-people-listen data (changes weekly)
- Career stage/trend (changes weekly)
- Track catalog (changes on new release)
- Social audience stats (changes weekly)

**Storage:** Local file cache for v1 (JSON files organized by artist ID and endpoint). Supabase or R2 only if data volume or multi-user access requires it.

---

## 9. Technical Architecture

### 9.1 Component Overview

```
                    +-------------------+
                    |   User Interface  |
                    | (Claude Code CLI) |
                    +--------+----------+
                             |
                    +--------v----------+
                    |   Claude Skills   |
                    | - Discovery Skill |
                    | - Evaluate Skill  |
                    | - Compare Skill   |
                    | - Analyze Skill   |
                    +--------+----------+
                             |
                    +--------v----------+
                    |    MCP Tools      |
                    | - Chartmetric API |
                    | - Scoring Engine  |
                    | - Revenue Model   |
                    | - Data Cache      |
                    | - Config Manager  |
                    | - Alert Router    |
                    | - Web Scraper     |
                    +--------+----------+
                             |
              +--------------+--------------+
              |              |              |
     +--------v---+  +------v-----+  +-----v------+
     | Chartmetric|  | FaroLatino |  | Web/Other  |
     |    API     |  | Internal   |  |  Sources   |
     +------------+  +------------+  +------------+
```

### 9.2 Skills (User-Facing Workflows)

| Skill         | Trigger                                  | Maps To                            |
|---------------|------------------------------------------|------------------------------------|
| **Discovery** | `/discover` or scheduled                 | Mode 1 — Automatic Discovery       |
| **Evaluate**  | `/evaluate {artist name}`                | Mode 2 — On-Demand Evaluation      |
| **Analyze**   | `/analyze {artist name}`                 | Use Case 1 — Internal Analysis     |
| **Compare**   | `/compare {prospect} vs {managed}`       | Use Case 3 — Comparative Analysis  |
| **Prospect**  | `/prospect {country}`                    | Use Case 2 — Market Prospecting    |

### 9.3 MCP Tools (Reusable Components)

- **`chartmetric_auth`** — Token management (refresh to access token, auto-renewal before 1hr expiry)
- **`chartmetric_search`** — Artist search and ID resolution
- **`chartmetric_artist`** — Full artist data pull (metadata, cmStats, career, geo, playlists, tracks, etc.)
- **`chartmetric_discovery`** — Discovery queries (artist/list/filter, anr endpoints, track/list/filter)
- **`scoring_engine`** — Compute Prospect Score across 7 dimensions
- **`revenue_model`** — CPM-based revenue estimation
- **`data_cache`** — Read/write cached artist data
- **`config_manager`** — Load search criteria, profiles, alert rules, data source config
- **`alert_router`** — Route alerts to configured channels based on score tier and signal rules
- **`dossier_generator`** — Assemble structured artist dossier from scored data
- **`web_scraper`** — Google search for supplementary artist info

### 9.4 LLM-Agnostic Design

All AI prompts stored in config files:
- `prompts/scoring_rationale.txt` — prompt for generating score explanations
- `prompts/dossier_narrative.txt` — prompt for dossier text generation
- `prompts/discovery_analysis.txt` — prompt for analyzing discovery batch results
- `prompts/comparison.txt` — prompt for comparative analysis

Changing the LLM provider requires only updating the tool layer's LLM client — no changes to Skills, config, or prompts.

---

## 10. Three Use Cases

### Use Case 1 — Internal Artist Analysis

**Input:** Artist name (already managed by FaroLatino)
**Data sources:** Chartmetric (public) + FaroLatino internal (revenue, CPMs, deal terms)
**Output:** Enriched dossier cross-referencing public metrics with actual internal performance. Validates whether public metrics align with real revenue. Identifies optimization opportunities (e.g., "artist has growing audience in Brazil but no Deezer presence").

### Use Case 2 — New Market Prospecting

**Input:** Target country (e.g., Peru)
**Data sources:** Chartmetric only (public data)
**Output:** Ranked list of prospects in that market, scored and with dossiers. Uses `code2` filter on discovery endpoints, focuses D2 scoring on the target market.

### Use Case 3 — Comparative Analysis

**Input:** Prospect name + managed artist name
**Data sources:** Chartmetric (both artists) + FaroLatino internal (managed artist only)
**Output:** Side-by-side comparison of metrics, trajectories, revenue projections. Benchmarks prospect against a known quantity. Uses `similar-artists/by-configurations` for additional context.

---

## 11. Alert System

### 11.1 Score-Based Tiers

| Tier  | Score  | Action              | Delivery                           |
|-------|--------|---------------------|------------------------------------|
| HOT   | 85-100 | Immediate contact   | Real-time push (Email + WhatsApp)  |
| WARM  | 70-84  | Weekly review       | Daily digest (Email)               |
| WATCH | 55-69  | Passive tracking    | Weekly digest (Email)              |
| PASS  | <55    | Archive             | None (auto re-evaluate in 90 days) |

### 11.2 Signal-Based Alerts (Fire Regardless of Score)

Detected from Chartmetric data during scheduled scans:

- **Shazam spike** — `shazam_count` diff >200% (from cmStats or track/list/filter)
- **TikTok virality** — `tiktok_posts` or `tiktok_followers` spike (from cmStats)
- **Editorial playlist addition** — New editorial playlist placement (from playlists endpoint, `is_editorial=true`)
- **Career stage jump** — Artist moves up a career stage (from career endpoint)
- **Momentum surge** — Trend shifts to "explosive growth" (from career endpoint)
- **Notable collaboration** — Featuring with a mainstream artist (from tracks endpoint)

### 11.3 Delivery

v1 delivery mechanism: Email (via SMTP or API). WhatsApp integration is a configuration point — can use Twilio or similar, to be determined based on FaroLatino's existing tools.

---

## 12. API Call Budget (Mode 2 — Per Artist Evaluation)

To meet the <60s SLA for Mode 2, the following API calls are needed per artist:

- `search` (1 call) — Resolve name to CM ID
- `artist/:id` (1 call) — Metadata
- `artist/:id/cmStats` (1 call) — All platform metrics
- `artist/:id/career` (1 call) — Stage + momentum
- `artist/:id/cpp` (1 call) — Cross-platform score
- `artist/:id/where-people-listen` (1 call) — Spotify geo
- `artist/:id/social-audience-stats` (1 call) — Social geo
- `artist/:id/market-coverage-views/youtube` (1 call) — YT geo
- `artist/:id/tracks` (1 call) — Catalog + release dates
- `artist/:id/albums` (1 call) — Discography
- `artist/:id/:platform/:status/playlists` (2-3 calls) — Spotify + Apple Music playlists
- `artist/:id/:type/charts` (1-2 calls) — Chart appearances
- `artist/:id/milestones` (1 call) — Milestones
- `artist/:id/noteworthy-insights` (1 call) — Recent signals
- `artist/:id/neighboring-artists` (1 call) — Similar artists context
- `artist/:id/urls` (1 call) — Social links
- `artist/:id/stat/:source` (2-3 calls) — Time series (Spotify, YT)

**Total: ~20 API calls per evaluation.**

At typical API response times, 20 sequential calls should complete well within 60 seconds. Parallelization of independent calls (geo endpoints, catalog endpoints) can reduce wall-clock time further.

---

## 13. Milestones & Delivery

**Week 0 (Pre-work):**
Chartmetric API key obtained, FaroLatino internal data exported (CPMs, revenue, market tiers), cloud infra provisioned if needed. Depends on FaroLatino team.

**Weeks 1-2: Foundations**
MCP tools for Chartmetric API (auth, search, artist data pull, discovery), data cache layer, config system skeleton. Depends on API key.

**Weeks 3-4: Scoring Engine**
Scoring engine (all 7 dimensions), Mode 2 (Evaluate skill) working end-to-end, dossier generation. Depends on internal data for D3 calibration.

**May 5 — MILESTONE: Mode 2 functional for Colombia trip.** Depends on Weeks 1-4.

**Weeks 5-6: Discovery**
Mode 1 (Discovery skill) with scheduled scanning, alert system, dynamic filters, all 3 use cases.

**Weeks 7-8: Hardening & Handoff**
Dashboard/output layer, system hardening, preset search profiles, calibration validation (5 managed artists), documentation, knowledge transfer to Mariana's team.

---

## 14. Open Questions & Blockers

1. **FaroLatino internal data format and delivery method** (CPMs, revenue, market tiers)
   - Owner: Javier/Agustin + Mariana
   - Impact: Blocks D3 calibration and revenue model

2. **Chartmetric API plan tier** — rate limits affect Mode 1 batch processing speed
   - Owner: Mariana
   - Impact: Determines parallelization strategy

3. **WhatsApp delivery mechanism** — Twilio or other?
   - Owner: Mariana
   - Impact: Alert system implementation

4. **Meta/Instagram API feasibility** — is CM's social-audience-stats sufficient, or do we need direct Meta access?
   - Owner: Tomer (evaluate during weeks 1-2)
   - Impact: D6 scoring accuracy

5. **Spotify API access** — is save-to-stream ratio worth the integration effort for v1?
   - Owner: Tomer + Julio
   - Impact: D6 bot detection accuracy

6. **Cloud storage decision** — local cache vs. Supabase vs. R2
   - Owner: Tomer
   - Impact: Data persistence architecture

7. **Tier 1/2/3 market table** — which countries fall in which tier?
   - Owner: Julio
   - Impact: D2 Geographic Fit scoring

---

## 15. Out of Scope for v1

- CRM integration (architecture must support it later)
- Luminate, Viberate, Artist.Tools, Songstats integrations (extensible architecture only)
- Web frontend / dashboard UI (Skills + MCP is the deliverable; wrappable later)
- Apple Music geographic data (not available from Chartmetric)
- Multi-language UI (all outputs in English; Spanish adaptation is a post-v1 consideration)
- Automated deal negotiation or contract generation

---

## 16. Success Criteria

1. **Mode 2 delivers a scored dossier in <60 seconds** from artist name input
2. **Mode 1 produces a ranked list of 10-20 prospects** per weekly scan that Julio considers actionable
3. **Revenue model calibrates to ~10% deviation** against 5+ managed artists with known revenue
4. **Non-technical configuration:** Julio can modify search profiles, alert rules, and filters without code changes
5. **May 5 milestone met:** Real-time evaluation functional for Colombia trip
6. **Extensibility validated:** Documentation enables Mariana's team to add a new data source without consultant involvement
