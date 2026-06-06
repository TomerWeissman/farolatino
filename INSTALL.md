# Installing FaroAI

A short walkthrough from "open your web browser" to "use the app." About
5 minutes the first time. After that, you double-click the FaroAI icon
and it opens.

If a step doesn't work, jump to **Troubleshooting** at the bottom.

---

## What you'll need

- A Mac or Windows computer.
- An internet connection.
- The **setup file** Tomer sent you (e.g. `FaroAI-API-Keys.txt`) — a plain
  text file holding all your API keys. On first launch you upload it once
  and everything connects. (No file? You can paste keys manually instead —
  see Step 4.)

Keep that file handy — you'll upload it into the app on first launch.

---

## Mac install

### Step 1 — Download FaroAI

1. Open your web browser.
2. Go to: **<https://github.com/farolatino-app/farolatino/releases/latest>**
3. Scroll down to the **Assets** section.
4. Click the file ending in **`.dmg`** (named something like
   `FaroAI-v0.5.13.dmg` — the version number bumps over time). It's
   about 84 MB, ~30 seconds on a normal connection.

The file lands in your **Downloads** folder.

### Step 2 — Install the app

1. Double-click the `.dmg` you just downloaded. A window opens showing the
   **FaroAI** icon next to an **Applications** folder.
2. **Drag the FaroAI icon onto the Applications folder** in that window.
3. Eject the disk image: in Finder's left sidebar, click the small
   ⏏ next to `FaroAI`.

### Step 3 — Unblock the app (one-time, ~30 seconds)

Because FaroAI isn't signed by an Apple Developer account, macOS will
refuse to open it on the first try. We unblock it with a single
Terminal command. You only do this once per computer.

1. Press **Cmd + Space** to open Spotlight Search.
2. Type **Terminal** and press Enter. A small text window opens.
3. Click in the Terminal window, then **copy and paste this exact line**
   (don't retype it — copy from this page):

   ```
   xattr -cr /Applications/FaroAI.app 2>/dev/null; open /Applications/FaroAI.app
   ```

4. Press Enter.
5. FaroAI opens. You'll see a "Welcome to FaroAI" screen.

> If your Mac shows a dialog saying *"FaroAI is damaged and can't be
> opened"* before you run the Terminal command, **click Cancel — never
> "Move to Trash"** or the app will be deleted and you'll have to
> re-download. Cancel keeps the app in place; the Terminal command
> above unblocks it.

### Step 4 — Connect your APIs

The Welcome screen opens with an **"Upload the file you were sent"** box at
the top. The easy path:

1. **Drag the setup file** (`FaroAI-API-Keys.txt`) onto that box — or click
   **Choose file** and pick it. Everything connects at once: AI model,
   Chartmetric, Spotify, YouTube and Power BI.
2. Click **Continue**. You're in.

**No setup file?** Fill in the cards below the upload box instead: the **AI
Model** key is required; **Chartmetric** is recommended; paste the **5
`PBI_` Power BI codes** into the Power BI box; Spotify/YouTube are optional.

### Future launches

Double-click the FaroAI icon in Applications. No Terminal needed — the
unblock step from Step 3 is permanent.

---

## Windows install

### Step 1 — Download FaroAI

1. Open your web browser.
2. Go to: **<https://github.com/farolatino-app/farolatino/releases/latest>**
3. Scroll down to the **Assets** section.
4. Click the file starting with **`FaroAI-Setup-`** and ending in
   **`.exe`** (e.g. `FaroAI-Setup-v0.5.13.exe`). About 29 MB.

### Step 2 — Run the installer

1. Find the file in your Downloads folder. Double-click it.
2. Windows shows a blue **"Windows protected your PC"** dialog. This is
   normal — Windows is being cautious about an app it hasn't seen
   before. Click the small **More info** link near the top.
3. A blue **Run anyway** button appears at the bottom. Click it.
4. The installer runs. Click **Next** through the wizard, then
   **Install**, then **Finish**.

The installer drops a **FaroAI** icon on your **Desktop** and adds it
to the **Start Menu**.

### Step 3 — Launch and connect your APIs

1. **Double-click the FaroAI icon on your Desktop.** (Or click Start,
   type FaroAI, press Enter — same thing.)
2. On the Welcome screen, **upload the setup file** (`FaroAI-API-Keys.txt`)
   in the box at the top — drag it on or click **Choose file**. Everything
   connects at once.
3. Click **Continue**. You're in.

**No setup file?** Use the manual cards below the upload box — the **AI
Model** key is required; paste the **5 `PBI_` Power BI codes** into the
Power BI box; Chartmetric/Spotify/YouTube as available.

### Future launches

Double-click the FaroAI icon on your Desktop. That's it.

---

## Updates

When Tomer ships a new version, FaroAI can update itself in place — no
re-downloading installers.

1. Open FaroAI.
2. Click **Connections** in the left sidebar.
3. Scroll to the **Updates** section. Click **Check for updates**.
4. If a newer version is available, click **Apply**. The app downloads
   the changes (~1–5 MB), restarts, and you're on the new version.

---

## Language

FaroAI opens in **Spanish by default**. To switch to English (or back):

1. Click **Settings** in the left sidebar.
2. Under **Language**, pick **English** / **Español**.

The interface and the assistant's responses switch on the next message.
Your choice persists across launches.

---

## Troubleshooting

### Mac: "FaroAI cannot be opened" or the icon disappeared from Applications

You skipped Step 3 (the Terminal unblock command), or you clicked
"Move to Trash" on a Gatekeeper dialog by mistake. Re-download the
.dmg, drag FaroAI to Applications again, then run the Terminal
command from Step 3 BEFORE double-clicking the app.

### Mac: Terminal says "command not found" or shows a long error

You probably retyped the command instead of copying it. The line is:

```
xattr -cr /Applications/FaroAI.app && open /Applications/FaroAI.app
```

Copy the whole line — including the `&&` in the middle — paste it,
press Enter.

### Windows: SmartScreen has no "Run anyway" link

Some corporate Windows installs disable that button via Group Policy.
If you're on a managed work laptop, ask IT to allow the FaroAI
installer, or use a personal machine.

### Windows: Installer runs but the app doesn't open

After Finish, FaroAI should be in the Start Menu under "FaroAI". If it
isn't:
- Look in `C:\Program Files\FaroAI\` for `FaroAI.exe` and double-click.
- If even that doesn't open the app, your Windows Defender may have
  quarantined a file. Open Defender → "Protection history", look for a
  FaroAI entry, click **Restore** if found.

### "AI Model key not detected"

The key needs to be exact — no quotes around it, no leading/trailing
spaces. Paste from your email straight into the field.

### Anything else

Email or message Tomer. Include a screenshot of whatever screen you're
stuck on if you can — it makes debugging fast.
