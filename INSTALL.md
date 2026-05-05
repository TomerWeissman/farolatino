# Installing FaroAI — Step-by-Step

A no-jargon walkthrough from "open your web browser" to "use the app".
About 15–20 minutes the first time. After that, double-click an icon and
you're in.

If a step doesn't work, jump to **Troubleshooting** at the bottom.

---

## What you'll need before starting

- A computer running macOS or Windows.
- An internet connection.
- An **Anthropic account** — free, you'll create one in Step 4 if you
  don't already have one. No credit card required.
- A **Chartmetric refresh token** — you already have this. Keep it handy
  in a notes app; you'll paste it in the very last step.

That's it. No paid subscriptions, no developer tools.

---

## Step 1 — Download FaroAI from GitHub

1. Open your web browser (Safari, Chrome, Edge — any works).
2. Go to: **<https://github.com/TomerWeissman/farolatino/releases/latest>**
3. The page will be titled with a version number, e.g. "v0.1.0". Scroll
   down to the **Assets** section.
4. Click **`farolatino-v0.1.0.zip`** to download it.
5. Find the file in your **Downloads** folder.
   - **Mac**: open Finder → Downloads.
   - **Windows**: open File Explorer → Downloads.
6. Double-click the `.zip` to unzip it. You'll get a folder named
   `farolatino-v0.1.0`.
7. Move that folder somewhere you can find again — your **Documents**
   folder is a good choice.

> If the Releases page doesn't show a `.zip` file, message Tomer — a
> release may not have been published yet.

---

## Step 2 — Install Python

Python is the language FaroAI runs on. Install it once, forget it
exists.

1. Go to **<https://www.python.org/downloads/>**
2. Click the big yellow **Download Python 3.x** button (anything 3.11 or
   higher works).
3. Open the downloaded installer.

### On Mac

- Double-click the installer and click **Continue** through every
  screen, then **Install**.

### On Windows

- **IMPORTANT**: on the very first screen of the installer, check the
  box that says **Add Python to PATH** before clicking Install. If you
  forget, run the installer again and tick it.

### Check it worked

You'll need to open Terminal (Mac) or PowerShell (Windows). If you've
never done this:

- **Mac**: press `Cmd + Space`, type `Terminal`, press Enter. A small
  black window appears.
- **Windows**: press the Windows key, type `PowerShell`, press Enter. A
  blue window appears.

In that window, type this exactly and press Enter:

```
python3 --version
```

(On Windows, type `python --version` instead.)

You should see something like `Python 3.11.5`. If you get "command not
found":

- **Mac**: close Terminal, reopen it, try again.
- **Windows**: re-run the Python installer and tick **Add Python to
  PATH**.

You can close the Terminal/PowerShell window after this check.

---

## Step 3 — Install Node.js

FaroAI uses Claude Code as its AI engine, and Claude Code needs Node.js.
Same drill — install once and forget it.

1. Go to **<https://nodejs.org/>**
2. Click the big green **LTS** download button on the left.
3. Open the installer and click **Continue** / **Next** through every
   screen — don't change any defaults.

To verify, open Terminal/PowerShell again (close any old window first
so it picks up the new install) and type:

```
node --version
```

You should see `v20.x.x` or similar.

---

## Step 4 — Install Claude Code

Claude Code is the AI engine FaroAI uses to answer questions.

1. Go to **<https://claude.com/claude-code>**
2. Follow the install steps on that page. Usually it's a single command
   you paste into Terminal/PowerShell.
3. Once it finishes, in the same Terminal/PowerShell window, type:

   ```
   claude login
   ```

4. Your web browser will open. Sign in with an **Anthropic account**.
   If you don't have one, click **Sign up** — it's free, no credit card.
5. Approve the permissions Claude Code requests.
6. Go back to Terminal — it should say something like "Logged in".

You only do this **once**. Future FaroAI launches don't need it.

---

## Step 5 — Launch FaroAI

The setup is done. Now to actually start the app:

