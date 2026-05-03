# Setup Guide — FaroAI

A 4-step install for the FaroLatino A&R dashboard. Plan for ~10 minutes
the first time. After that, double-click and you're in.

You don't need to be technical. The only Terminal command you'll ever
type is `claude login` — once.

---

## Step 1 — Download FaroAI

Open the [Releases page](https://github.com/TomerWeissman/farolatino/releases/latest)
and download `farolatino-vX.Y.Z.zip`. Double-click the zip to unpack it
into a folder. Drag that folder somewhere stable — your `Documents`
folder is a fine home.

> **Mac**: the first time you run anything inside, macOS may say "this
> can't be opened because the developer can't be verified." Right-click
> the script → **Open** → confirm. Only needed once.
>
> **Windows**: SmartScreen may say "Windows protected your PC." Click
> **More info** → **Run anyway**. Only needed once.

## Step 2 — Install Python 3.11+

Open <https://www.python.org/downloads/> and click the big yellow
**Download Python** button. Run the installer.

> **Windows specifically**: tick the **Add Python to PATH** checkbox at
> the bottom of the installer's first screen. If you forget, re-run the
> installer and tick it.

To check it worked: open Terminal (Mac) or PowerShell (Windows) and
type `python3 --version` (Mac) or `python --version` (Windows). You
should see `Python 3.11.x` or higher.

## Step 3 — Install Claude Code

Open <https://claude.com/claude-code> and follow the install
instructions for your platform. Then in a Terminal / PowerShell window,
run once:

```
claude login
```

Follow the browser prompts to sign in to your Anthropic account. This
is the only Terminal command you'll need to type.

## Step 4 — Launch FaroAI

In the FaroAI folder you unzipped:

- **Mac**: double-click `start.command`.
- **Windows**: double-click `start.bat`.

A Terminal window opens, runs setup (~60s the first time, ~5s
afterward), and your browser opens automatically to the dashboard.

> If the Terminal window says "Python isn't installed" or "Claude Code
> isn't installed", scroll back up — those mean Step 2 or 3 didn't
> stick. Fix and double-click again.

---

## Step 5 (in the app) — Add your API keys

When FaroAI first opens you'll see the chat. Click **Connections** in
the left sidebar. Each row is one external service:

- **Chartmetric** — required. Click the row to expand it, paste your
  refresh token, click **Save**. The status badge flips green.
- **Spotify, YouTube** — optional. Add them the same way for richer
  cross-validation when you ask FaroAI about an artist.

That's it. Click **FaroAI** in the sidebar to go back to the chat and
ask `@evaluate Bad Bunny` or any artist name.

---

## Quitting

Close the Terminal window where `start.command` / `start.bat` is
running, or hit `Ctrl+C` inside it. The browser tab can stay open —
it'll just show a connection error until you launch again.

## Updating

Download the new release zip from the same Releases page. Replace the
folder. Your API keys live in `.env` inside the folder, so re-using the
old `.env` keeps your credentials. (Or just add them again from the
Connections page — takes a minute.)

## Troubleshooting

| What you see | What it means | Fix |
|---|---|---|
| Terminal closes immediately | Probably a "Python not installed" error you missed | Double-click again, watch the Terminal window — the message stays up until you press Enter |
| "Address already in use" | A previous FaroAI is still running | Quit the old Terminal window, then double-click again — the launcher kills stale processes automatically on relaunch |
| Browser opens to "This site can't be reached" | Launcher hasn't finished booting yet | Wait ~5 seconds, refresh the page |
| Chat says "Backend closed the stream..." | Connection issue between the page and the launcher | Quit Terminal + relaunch |

If you're stuck, send a screenshot of the Terminal window — it has the
error message verbatim, which is enough for me to debug remotely.
