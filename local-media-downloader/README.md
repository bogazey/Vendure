# Local Media Downloader

A local-only web app for downloading publicly accessible media from YouTube,
TikTok, Instagram, and Facebook by pasting a URL. Everything runs on your own
machine — there is no cloud service, no account, and no paid API involved.

> **This is the `commercial-v1` branch.** It adds an account/billing/plans
> layer (Free/Pro/Creator, Paddle Sandbox checkout, credit-based usage
> limits) on top of everything below, which still describes the core
> downloader itself. For the commercial layer specifically, see
> [`COMMERCIAL_ARCHITECTURE.md`](./COMMERCIAL_ARCHITECTURE.md) and
> [`PADDLE_SANDBOX_TESTING.md`](./PADDLE_SANDBOX_TESTING.md). The original
> single-user, no-account version of this app lives on the
> `personal-stable` branch (tag `personal-v1-working`) and is unaffected by
> any of this.

> **Use responsibly.** This tool is for downloading content you are lawfully
> allowed to access and save (your own uploads, public domain media, content
> whose creator permits downloading, etc.). It does not circumvent DRM,
> paywalls, or authentication systems. Private/login-required content only
> works if you supply your own browser cookies, exactly as your browser would
> send them.

## Screenshots

_Add screenshots of the Dashboard, format selection, live download queue, and
Settings page here once you've run the app locally._

- `docs/screenshots/dashboard.png`
- `docs/screenshots/download-queue.png`
- `docs/screenshots/settings.png`

## Features

- Paste a URL and auto-detect the platform (YouTube, TikTok, Instagram, Facebook)
- Metadata preview: thumbnail, title, uploader, duration, description
- Simple quality presets (2160p → 360p, Best Audio, MP3, M4A) plus an
  "Advanced Formats" table of every stream yt-dlp actually found
- Video downloads default to a genuine, broadly-playable **MP4** (H.264 +
  AAC) — remuxing when the source is already compatible, transcoding with
  FFmpeg when it isn't (e.g. YouTube's VP9/AV1 + Opus streams), never just
  renaming a `.webm` to `.mp4`. The expected output container is shown
  before you download; an opt-out "Best Quality / Original Container" mode
  keeps the raw source codec/container instead
- Live download progress over Server-Sent Events (no polling)
- Concurrent download queue (configurable, default 2 at a time)
- Cancel an in-progress download
- Download history in SQLite: search, filter, sort, retry, remove, open
  file/folder
- Optional clip-range downloads (download only part of a video)
- Optional cookie support for content that needs your logged-in session
  (cookies never leave your computer)
- Settings for download folder, concurrency, theme (System/Light/Dark, fully
  live-applied), video output mode (Compatibility MP4/Original), MP3
  bitrate, metadata/thumbnail embedding, network timeout
- First-run FFmpeg check with OS-specific install instructions
- Downloads interrupted by an app crash or force-quit are recovered as
  "Failed" (with a Retry button) the next time the backend starts, instead of
  vanishing silently

## Architecture

```
local-media-downloader/
  backend/            FastAPI app (Python)
    app/
      main.py          App wiring, CORS, error handlers
      api/              HTTP route modules (one per resource)
      services/         yt-dlp wrapper, download queue, settings, filesystem
      models/           Pydantic schemas + enums
      database/         SQLite connection + repositories
      utils/            URL detection, sanitization, timecode parsing, paths
      config/           Paths & logging configuration
    tests/              pytest suite (yt-dlp is mocked; no network calls)
  frontend/           React + Vite + TypeScript + Tailwind
    src/
      components/       Reusable UI pieces (MediaCard, FormatSelector, ...)
      pages/            Dashboard, History, Settings
      hooks/            useDownloadProgress (SSE)
      services/         Typed fetch client
      types/            Shared TypeScript types mirroring the backend schemas
  downloads/          Default download destination
  data/               SQLite database + rotating logs
  scripts/            start.sh / start.bat
```

