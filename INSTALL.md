# Installing FaroAI

A short walkthrough from "open your web browser" to "use the app." About
5 minutes the first time. After that, you double-click the FaroAI icon
and it opens.

If a step doesn't work, jump to **Troubleshooting** at the bottom.

---

## What you'll need

- A Mac or Windows computer.
- An internet connection.
- The two **API keys** Tomer sent you in your welcome email:
  - An AI Model key (starts with `sk-ant-`, `sk-`, or `AIza`).
  - A Chartmetric refresh token (a long random string).

Keep both keys handy — you'll paste them into the app on first launch.

---

## Mac install

### Step 1 — Download FaroAI

1. Open your web browser.
2. Go to: **<https://github.com/TomerWeissman/farolatino/releases/latest>**
3. Scroll down to the **Assets** section.
4. Click **`FaroAI-v0.4.2.dmg`** to download (78 MB, ~30 seconds on a
   normal connection).

The file lands in your **Downloads** folder.

### Step 2 — Install the app

1. Double-click `FaroAI-v0.4.2.dmg`. A window appears showing a single
   `FaroAI` icon.
2. Drag that `FaroAI` icon onto your **Applications** folder. (You can
   open Applications via Finder → Applications, or just drag the icon
   into the sidebar.)
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

### Step 4 — Paste your keys

The Welcome screen shows two fields:

1. **AI Model** — paste the `sk-ant-…` / `sk-…` / `AIza…` key Tomer sent
   you. The app auto-detects which provider it's for.
2. **Chartmetric** — paste the long refresh token Tomer sent you.

Click **Continue**. You're in.

### Future launches

Double-click the FaroAI icon in Applications. No Terminal needed — the
unblock step from Step 3 is permanent.

---

## Windows install

### Step 1 — Download FaroAI

1. Open your web browser.
2. Go to: **<https://github.com/TomerWeissman/farolatino/releases/latest>**
3. Scroll down to the **Assets** section.
4. Click **`FaroAI-Setup-v0.4.2.exe`** to download (29 MB).

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

### Step 3 — Launch and paste your keys

1. **Double-click the FaroAI icon on your Desktop.** (Or click Start,
   type FaroAI, press Enter — same thing.)
2. The Welcome screen shows two fields. Paste:
   - **AI Model**: the `sk-ant-…` / `sk-…` / `AIza…` key Tomer sent.
   - **Chartmetric**: the long refresh token Tomer sent.
3. Click **Continue**. You're in.

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

## Switching the app to Spanish

Once you're inside FaroAI:

1. Click **Settings** in the left sidebar.
2. Under **Language**, click **Español**.

The interface and the assistant's responses both switch to Spanish on
the next message. Toggle back to English the same way. Your choice
persists across launches.

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
