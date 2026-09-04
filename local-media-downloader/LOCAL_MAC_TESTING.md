# Testing Local Media Downloader on macOS

Exact commands to install, run, and manually test the app on a Mac. Run all
commands from a Terminal (`Terminal.app`, iTerm, etc.) unless noted.

Every command below assumes you're in the project root — the folder
containing `backend/`, `frontend/`, `scripts/`, and this file. Replace
`~/local-media-downloader` with wherever you actually cloned/unzipped it.

```bash
cd ~/local-media-downloader
```

---

## 1. Install dependencies

### 1a. Homebrew (skip if already installed)

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 1b. Python, Node, and FFmpeg

```bash
brew install python@3.12 node ffmpeg
```

Apple Silicon Macs install Homebrew to `/opt/homebrew`; Intel Macs to
`/usr/local`. Either way `brew install` puts `ffmpeg` on your `PATH`
automatically for new terminal sessions.

### 1c. Verify versions

```bash
python3 --version   # 3.12.x or newer (3.11 also works)
node --version       # v18 or newer
ffmpeg -version | head -1
```

### 1d. Backend Python dependencies

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ..
```

### 1e. Frontend Node dependencies

```bash
cd frontend
npm install
cd ..
```

---

## 2. Check FFmpeg is actually found by the app

The backend looks for `ffmpeg` on `PATH`, then falls back to
`/opt/homebrew/bin/ffmpeg` and `/usr/local/bin/ffmpeg` if it isn't on `PATH`
(common when launching from a GUI rather than a terminal). Confirm it
resolves correctly:

```bash
which ffmpeg
```

If that prints nothing, Homebrew's shell integration probably isn't loaded
in your shell profile. Run this once (Apple Silicon):

```bash
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
```

or on Intel Macs:

```bash
echo 'eval "$(/usr/local/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/usr/local/bin/brew shellenv)"
```

Then open a new terminal tab and re-run `which ffmpeg`.

---

## 3. Start the app

### Easiest: the startup script

```bash
./scripts/start.sh
```

This creates the venv if missing, installs/updates dependencies, checks
FFmpeg, starts the backend on `http://127.0.0.1:8000`, starts the frontend
on `http://127.0.0.1:5173`, and opens your browser automatically. Leave the
terminal window open — closing it (or `Ctrl+C`) stops both servers.

### Manual: two terminal tabs

**Tab 1 — backend:**