**Backend**: FastAPI + Uvicorn, yt-dlp for extraction/download, FFmpeg for
merging and audio conversion, SQLite for history/settings, Server-Sent Events
for progress. All downloads run through an in-process async queue with a
configurable concurrency limit; yt-dlp itself runs in a worker thread per job
so the event loop stays responsive. For video downloads in Compatibility
mode, `download_manager._ensure_compatible_mp4` inspects the actually-
downloaded codecs (`ytdlp_service.needs_mp4_transcode`) after yt-dlp finishes
and, if they aren't already H.264/AAC, runs a second FFmpeg pass — a fast
lossless remux when only the container needs to change, or a genuine
transcode (libx264/AAC) when the codecs themselves are incompatible — before
the job is ever reported "Completed".

**Frontend**: React + TypeScript + Tailwind CSS, built with Vite. Talks to the
backend over a small typed `fetch` client and subscribes to
`/api/progress/stream` for live job updates.

## Supported platforms

| Platform  | Recognized URL forms                                   |
|-----------|----------------------------------------------------------|
| YouTube   | `youtube.com/watch`, `youtu.be`, `/shorts/`, live links  |
| TikTok    | `tiktok.com`, `vm.tiktok.com`, `vt.tiktok.com`            |
| Instagram | `instagram.com/reel/`, `/p/`, `/tv/`                      |
| Facebook  | `facebook.com`, `fb.watch`, reels                          |

Extraction itself is delegated entirely to yt-dlp, so support tracks whatever
yt-dlp's extractors currently handle for these domains.

## Requirements

