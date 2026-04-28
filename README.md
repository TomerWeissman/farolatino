# FaroLatino A&R Pipeline

AI-assisted artist scouting pipeline for FaroLatino, a Latin music distributor. Scores Latin artists on a 7-dimension Prospect Score, projects revenue potential, and produces investment-ready dossiers — all from Chartmetric data, surfaced as Claude Code skills via an MCP server.

Status: data-collection layer verified end-to-end against live Chartmetric. Scoring calibration and dossier tuning come next, ahead of the May 5, 2026 Colombia field test.

## Architecture

```
Claude Code skills (analyze/compare/discover/evaluate/prospect)
        |
        v
  MCP server (mcp_server/server.py)
        |
        +-- chartmetric_auth.py     # token refresh + 1 req/s throttle
        +-- chartmetric_search.py   # name/URL -> cm_id
        +-- chartmetric_artist.py   # 14-endpoint ArtistProfile
        +-- chartmetric_discovery.py
        +-- data_cache.py           # per-endpoint TTL cache
        +-- scoring/                # 7 dimension scorers + engine
        +-- revenue_model.py
        +-- dossier_generator.py
        +-- alert_router.py
        +-- config_manager.py
```

### Prospect Score (0-100)

| Dimension | Weight | Source |
|---|---|---|
| Momentum | 25% | streaming + social diff% |
| Geographic Fit | 20% | where-people-listen, market tiers |
| Revenue Potential | 20% | listeners x CPM rates |
| Timing | 15% | noteworthy-insights, milestones |
| Content Velocity | 8% | tracks endpoint (recent releases) |
| Engagement Quality | 7% | IG/TikTok engagement, follower:listener ratio |
| Platform Diversification | 5% | active platforms |

Four scoring profiles (`default`, `emerging_momentum`, `revenue_focus`, `latam_expansion`) re-weight the dimensions for different scouting briefs (see [config/profiles.yaml](config/profiles.yaml)).

Tier thresholds: HOT >=85, WARM >=70, WATCH >=55, PASS otherwise (see [config/alerts.yaml](config/alerts.yaml)).

## Setup

Requires **Python 3.11+** (developed on 3.14) and a Chartmetric refresh token.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fill in CHARTMETRIC_REFRESH_TOKEN at minimum (see Credentials below)
```

### Credentials

| API | What you need | Where to get it |
|---|---|---|
| **Chartmetric** (required) | refresh token | Chartmetric account → API settings → "Generate refresh token". For FaroLatino, request from Julio (`julio@farolatino.com`). |
| **Spotify** (optional, deferred) | `client_id` + `client_secret` | https://developer.spotify.com/dashboard → Create app → Web API. |
| **YouTube OAuth** (optional, deferred) | `client_id` + `client_secret` + refresh token | https://console.cloud.google.com → enable YouTube Data API v3 → create "OAuth client ID" of type **Desktop app** → run `python scripts/youtube_oauth_bootstrap.py`, paste the printed token into `.env`. |

Without Chartmetric, the test suite still runs (mocks); `collect_artist.py` will fail. Spotify and YouTube are wired but unused in v1.

## Usage

A standalone walkthrough for verifying every piece on a fresh machine lives in [TESTING.md](TESTING.md).

### Run the test suite (no credentials needed)

```bash
pytest tests/ -q
```

42 tests against fixtures in `tests/mock_data/`. Should pass on a fresh clone with no `.env`.

### Collect a full ArtistProfile from a name (needs Chartmetric)

```bash
python scripts/collect_artist.py "Feid"
```

Calls `search_artists`, picks the top match, fetches all 14 Chartmetric endpoints (~15s cold, throttled at 1 req/s), and dumps the assembled profile to `data/cache/collect_<cm_id>_<timestamp>.json`. Prints a coverage summary at the end.

### Use the MCP server in Claude Code

The skills in [.claude/skills/](.claude/skills/) wire the MCP tools into slash commands (`/evaluate`, `/discover`, `/compare`, `/prospect`, `/analyze`).

Register the MCP server with Claude Code (run from the project root):

```bash
claude mcp add farolatino -s user -- $(pwd)/venv/bin/python -m mcp_server.server
```

Then in Claude Code:

```
/evaluate "Ryan Castro"
```

To verify the server starts cleanly outside Claude Code:

```bash
python -m mcp_server.server   # should hang waiting for stdio input — Ctrl-C to exit
```

## Layout

```
mcp_server/         # MCP server: tools, scorers, models
config/             # YAML configs (profiles, market tiers, CPM rates, alerts)
prompts/            # Prompt templates for narrative outputs
scripts/            # CLI utilities (collect_artist, oauth_bootstrap)
tests/              # Pytest suite + mock fixtures
docs/PRD_v1.md      # Product requirements doc
.claude/skills/     # Claude Code slash commands (analyze, evaluate, ...)
```

## Data sources

Chartmetric is the single source of truth for v1. Per-artist enrichment hits 14 endpoints:

```
metadata, cmStats, career, cpp, stat/spotify, instagram-audience-stats,
milestones, neighboring-artists, albums, spotify_top_daily/charts,
spotify/current/playlists, tracks, where-people-listen, noteworthy-insights
```

Spotify Web API and YouTube Data API are wired but unused — deferred until a Chartmetric gap forces them.

## Operational notes

- Chartmetric hard rate limit is **1 req/s**; enforced module-wide in [mcp_server/tools/chartmetric_auth.py](mcp_server/tools/chartmetric_auth.py).
- All API responses are cached locally under `data/cache/<cm_id>/<endpoint>.json` with per-data-type TTLs (streaming stats: 1 day, tracks: 2 weeks, etc.).
- `.env` and OAuth tokens are gitignored; never commit credentials.
