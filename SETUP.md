# Setup Guide — FaroAI

Get FaroAI running on your computer. The only Terminal command you'll
ever type is `claude login`, and only once. Plan for ~10 minutes the
first time; after that, double-click and you're in.

---

## 1. Download FaroAI

Open the [Releases page](https://github.com/TomerWeissman/farolatino/releases/latest)
and download `farolatino-vX.Y.Z.zip`. Double-click to unpack, then
drag the folder somewhere stable — `Documents` is fine.

## 2. Install Python 3.11+

Go to <https://www.python.org/downloads/> and click the big yellow
**Download Python** button. Run the installer.

> **Windows**: tick **Add Python to PATH** on the installer's first
> screen. If you forget, re-run the installer and tick it.

To check: open Terminal (Mac) or PowerShell (Windows) and run
`python3 --version` (Mac) or `python --version` (Windows). You should
see `Python 3.11.x` or higher.

## 3. Install Claude Code

Go to <https://claude.com/claude-code> and follow the install steps
for your platform. Then, in Terminal / PowerShell, run once:

```
claude login
```

Follow the browser prompts to sign in. That's the only Terminal
command you need.

## 4. Launch FaroAI

Inside the FaroAI folder:

- **Mac**: double-click `start.command`.
- **Windows**: double-click `start.bat`.

A Terminal window opens and runs setup (~60s the first time, ~5s
afterward). Your browser opens to the dashboard automatically.

> First time only — the OS may warn about an unverified developer.
> **Mac**: right-click `start.command` → **Open** → confirm.
> **Windows**: SmartScreen → **More info** → **Run anyway**.

## 5. Add your API keys (in the app)

When FaroAI opens, click **Connections** in the left sidebar. Each row
is one external service:

- **Chartmetric** — required. Expand the row, paste your refresh
  token, click **Save**. The badge flips green.
- **Spotify, YouTube** — optional. Add them the same way for richer
  cross-validation.

Click **FaroAI** in the sidebar to go back to the chat. Try
`@evaluate Bad Bunny` to see a full dossier.

---

## Quitting

Close the Terminal window, or hit `Ctrl+C` inside it. The browser tab
can stay open — it'll show a connection error until you relaunch.

## Updating

Download the new release zip and replace the folder. Your API keys
live in `.env` inside the folder; copy that file over to keep your
credentials, or re-add them from the Connections page.

## Troubleshooting

| What you see | Fix |
|---|---|
| Terminal closes immediately | Re-launch and watch for a "Python not installed" or "Claude Code not installed" message |
| "Address already in use" | A previous FaroAI is still running. Quit its Terminal window and relaunch — the launcher cleans up stale processes |
| Browser shows "This site can't be reached" | Launcher is still booting. Wait ~5s and refresh |
| Chat says "Backend closed the stream..." | Connection between the page and the launcher dropped. Quit Terminal and relaunch |

Stuck? Screenshot the Terminal window — the error is verbatim and
that's usually enough to debug remotely.
