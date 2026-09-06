# Loady production deployment

## Architecture

Production retains the existing architecture: Nginx serves the Vite build and eight prerendered SEO pages, proxies `/api` and SSE to one FastAPI/Uvicorn process, and PostgreSQL stores commercial data. The raw SQLite `app.db` continues to store downloader settings/history. Redis and a separate worker are intentionally absent.

Only Nginx publishes host ports. Backend port 8000 and PostgreSQL port 5432 exist only on the Compose network. The backend runs as UID/GID 10001 with dropped capabilities; no service is privileged, uses host networking, mounts the Docker socket, or receives a public database port.

## Prerequisites

- Docker Engine and Docker Compose
- DNS for `loady.cc` only when launch is approved
- TLS certificate and key before enabling `compose.tls.yml`
- At least 15 GB free disk before building
- A separately stored copy of production secrets

Do not expose the app before production email delivery and Paddle launch configuration have been approved. The current code deliberately keeps Paddle in sandbox mode.

## Environment

Copy `.env.production.example` to `.env.production`, generate unique values for `SECRET_KEY` and both database passwords, and keep that file off Git. Run Compose with `--env-file .env.production`; `LOADY_ENV_FILE` tells the backend service which file to load.

`VITE_API_BASE_URL` is intentionally empty in production so browser requests use same-origin `/api`. `LMD_MAX_CONCURRENT_DOWNLOADS=1` is the beta default. Existing persisted `app.db` settings can override this; verify the Settings page still reports one simultaneous download after restoring an old database.

`EMAIL_BACKEND=disabled` suppresses token-bearing reset/verification messages. A real provider remains a launch requirement. Production mode will never fall back to logging full auth links.

## Build and first local start

```sh
cd local-media-downloader
cp .env.production.example .env.production
# Edit .env.production with local, non-production test secrets.
LOADY_ENV_FILE=.env.production docker compose --env-file .env.production -f compose.production.yml config
LOADY_ENV_FILE=.env.production docker compose --env-file .env.production -f compose.production.yml build
LOADY_ENV_FILE=.env.production docker compose --env-file .env.production -f compose.production.yml up -d
docker compose -f compose.production.yml ps
curl -fsS http://127.0.0.1/api/health
```

The backend entrypoint applies `python -m alembic upgrade head` before starting exactly one Uvicorn worker.

## TLS and DNS

Do not enable the TLS overlay until `secrets/tls/fullchain.pem` and `secrets/tls/privkey.pem` exist. The `secrets/` directory is ignored by Git.

```sh
LOADY_ENV_FILE=.env.production docker compose --env-file .env.production \
  -f compose.production.yml -f compose.tls.yml up -d
```

The overlay publishes 443 and redirects HTTP to `https://loady.cc`. If Cloudflare is used, set SSL/TLS mode to Full (strict), install a valid origin certificate first, preserve real visitor IP configuration in a separately reviewed proxy-hardening pass, and only then enable proxying. Do not use Flexible TLS.

## Operations

```sh
docker compose -f compose.production.yml ps
docker compose -f compose.production.yml logs --tail=200 backend
docker compose -f compose.production.yml logs --tail=200 reverse-proxy
docker compose -f compose.production.yml restart backend
docker compose -f compose.production.yml stop
docker compose -f compose.production.yml start
```

Docker's log rotation should be configured at the daemon level (`json-file` with `max-size` and `max-file`) or through the VPS logging policy. Application file logs rotate at 2 MB with five backups.

## Health checks

- Public: `GET /api/health` (production suppresses filesystem paths)
- Nginx container: `/robots.txt`
- PostgreSQL: `pg_isready`

Confirm `/api/health`, `/robots.txt`, `/sitemap.xml`, `/en`, and `/ar` through Nginx. Backend and PostgreSQL must have no host port bindings in `docker compose ps`.

## Media delivery and cleanup

Browsers download by opaque job ID from `GET /api/downloads/{job_id}/file`. The backend resolves the server-side record, checks account or guest ownership, requires completion, validates the resolved path within the caller's isolated directory under `DOWNLOAD_ROOT`, and streams with `FileResponse`.

The single backend process runs cleanup hourly. Authenticated media expires after 24 hours, guest media follows `GUEST_DATA_TTL_HOURS` (48 hours by default), and stale `.part`, `.ytdl`, `.tmp`, `.temp` and FFmpeg-style intermediates expire after 6 hours. Active paths and anything outside the resolved download root are excluded. Cleanup errors are logged without terminating the API.

The media volume is disposable and must be monitored for disk usage. Never include it in backups.

## Backups

Create backups outside the repository and media volume.

PostgreSQL:

```sh
docker compose --env-file .env.production -f compose.production.yml exec -T postgres \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > /secure-backups/loady-postgres.dump
```

SQLite should be copied with SQLite's online backup command, not a raw copy during writes:

```sh
docker compose -f compose.production.yml exec -T backend \
  python -c 'import sqlite3; s=sqlite3.connect("/var/lib/loady/data/app.db"); d=sqlite3.connect("/tmp/app-backup.db"); s.backup(d); d.close(); s.close()'
docker compose -f compose.production.yml cp backend:/tmp/app-backup.db /secure-backups/app.db
```

Store `.env.production` in an encrypted secrets backup outside the VPS. Do not back up `media-data`, downloads, partial files, thumbnails, or FFmpeg intermediates.

## Restore

1. Stop the backend.
2. Restore PostgreSQL into an empty database with `pg_restore --clean --if-exists` using an authorized database operator.
3. Copy the verified SQLite backup to `/var/lib/loady/data/app.db` and ensure UID/GID 10001 can read/write it.
4. Start PostgreSQL, then backend; its entrypoint applies any newer Alembic migrations.
5. Verify health, login, Admin V2, credits and history before reopening traffic.

## Rollback

Never rewrite Git history. Record the previously deployed commit and image IDs before each release. To roll back, check out the previous known-good commit in the deployment checkout, rebuild images, and run Compose again. Database migrations must be assessed before rollback; restore the pre-deployment database backups if the older code cannot read the newer schema. Media is disposable and is not restored.

## Resource limits

- Nginx: 0.5 CPU, 256 MB
- Backend/FFmpeg: 3 CPUs, 5 GB
- PostgreSQL: 0.75 CPU, 1 GB
- One backend worker and one simultaneous heavy-media job

These leave capacity for Ubuntu and Docker on the 4-vCPU/8-GB beta VPS. Monitor memory, load, disk space, download duration and container restarts before raising concurrency.

## Troubleshooting

- Migration failure: inspect backend logs and validate `DATABASE_URL` resolves `postgres`.
- Permission failure: inspect named-volume ownership; backend runs as UID/GID 10001.
- SSE stalls: confirm the exact stream location still has buffering disabled.
- SEO route returns SPA shell: rebuild the frontend image and inspect `/usr/share/nginx/html/en/index.html`.
- Unknown route returns 200: ensure the committed Nginx config is mounted and no upstream CDN rewrites 404s.
- Reset email absent: expected while `EMAIL_BACKEND=disabled`; configure an approved provider before launch.