### On Mac

1. Open Finder and navigate to the `farolatino-v0.1.0` folder.
2. Find the file called `start.command`.
3. **Right-click** it and choose **Open**. (On a trackpad, "right-click"
   means a two-finger tap, or hold the `Control` key while clicking.)
4. macOS will ask "Are you sure you want to open it?" — click **Open**.

> The right-click is only needed the very first time. After that, you
> can double-click normally.

### On Windows

1. Open File Explorer and navigate to the `farolatino-v0.1.0` folder.
2. Find the file called `start.bat`.
3. **Double-click** it.
4. Windows SmartScreen may say "Windows protected your PC" — click
   **More info** → **Run anyway**.

### What happens next

A Terminal window opens and shows progress messages. The first launch
takes about **60 seconds** while it sets things up; subsequent launches
take ~5 seconds.

When ready, your web browser opens automatically to the FaroAI
dashboard. **Don't close the Terminal window** — closing it shuts the
app down. Just minimize it and forget about it.

---

## Step 6 — Paste your Chartmetric token (in the app)

The dashboard is open. Last step:

1. In the left sidebar, click **Connections**.
2. You'll see rows for Chartmetric, Spotify, YouTube. Click the
   **Chartmetric** row to expand it.
3. Paste your Chartmetric refresh token into the text box.
4. Click **Save**. The status indicator on that row should turn green
   and say "ok".
5. Click **FaroAI** at the top of the sidebar to return to the chat.

That's it. Try typing **`@evaluate Bad Bunny`** to see a full artist
dossier.

---

## Day-to-day use

- **Start FaroAI**: double-click `start.command` (Mac) or `start.bat`
  (Windows). Browser opens automatically. Takes ~5 seconds.
- **Stop FaroAI**: close the Terminal window. Your browser tab can stay
  open — it'll just show a connection error until you relaunch.
- **Update FaroAI**: when a new release comes out, download the new
  `.zip` from GitHub the same way as Step 1, unzip it, and replace your
  old folder. Your Chartmetric token lives in a hidden file inside the
  folder; the easiest way to keep it is to re-paste it in the
  Connections page after updating.

---

## Troubleshooting

| What you see | What it means | What to do |
|---|---|---|
| Terminal/PowerShell closes the moment it opens | Something's missing — usually Python or Claude Code | Re-launch `start.command` / `start.bat`, watch the window for the actual error message |
| Window says "Python isn't installed" | Step 2 didn't take | Re-do Step 2; on Windows make sure **Add Python to PATH** is ticked |
| Window says "Claude Code isn't installed" | Step 4 didn't take | Re-do Steps 3 and 4 |
| `claude: command not found` when running `claude login` | Either Node.js or Claude Code isn't on your PATH | Restart Terminal/PowerShell, retry. If still failing, redo Steps 3 and 4 |
| Browser shows "This site can't be reached" | The launcher is still booting | Wait 5 seconds, refresh the browser tab |
| "Address already in use" | A previous FaroAI is still running | Quit its Terminal window, relaunch |
| Chat says "Backend closed the stream..." | Connection to the launcher dropped | Quit Terminal, relaunch |
| Connections page shows Chartmetric as red | Token is wrong or expired | Re-paste it; if still red, the token has been rotated — ask Tomer for a new one |

Still stuck? Take a screenshot of the Terminal window (the error
message is shown verbatim there) and send it to Tomer. That's almost
always enough to debug remotely.

- **Screenshot on Mac**: `Cmd + Shift + 4`, drag a box around the
  Terminal window. The image saves to your Desktop.
- **Screenshot on Windows**: press `PrtScn` (or `Win + Shift + S` for a
  selection box), then paste into a chat or email.

---

## What you can safely ignore

- The hidden **`.env`** file inside the FaroAI folder. The Connections
  page in the app handles everything inside it for you.
- The other subfolders (`api`, `core`, `web`, …) — those are the app's
  source code. Don't move or rename them.

Welcome to FaroAI.
