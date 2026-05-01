# Setup Guide — FaroLatino A&R Dashboard

A short, non-technical guide to running the dashboard on your computer. **You'll be done in 2-3 minutes the first time, ~10 seconds every time after.**

---

## What you're testing

A web dashboard for evaluating Latin music artists — type a name, see a revenue projection, prospect tier, and competitive landscape.

## What you need

1. **The folder you were sent** (contains the dashboard code + a pre-configured `.env` file with API access).
2. **Python 3.11 or later** installed on your computer. If you don't have it:
   - Download from <https://www.python.org/downloads/>
   - **On Windows:** during install, check the box that says "Add Python to PATH". (If you forget, just run the installer again.)
   - On Mac: the default installer works — no extra steps.

That's it. No Terminal commands, no editing files.

---

## Mac instructions

1. Unzip / open the folder you were sent.
2. **Double-click `start.command`.**
3. Terminal will open and run automatically. The first time, it spends ~60-90 seconds installing dependencies — you'll see lines scrolling. Subsequent runs take ~10 seconds.
4. Your browser will open to the dashboard automatically.

### If macOS warns "can't be opened from unidentified developer"

This happens once because the file isn't signed by Apple.

- **Right-click** (or Control-click) `start.command` → choose **Open**.
- A second warning will appear with an **Open** button — click it.
- Future double-clicks work normally.

---

## Windows instructions

1. Unzip / open the folder you were sent.
2. **Double-click `start.bat`.**
3. A black command-prompt window will open and run automatically. The first time, it spends ~60-90 seconds installing dependencies. Subsequent runs take ~10 seconds.
4. Your browser will open to the dashboard automatically.

### If Windows SmartScreen warns "Windows protected your PC"

- Click **More info**.
- Click the **Run anyway** button that appears.
- Future double-clicks work normally.

---

## What you'll see

When the dashboard loads:

- **Top:** "FaroLatino A&R Dashboard"
- **Sidebar:** a green "✓ Chartmetric connected" badge means the API is working.
- **Three tabs:**
  - **Evaluate** — type any artist's name, see a full report.
  - **Compare** — pick two artists, see them side-by-side.
  - **Similar** — pick an artist, see comparable peers.

Try typing **"Feid"** in the Evaluate tab to see a sample dossier.

---

## Stopping the dashboard

- **Mac:** close the Terminal window, or click into it and press `Ctrl+C`.
- **Windows:** close the command-prompt window.

---

## Restarting

Just double-click `start.command` (Mac) or `start.bat` (Windows) again. After the first run, dependencies are already installed — it'll launch in seconds.

---

## If something goes wrong

| What you see | What to do |
|---|---|
| "Python is not installed" | Install Python 3.11+ from <https://www.python.org/downloads/>, then double-click again. |
| "The .env file is missing" | The folder you received should include a `.env` file. If it's missing, ask Tomer to resend it. |
| Browser doesn't open automatically | Open <http://localhost:8501> manually in any browser. |
| Sidebar shows red "Token rejected" | Your `.env` file is invalid or expired. Ask Tomer for a fresh one. |
| Sidebar shows yellow "Connection issue" | Check your internet connection, then refresh the page. |
| Port 8501 already in use | Another copy is already running. Close other browser tabs / Terminal windows showing the dashboard. |

If none of these match, take a screenshot of whatever error you see and send it to Tomer.