- Python 3.12+ (3.11 also works; see [Known limitations](#known-limitations))
- Node.js 18+
- FFmpeg (required for merging video/audio and for audio conversion)

## Installation

### macOS

```bash
brew install python ffmpeg node
git clone <this-repo>
cd local-media-downloader
./scripts/start.sh
```

### Windows

```powershell
winget install Python.Python.3.12
winget install Gyan.FFmpeg
winget install OpenJS.NodeJS.LTS
git clone <this-repo>
cd local-media-downloader
scripts\start.bat
```

### Linux (Debian/Ubuntu)

```bash
sudo apt update && sudo apt install -y python3 python3-venv ffmpeg nodejs npm
git clone <this-repo>
cd local-media-downloader
./scripts/start.sh
```

## FFmpeg installation

| OS | Command |
|----|---------|
| macOS (Homebrew) | `brew install ffmpeg` |
| Windows (winget) | `winget install Gyan.FFmpeg` |
| Windows (Chocolatey) | `choco install ffmpeg` |
| Ubuntu / Debian | `sudo apt install ffmpeg` |
| Fedora | `sudo dnf install ffmpeg` |
| Arch Linux | `sudo pacman -S ffmpeg` |

If FFmpeg isn't found, the app shows a setup screen with these same
instructions and a "Recheck" button — no need to restart the app once it's
installed.

## Local startup

The easiest path is the startup script, which creates the Python virtual
environment, installs dependencies, verifies FFmpeg, and launches both
servers:

```bash
# macOS / Linux
./scripts/start.sh

# Windows
scripts\start.bat
```

This opens the app at **http://127.0.0.1:5173**. The backend API listens on
**http://127.0.0.1:8000** and is bound to localhost only.

For a full manual test checklist (per-platform tests, MP3, 1080p merging,
cancellation, cookies) and macOS-specific troubleshooting, see
[`LOCAL_MAC_TESTING.md`](./LOCAL_MAC_TESTING.md).

### Manual startup

```bash
# Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate        # .venv\Scripts\activate on Windows
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

## Settings

All settings are edited from the Settings page and persisted in SQLite
(`data/app.db`):

- **General** — download folder, max simultaneous downloads, theme
- **Video** — default quality, video output mode (**Compatibility MP4**,
  default — always ends in a genuine playable MP4, transcoding via FFmpeg
  when the source is WebM/VP9/AV1/Opus; or **Best Quality / Original
  Container** — keeps the source codec/container as-is, may be WebM/MKV,
  never transcodes), embed metadata, save thumbnail
- **Audio** — preferred format, MP3 bitrate, embed thumbnail in audio files
- **Authentication** — cookie source (see below)
- **Advanced** — yt-dlp version, FFmpeg path (read-only), network timeout,
  retry count

## Cookie support

Some content requires your normal logged-in browser session. In
**Settings → Authentication** you can choose:

- No cookies (default)
- Cookies from Chrome, Firefox, Edge, or Safari (read directly from your
  browser's local cookie store via yt-dlp's `--cookies-from-browser`)
- A cookie file you export yourself (Netscape format)

Cookies are read locally by yt-dlp and are **never uploaded anywhere** — they
stay on your computer and are never sent to the frontend, logged, or
transmitted over the network by this app. This only makes a difference for
content your own account can already see; it does not unlock content you
don't have access to.

## Troubleshooting

- **"FFmpeg is required" screen won't go away** — install FFmpeg (see above)
  and click Recheck. Restarting the backend also re-checks on startup.
- **"Could not reach the local backend"** — make sure the backend is running
  on port 8000 and that nothing else is using that port.
- **A specific video fails to analyze/download** — the app surfaces a
  friendly message (private/login-required, geo-restricted, age-restricted,
  unavailable, network error, etc.) with an optional "Show technical details"
  section. Check `data/logs/app.log` for the full error.
- **Downloads are slow or stall** — check Settings → Advanced for the
  network timeout/retry values; some platforms rate-limit aggressively.
- **Format/resolution I expected isn't shown** — the app only shows presets
  that actually exist for that particular video; check "Advanced Formats" to
  see every stream yt-dlp found.

## Testing

```bash
# Backend (207 tests: 121 for the downloader itself - yt-dlp/ffmpeg mocked,
# no network access needed - plus 86 for the commercial layer: auth, plan
# gating, usage/credit reservation including a real concurrency test, Paddle
# webhook signature/idempotency, and HTTP-level route/authorization checks)
cd backend && source .venv/bin/activate && python -m pytest -q

# Frontend (39 tests: utility functions plus component tests for auth
# context, protected routes, the header's signed-in/out states, and pricing)
cd frontend
npm run typecheck   # tsc, no emit
npm run lint        # eslint
npm run test        # vitest + jsdom + React Testing Library
npm run build       # production build
```

## Commercial layer quick start

`./scripts/start.sh` (or `start.bat`) handles this automatically — on first
run it generates `backend/.env` with a random `SECRET_KEY` and applies the
commercial database's Alembic migrations before starting both servers. To
do it by hand:

```bash
cd backend
cp .env.example .env   # then fill in SECRET_KEY at minimum
source .venv/bin/activate
python -m alembic upgrade head
```

Billing runs against **Paddle Sandbox only** — see
[`PADDLE_SANDBOX_TESTING.md`](./PADDLE_SANDBOX_TESTING.md) before setting
`PADDLE_*` variables. Without them, everything except checkout/billing
works normally (Free-plan signup, downloads within the Free limits, and the
whole commercial UI render fine with billing simply unconfigured).

## Updating yt-dlp

Platforms change frequently, and yt-dlp ships frequent fixes. To update:

```bash
cd backend
source .venv/bin/activate
pip install --upgrade yt-dlp
```

The installed version is shown in Settings → Advanced.

## Known limitations

- This environment's Python is 3.11 rather than the requested 3.12+; the app
  has no 3.12-only dependencies, so it runs correctly on 3.11+, but 3.12+ is
  still recommended for production use.
- Active download jobs live in memory, not just in SQLite, while running. If
  the backend is killed mid-download (crash, force-quit, `pkill`), the job
  itself is gone, but it is **not** silently lost: on the next startup it's
  automatically marked "Failed" with an explanatory message and a Retry
  button in History. True byte-level resume isn't attempted, but yt-dlp's
  own partial-file (`.part`) resume will often kick in transparently if the
  retry writes to the same filename.
- Cancelling during yt-dlp's own internal merge or MP3-extraction step can't
  interrupt that specific FFmpeg subprocess mid-flight (yt-dlp doesn't expose
  a hook for it), but the app still honors the cancellation afterwards — the
  job ends up "Cancelled" and the file that just finished is deleted rather
  than silently reporting success. The app's own separate Compatibility-mode
  MP4 conversion pass (the "Converting" stage after a WebM/VP9 download)
  *is* directly interruptible — clicking Cancel there stops FFmpeg within
  about a fifth of a second and cleans up the partial output.
- Compatibility mode's FFmpeg transcode (when the source isn't already
  H.264/AAC) uses `libx264 -preset medium -crf 18` — near-visually-lossless
  and broadly compatible, but a genuine re-encode is CPU-bound and takes
  meaningfully longer than a remux, especially for 4K+ source video. Switch
  to "Best Quality / Original Container" in Settings to skip conversion
  entirely if you'd rather keep the native WebM/AV1 file.
- Cookie-based access only works for content your own logged-in account can
  already see in a normal browser — it does not bypass any access control.
- Platform behavior (available qualities, playlist metadata, private-content
  handling) depends entirely on yt-dlp's extractors and will change as
  platforms change their sites.
- The clip-range feature re-encodes at cut points for accuracy, which is
  slower than a plain full-file download.
- `npm audit` flags two moderate/high advisories in Vite's dev server itself
  (not the production build) and one in react-router; fixing them requires a
  Vite 5→8 major upgrade we deliberately didn't force in this pass (too risky
  to land unverified). The dev server already only binds to 127.0.0.1 and
  isn't reachable from your network; avoid browsing untrusted sites while
  `npm run dev` is running if you want to fully eliminate the residual risk,
  or run `npm audit fix --force` yourself and retest.

## Security & privacy

- Backend binds to `127.0.0.1` only — nothing here listens on your network.
- CORS is restricted to the local frontend origins.
- No endpoint reads arbitrary files or executes arbitrary shell commands; the
  only filesystem operations are: writing inside your configured download
  folder, and opening/deleting a file you already downloaded via the OS's own
  file manager (`open` / `explorer` / `xdg-open`), invoked with argument
  arrays — never a shell string.
- Every "open" or "delete" filesystem action is checked server-side against
  the configured download folder (or an exact match to a file this app
  actually recorded in history) before it runs — the API can't be used to
  open or delete an arbitrary path elsewhere on disk, even if something other
  than the bundled frontend calls it directly.
- `/api/health` never creates directories or writes probe files as a side
  effect of a GET request; only explicitly saving a new download folder in
  Settings does.
- Filenames are sanitized for Windows/macOS/Linux compatibility before
  anything is written to disk.
- The Compatibility-mode FFmpeg conversion pass invokes `ffmpeg` the same
  way — an argument array (`subprocess.Popen([ffmpeg_path, ...])`), never a
  shell string built from user input.
- Cookies, authorization headers, and other session data are never logged or
  sent anywhere except to the platform's own servers via yt-dlp, exactly as
  your browser would.

## Version 2 ideas

- Batch/queue multiple URLs at once from a pasted list
- Per-item playlist selection (choose specific videos from a playlist, not
  just "current" vs "all")
- Tauri desktop packaging (structure already keeps backend/frontend
  independent enough to wrap)
- Scheduled/recurring downloads (e.g. "watch this channel")
- Subtitle download/embedding
- Per-row "delete file too" on a single history record (currently only the
  bulk "Clear History" flow offers that choice)