```bash
cd backend
source .venv/bin/activate
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Tab 2 — frontend:**

```bash
cd frontend
npm run dev
```

Then open **http://127.0.0.1:5173** in your browser.

### Confirm the backend is healthy

```bash
curl -s http://127.0.0.1:8000/api/health | python3 -m json.tool
```

Expect `"status": "ok"`, `"ffmpeg_available": true`, and
`"database_ok": true`. The same info shows as green/amber dots in the app's
header. If `ffmpeg_available` is `false`, the app itself will show a
first-run setup screen with install instructions — go back to step 2.

---

## 4. Manual test checklist

For each platform test, paste the URL into the big input on the Dashboard
and click **Analyze**, confirm the preview card (thumbnail, title, uploader,
duration) looks right, then proceed as described.

> Use your own content, or content you know you're allowed to download
> (your own uploads, Creative Commons / public domain clips, etc.). Only
> download things you actually have the right to save.

### 4a. YouTube (video)

1. Paste a public YouTube video URL, e.g. `https://www.youtube.com/watch?v=<id>` or a `youtu.be/<id>` short link.
2. Click **Analyze** — the preview card and quality presets (2160p/1440p/…/360p, greyed out for resolutions that don't exist for that video) should appear.
3. Leave quality on **Best Available**, click **Start Download**.
4. Watch it move through **Downloading → Completed** in "Active & Recent Downloads", with a live percentage, speed, and ETA.
5. Open **Downloads** in the header — the completed row should show a working **Open file** and **Open folder** button (these call macOS `open` under the hood).

### 4b. TikTok

1. Paste a TikTok video URL, e.g. `https://www.tiktok.com/@<user>/video/<id>` (or a `vm.tiktok.com/<code>` short link).
2. Analyze, then download at **Best Available**.
3. TikTok videos are usually already a single muxed file — you should see it move straight from Downloading to Completed with no separate "Merging" stage.

### 4c. Instagram

1. Paste an Instagram Reel or post URL you have the right to download, e.g. `https://www.instagram.com/reel/<id>/`.
2. If it's your own content or something public, Analyze should work with no cookies configured.
3. If you get a **"private or requires a logged-in session"** error on content you can see while logged into Instagram in your own browser, see §4g (cookies) below.

### 4d. Facebook

1. Paste a public Facebook video/watch URL or an `fb.watch/<code>` short link.
2. Facebook is the platform most likely to require a login even for content that looks public — if analysis fails with a login-required message, again see §4g.

### 4e. MP3 audio download

1. Analyze any YouTube/TikTok video.
2. In the format panel, switch to the **Audio Only** tab, select **MP3**, pick a bitrate (128/192/256/320 kbps).
3. Start the download. Stage should go **Downloading → Converting → Completed** (the "Converting" stage is FFmpeg doing the MP3 encode).
4. Open the finished file — it should play as an actual MP3, and (if "Embed thumbnail into downloaded audio files" is on in Settings) show cover art in your player/Finder preview.
5. Confirm the *un*checked case too: turn off "Embed thumbnail" and "Save thumbnail" in Settings, download another MP3, and check the download folder has **no leftover `.jpg`/`.webp` file** next to it (this was a real bug we fixed — a stray thumbnail file used to get left behind).

### 4f. 1080p video + audio merging

1. Analyze a YouTube video that actually has a separate 1080p video-only stream (most videos over a few minutes long do).
2. Select **1080p** explicitly (not "Best Available") and start the download.
3. You should see the stage move **Downloading → Merging → Completed** — "Merging" is FFmpeg muxing the separately-downloaded video and audio streams into one file.
4. Play the finished file and confirm both picture *and* sound are present (a broken merge is usually silent video or an error, not a video that "looks fine but plays with no audio" — but check anyway).
5. Open **Settings → Video → Preferred container** and set it to **MKV**, then repeat with a different video — the merged output should be a `.mkv` file this time.

### 4g. Cancellation

1. Start a download of a reasonably large/long video (bigger files give you more time to click Cancel before it finishes).
2. While it's in the **Downloading** stage, click **Cancel** on that item.
3. It should move to **Cancelled** within a second or two, and the partially-downloaded file should be gone from the download folder (check Finder, or click **Downloads** in the header — a cancelled row has no "Open file" button since there's nothing to open).
4. From the **Downloads** page, click **Retry** on the cancelled row — it should re-queue with the same options and either complete or let you cancel again.
5. Also try cancelling right as a download finishes downloading but is still merging/converting (harder to time exactly) — the app is written to still honor a cancel clicked during that window: the job ends up **Cancelled**, and the file FFmpeg just finished writing gets deleted rather than being kept while the UI says "cancelled."

### 4h. Browser cookies (for private/login-required content)

Cookies never leave your computer — the backend reads them locally via
yt-dlp's normal cookie mechanisms and only ever uses them to talk to the
platform itself, exactly like your browser would.

1. Log into Instagram or Facebook in your normal browser (Chrome, Firefox, Edge, or Safari) so a valid session cookie exists.
2. **Fully quit that browser first** — Chrome/Firefox lock their cookie database while running, which can make yt-dlp fail to read it.
   * Chrome: `Cmd+Q` from the Chrome menu (not just closing the window)
   * Firefox: `Cmd+Q`
3. In the app, go to **Settings → Authentication → Cookie source** and pick your browser (Chrome / Firefox / Edge / Safari).
4. Go back to Dashboard and re-analyze the URL that previously failed with a login-required error. It should now succeed if your logged-in account can actually see that content.
5. Alternative: export cookies to a Netscape-format `cookies.txt` file (e.g. with a browser extension like "Get cookies.txt") and set **Cookie source → Cookie file**, then paste the full path (e.g. `/Users/you/Downloads/cookies.txt`) into the field that appears. The app validates the file actually exists when you save.
6. Sanity check that nothing sensitive is ever printed anywhere:
   ```bash
   grep -i "cookie" data/logs/app.log
   ```
   This should show at most the *fact* that a cookie file or browser source was used in a log line — never an actual cookie value.

---

## 5. Automated tests, lint, and build

Run these to confirm the app is internally healthy without needing a browser:

```bash
# Backend: 99 tests, yt-dlp itself is mocked (no network calls)
cd backend
source .venv/bin/activate
python -m pytest -q
cd ..

# Frontend: type-check, lint, unit tests, production build
cd frontend
npm run typecheck
npm run lint
npm run test
npm run build
cd ..
```

All four frontend commands and the backend test run should finish with no
errors.

---

## 6. Troubleshooting common yt-dlp errors

The app translates yt-dlp/network errors into a short, friendly message with
a collapsible **"Show technical details"** section underneath it — that
technical text is the real underlying yt-dlp error and is the fastest way to
diagnose an issue. `data/logs/app.log` has the same detail plus history.

| Symptom | Likely cause | Fix |
|---|---|---|
| "This URL isn't supported" | Domain isn't YouTube/TikTok/Instagram/Facebook, or a typo in the URL | Double-check the URL; only these four platforms are supported |
| "This content is private or requires a logged-in session" | Private video, or platform is rate-limiting anonymous requests | Add browser cookies (§4g) if you actually have access |
| "This content is age-restricted" | Age-gated video with no cookies configured | Log in as an adult account in your browser and use cookies |
| "This content is not available in your region" | Geo-restriction | Nothing the app can/should do — this is a real access control, not a bug |
| "FFmpeg is required... was not found" | FFmpeg not installed or not resolvable | Re-run §1b/§2 above |
| "Permission denied writing to the download folder" | Chosen download folder isn't writable (e.g. inside a read-only volume, or macOS blocked Terminal's folder access) | Pick a different folder in Settings, or grant Terminal "Files and Folders" access in **System Settings → Privacy & Security** |
| "The download destination is out of disk space" | Disk actually full | Free up space or change the download folder |
| Video downloads but has no audio, or download fails during "Merging" | FFmpeg couldn't merge — often an FFmpeg version mismatch | Run `brew upgrade ffmpeg`; check `ffmpeg -version` is a reasonably recent build |
| "Failed to extract any player response" / similar YouTube extractor errors | yt-dlp is out of date — YouTube changes frequently and old yt-dlp versions break within weeks | `cd backend && source .venv/bin/activate && pip install --upgrade yt-dlp` |
| Cookie-based download still fails after setting cookies | Browser was still running when cookies were read, or you're not actually logged in with access to that content | Fully quit the browser first (§4g step 2); confirm you can see the content in that same browser |
| "Could not read the configured cookie file" | Cookie file path is wrong or the file was deleted/moved | Re-check the path in Settings → Authentication |
| App shows "Could not reach the local backend" | Backend isn't running, or something else is using port 8000 | Confirm Tab 1 (backend) is still running; `lsof -i :8000` to see what's bound to that port |
| Downloads seem to silently stop after a Mac sleep/wake or force-quit | The app was killed mid-download | On next backend startup, any download stuck "in progress" is automatically marked **Failed** (not silently lost) and shows a **Retry** button in History |

### Updating yt-dlp

Because platforms change their sites frequently, this is the single most
common fix for "it used to work and now it doesn't":

```bash
cd backend
source .venv/bin/activate
pip install --upgrade yt-dlp
```

The version currently installed is shown in **Settings → Advanced → yt-dlp
version**, and also in `/api/health`.
