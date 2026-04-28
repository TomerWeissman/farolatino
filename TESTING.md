# Testing on a Fresh Machine

Step-by-step walkthrough for verifying each piece of the FaroLatino A&R pipeline works on a fresh clone. Follow top to bottom — each section either works without credentials or tells you which one it needs.

## 1. Clone and install (no credentials needed)

```bash
git clone https://github.com/TomerWeissman/farolatino.git
cd farolatino
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Verify:**
```bash
python -c "from mcp_server.server import mcp; print('OK')"
```
Should print `OK`. If you see an `ImportError`, your Python is too old (need 3.11+).

## 2. Run the test suite (no credentials needed)

```bash
pytest tests/ -q
```

**Expected:** `42 passed` in under a second. These cover the 7 dimension scorers, dossier generator, revenue model, and alert router against mock fixtures in `tests/mock_data/`.

If any fail on a fresh clone, that's a real bug — open an issue.

## 3. Set up credentials

```bash
cp .env.example .env
```

Open `.env` and fill in **at minimum**:

```
CHARTMETRIC_REFRESH_TOKEN=<from Chartmetric API settings>
```

Everything else (Spotify, YouTube, SMTP, Twilio) is optional for v1. Skip them.

**Verify Chartmetric auth works:**
```bash
python -c "
from mcp_server.tools.chartmetric_auth import get_access_token
print('Access token len:', len(get_access_token()))
"
```
Should print `Access token len: 200+`. If you get a `ConnectionError`, the refresh token is wrong or expired.

## 4. Search for an artist (1 API call)

```bash
python -c "
from mcp_server.tools.chartmetric_search import search_artists
import json
print(json.dumps(search_artists('Feid', limit=3), indent=2))
"
```

**Expected:** JSON with `count: 3` and three Feid candidates (the right one has `cm_id: 152776`).

This proves: Chartmetric auth → API call → JSON parse all work.

## 5. Pull a full ArtistProfile (14 API calls, ~15 seconds)

```bash
python scripts/collect_artist.py "Feid"
```

When prompted, press Enter to pick the top match.

**Expected:**
- `Done in 14.x s` (cold). Re-running on the same artist takes <1s thanks to the per-endpoint cache.
- Long JSON dump of the `ArtistProfile` to stdout.
- A coverage summary at the end:
  ```
  data_completeness: 1.0
  populated (16/16): name, genres, career_stage, ...
  missing/empty: (none)
  ```
- A file at `data/cache/collect_152776_<timestamp>.json` you can inspect with any JSON viewer.

This proves the full data-collection layer is healthy: rate-limit throttle, all 14 endpoints, cache, and field normalization.

**Three good test artists** (cover different career stages):
- `Feid` — superstar (cm_id 152776)
- `Ryan Castro` — rising mid-tier (cm_id 1045417)
- `Blessd` — superstar (cm_id 1776209)

## 6. Run the MCP server standalone

```bash
python -m mcp_server.server
```

The process will hang waiting for stdio input — that's correct. The MCP server speaks JSON-RPC over stdin/stdout. **Press Ctrl-C to exit.**

If it crashes immediately, something is wrong with the imports — check `pytest` first.

## 7. Use the MCP server inside Claude Code

(Optional — only if you have Claude Code installed.)

Register the server (from the project root):

```bash
claude mcp add farolatino -s user -- $(pwd)/venv/bin/python -m mcp_server.server
```

Then in any Claude Code session:

```
/evaluate "Ryan Castro"
```

The skill will route through the MCP server, which calls `search_artists` → `get_artist_data` → `compute_prospect_score` → `generate_dossier` and prints a written analysis.

To unregister later:
```bash
claude mcp remove farolatino
```

## 8. (Optional) YouTube OAuth bootstrap

Only needed if you plan to query YouTube data directly (not used in v1).

```bash
python scripts/youtube_oauth_bootstrap.py
```

Walks you through the browser OAuth dance, then prints:
```
YOUTUBE_REFRESH_TOKEN=1//0...
```
Paste that line into your `.env`.

## What to expect from caching

After step 5, the cache layout is:

```
data/cache/
├── 152776/                        # cm_id directory, raw API responses
│   ├── metadata.json              # 1 day TTL
│   ├── tracks.json                # 2 weeks TTL
│   ├── where_people_listen.json   # 1 week TTL
│   └── ... (14 files total)
└── collect_152776_<timestamp>.json  # full assembled ArtistProfile
```

Re-running `collect_artist.py` on the same artist within the TTL window won't hit the API. To force a fresh fetch, delete the cm_id directory.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `ModuleNotFoundError: mcp_server` | Run from project root, or activate the venv. |
| `ConnectionError: Chartmetric auth failed (HTTP 401)` | Wrong/expired refresh token in `.env`. |
| `HTTP 429` while collecting | Throttle is set to 1.05 req/s — this shouldn't happen. If it does, raise `_MIN_REQUEST_INTERVAL` in `mcp_server/tools/chartmetric_auth.py`. |
| `collect_artist.py` exits without prompting | Probably an exception during `search_artists`. Re-run with the cm_id directly: `python scripts/collect_artist.py 152776`. |
| Tests pass but `collect_artist.py` returns empty fields | Chartmetric coverage gap for that specific artist — try a more popular one. |
