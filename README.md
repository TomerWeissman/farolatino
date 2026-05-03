# FaroAI

The A&R assistant for **FaroLatino**, an independent Latin-music
distributor. Type an artist name → see a prospect score across 7
dimensions, a 12-month revenue projection, geographic profile, and tier
classification (HOT / WARM / WATCH / PASS).

Built on Chartmetric data, with optional Spotify and YouTube
integrations for cross-validation.

---

## Install (for the FaroLatino team)

**[→ Download the latest release](https://github.com/TomerWeissman/farolatino/releases/latest)**

Then follow [SETUP.md](SETUP.md) — 4 steps, ~10 minutes, mostly clicking
installers. The only Terminal command is `claude login` once.

You'll need:
- **Python 3.11+** ([download](https://www.python.org/downloads/))
- **Claude Code** ([download](https://claude.com/claude-code))
- **A Chartmetric refresh token** (paste it inside the app on first launch)

After install, double-click `start.command` (Mac) or `start.bat`
(Windows) any time you want to use the dashboard.

---

## What's inside

The dashboard ships with five tabs in the left sidebar:

- **FaroAI** — chat. Type `@evaluate <artist>` for a full dossier,
  `@similar <artist>` for comparable artists, or any free-form A&R
  question.
- **Skills** — view, edit, add, or delete the `@`-skills the chat uses.
- **Memory** — the persona / system prompt the assistant runs with,
  plus a reasoning history of past chats.
- **Files** — calibration YAMLs (revenue model, scoring profiles),
  cached Chartmetric responses, and the internal royalty datasets
  used for calibration.
- **Connections** — live status of every external API (Chartmetric,
  Spotify, YouTube). Click a row to add or update credentials inline.

---

## For developers

Clone the repo and use `scripts/start_dev.sh` for hot-reloading dev
mode (uvicorn `--reload` on `:8000`, Next.js dev server on `:3000`).

```bash
git clone https://github.com/TomerWeissman/farolatino.git
cd farolatino
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
./scripts/start_dev.sh
```

Tests:

```bash
pytest tests/ -q
```

Architecture notes are in [docs/](docs/).

### Repository layout

```
api/                # FastAPI backend (web layer; serves both /api and the SPA)
core/               # Pure-Python helpers (claude_runner, run_log, paths)
mcp_server/         # MCP tools the chat invokes (Chartmetric, scoring, revenue)
web/                # Next.js + Tailwind + shadcn frontend (web/out/ is committed)
config/             # Calibration YAMLs (scoring profiles, stream multipliers, ...)
data/               # Cached Chartmetric responses + internal datasets (gitignored)
.claude/skills/     # @-skill markdown files
scripts/            # build_release.sh, build_web.sh, start_dev.sh, test_wizard.sh
tests/              # pytest suite (61 tests covering scoring, revenue, composites)
```

### Building a release

```bash
./scripts/build_release.sh          # produces dist/farolatino-vX.Y.Z.zip
git tag v0.1.0 && git push --tags   # CI builds + uploads to GitHub Releases
```

---

## Contact

Questions, ideas, or running into something the troubleshooting section
of [SETUP.md](SETUP.md) doesn't cover: open an issue or DM Tomer.
