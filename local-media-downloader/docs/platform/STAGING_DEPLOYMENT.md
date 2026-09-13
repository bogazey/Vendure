# Staging Deployment Runbook (Mission 4)

Everything in this document was actually run, in this order, on a single
Docker host, to bring up Platform Core staging + Loady staging together.
It never touches the real Loady production VPS, DNS, TLS, Cloudflare, or
Paddle Live.

## Prerequisites

- Docker + Docker Compose v2 (`docker compose version`).
- `openssl` (for the self-signed staging cert and signing key).
- Python 3.11+ available locally only if you want to run the backend test
  suites outside a container.

## 1. Platform Core staging

```sh
cd platform-core

# Secrets, generated locally, never committed (gitignored):
./reverse-proxy/generate-staging-cert.sh platform-staging.local
./backend/generate-staging-signing-key.sh

cp .env.staging.example .env.staging
# Edit .env.staging: set POSTGRES_PASSWORD and COOKIE_SIGNING_KEY to real
# random values, e.g.:
python3 -c "import secrets; print(secrets.token_urlsafe(24))"   # POSTGRES_PASSWORD
python3 -c "import secrets; print(secrets.token_hex(32))"       # COOKIE_SIGNING_KEY
```

Bring the stack up:

```sh
docker network create platform-staging-net   # shared with Loady staging; create once
docker compose -f compose.staging.yml --env-file .env.staging up -d --build
```

### Health verification

```sh
curl -sk https://127.0.0.1:8443/health   # {"status":"ok"}
curl -sk https://127.0.0.1:8443/ready    # {"status":"ok","checks":{"database":true,"signing_key":true}}
```

A `503` from `/ready` with `"database": false` or `"signing_key": false`
tells you which dependency is the problem — check `docker compose logs
backend`.

### Grand Admin bootstrap

```sh
curl -sk -X POST https://127.0.0.1:8443/api/v1/auth/signup \
  -H 'content-type: application/json' \
  -d '{"email":"you@example.com","password":"a-real-password"}'

docker exec platform-core-staging-backend-1 \
  python -m app.scripts.promote_super_admin you@example.com
```

Open `https://127.0.0.1:8443/` (accept the self-signed certificate
warning, or add `platform-staging.local` to `/etc/hosts` pointing at
`127.0.0.1` first) and sign in with that account — this is the Grand
Admin production build, served by nginx, not a dev server.

### OAuth client registration

```sh
# Loady:
docker exec platform-core-staging-backend-1 \
  python -m app.scripts.register_loady_client \
  --redirect-uri http://localhost:8090/api/auth/platform/callback
# Prints PLATFORM_CLIENT_ID/PLATFORM_CLIENT_SECRET — paste into Loady's .env.staging.

# Demo products, if needed:
docker exec platform-core-staging-backend-1 python -m app.scripts.register_demo_clients
```

## 2. Loady staging

```sh
cd ..   # repo root
cp .env.staging.example .env.staging
```

Fill in `.env.staging`:

- `SECRET_KEY`, `POSTGRES_PASSWORD`: real random values (same generation
  commands as above).
- `PLATFORM_CLIENT_SECRET`: the value printed by `register_loady_client`
  above.
- `PLATFORM_TOKEN_ENCRYPTION_KEY`: `python -c "import secrets, base64;
  print(base64.b64encode(secrets.token_bytes(32)).decode())"` — a real
  32-byte key, distinct from `SECRET_KEY` and from Platform Core's
  signing key.
- Leave `PLATFORM_AUTH_BASE_URL`/`PLATFORM_API_BASE_URL` pointing at the
  public `https://platform-staging.local:8443` and
  `PLATFORM_INTERNAL_BASE_URL` at `http://platform-core-backend:8000` —
  see `STAGING_ARCHITECTURE.md` for why these differ.

```sh
docker compose -f compose.staging.yml --env-file .env.staging up -d --build
```

### Health verification

```sh
curl -s http://localhost:8090/api/health
curl -s http://localhost:8090/api/auth/platform/status   # {"enabled":true}
```

### Connecting to Platform Core staging

Both stacks must be attached to the same `platform-staging-net` external
network (Loady's `compose.staging.yml` already declares its `backend`
service on it) — confirm with:

```sh
docker exec loady-staging-backend-1 python -c \
  "import httpx; print(httpx.get('http://platform-core-backend:8000/health', timeout=5).json())"
```

## 3. Backup

See `PLATFORM_BACKUP_RESTORE.md` for the full procedure and the ownership
pitfall it surfaced. Quick reference:

```sh
docker exec platform-core-staging-postgres-1 \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -F c -f /tmp/backup.dump
docker cp platform-core-staging-postgres-1:/tmp/backup.dump ./backup.dump
```

## 4. Restore

```sh
docker exec -i platform-core-staging-postgres-1 \
  pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --role="$POSTGRES_USER" \
  --clean --if-exists < ./backup.dump
```

## 5. Shutdown / restart

```sh
# Stop everything, keep data:
docker compose -f compose.staging.yml --env-file .env.staging down
docker compose -f platform-core/compose.staging.yml --env-file platform-core/.env.staging down

# Restart (data, session cookies, and the signing key all survive — verified):
docker compose -f platform-core/compose.staging.yml --env-file platform-core/.env.staging up -d
docker compose -f compose.staging.yml --env-file .env.staging up -d

# Destroy everything including data (staging only — never run against production):
docker compose -f compose.staging.yml --env-file .env.staging down -v
docker compose -f platform-core/compose.staging.yml --env-file platform-core/.env.staging down -v
docker network rm platform-staging-net
```

## 6. Logs

```sh
docker compose -f platform-core/compose.staging.yml logs -f backend
docker compose -f compose.staging.yml logs -f backend
```

Structured, single-line-per-event logs (`timestamp level [service] message`)
— never contains passwords, tokens, authorization codes, client secrets,
signing keys, or encryption keys (see the security review in the
mission's final report for what was specifically checked).

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Backend container `unhealthy`, logs show `PermissionError: [Errno 13] Permission denied: '/data'` | `LMD_DATA_DIR`/`LMD_LOG_DIR`/`LMD_DB_PATH`/`DOWNLOAD_ROOT` not set in `.env.staging` — Loady's non-root container can't write to its default path | Set them to the mounted volume paths, exactly as in `.env.staging.example` |
| `reverse-proxy` container fails with `address already in use` | Host port collision with something else already running | Change `PLATFORM_STAGING_HTTP_PORT`/`PLATFORM_STAGING_HTTPS_PORT` (or `LOADY_STAGING_HTTP_PORT`) in `.env.staging` |
| `/ready` returns `"signing_key": false` | `JWT_PRIVATE_KEY_PATH` not mounted, or `generate-staging-signing-key.sh` was never run | Run the script, confirm the volume mount path matches `JWT_PRIVATE_KEY_PATH` |
| Loady's `/api/auth/platform/login` 404s | `PLATFORM_CLIENT_ID`/`PLATFORM_CLIENT_SECRET` not set — the integration is dormant by design | Set both from `register_loady_client`'s output |
| Loady backend can't reach Platform Core (`Name or service not known`) | Not on the shared `platform-staging-net` network, or Platform Core's backend container isn't up | `docker network create platform-staging-net` (once), confirm both compose files reference it |
| `pg_restore` prints `ALTER TABLE ... OWNER TO` errors | Restoring into a database with a different role name than the original | Use `--no-owner --role=<target_user>` |
