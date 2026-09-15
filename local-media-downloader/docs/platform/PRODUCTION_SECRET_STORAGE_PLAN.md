# Production Secret Storage Plan — Single-VPS V1 (Mission 15, Phase 9)

## V1 procedure (no secret manager — matches the existing Loady practice this box already runs)

1. **Root-owned env files, restricted permissions.** `.env.rc`,
   `.env.production` (Loady), `platform-core/.env.production` all live only
   on the VPS filesystem, owned by the deploying user (not `root` unless
   Docker itself runs as root — match whatever Loady's existing deployment
   user already is), `chmod 600`. Never group- or world-readable.
2. **Compose env injection**, not baked into any image. `compose.rc.yml`
   already does this correctly for every service (`env_file:`,
   `environment:` with `${VAR:?}` guards) — confirmed by direct read; no
   secret value is an `ARG`/`ENV` baked into a Dockerfile anywhere in
   `platform-core/backend/Dockerfile`, `backend/Dockerfile`, or the two
   frontend Dockerfiles (build args there are all non-secret, e.g.
   `VITE_SITE_URL`, `VITE_PLATFORM_API_BASE_URL`).
3. **The RS256 private key is a mounted file, not an env var** —
   `PLATFORM_SIGNING_KEY_PATH` (host path) bind-mounted read-only to
   `/run/secrets/platform-signing-key.pem` inside the container. `chmod
   600` on the host file; the container reads it read-only
   (`:ro` in `compose.rc.yml`).
4. **Never**: committed to Git (every `.env*` except `*.example` is
   gitignored — verified pattern, not assumed), baked into a Docker image
   layer, embedded in any frontend bundle (the two frontends' only
   `VITE_*` build args are non-secret by design, confirmed above), written
   to application logs (Phase 43 re-verifies this specifically), or left
   in shell history (use `read -s` or a file redirect when entering
   generated values, never a bare command-line argument containing the
   secret itself).
5. **Directory layout on the VPS** (recommended, not yet created):
   ```
   /opt/loady-rc/
     .env.rc                              (600, deploy user)
     .env.production                      (600, deploy user)   # Loady
     platform-core/.env.production        (600, deploy user)
     platform-core/secrets/platform-signing-key.pem  (600, deploy user)
     secrets/tls/{fullchain.pem,privkey.pem}          (600, deploy user)
   ```
   This mirrors `.env.rc.example`'s own path conventions
   (`PLATFORM_SIGNING_KEY_PATH=./platform-core/secrets/platform-signing-key.pem`,
   `RC_TLS_DIR=./secrets/tls`) exactly — no new convention invented here.

## Backup handling for these files specifically

Config files (not values) are captured by
`backup-before-platform-migration.sh`'s "configuration inventory" step —
confirming *which* variables were set and their file permissions, never
their contents. The signing key and TLS private key are backed up as
opaque binary blobs, encrypted at rest (existing mechanism, `openssl enc`,
per `PLATFORM_BACKUP_RESTORE.md`), with the same or greater protection as
the database backup, per `PRODUCTION_SECRET_INVENTORY.md`.

## Future secret-manager upgrade path (not a blocker for V1)

`PRODUCTION_READINESS_CHECKLIST.md` already flags "no secret-manager
integration" as a HIGH-severity (not BLOCKER-severity) gap. This mission
does not close that gap — introducing a secret manager (Vault, a cloud
KMS, etc.) on a single, already-resource-constrained VPS is exactly the
kind of infrastructure addition the mission's "No Feature Creep" rule
forbids introducing speculatively. The upgrade path, when eventually
pursued, is additive: point the same env var names at a secret manager's
injected values instead of a file, without changing any application code
that reads `get_settings()` — every secret is already read through a
single `Settings`/`CommercialSettings` object, not scattered `os.environ`
calls, so this is a deployment-layer change only when it happens.

## What V1 explicitly accepts as a limitation

- A single compromised deploy-user account or a misconfigured file
  permission is a full-secret-exposure event — there is no secret-manager
  audit log, no per-secret access control, no automatic rotation. This is
  the same posture Loady's own production already operates under today
  (unaffected by this mission), extended consistently to Platform Core's
  new secrets rather than introducing a stronger posture for the new
  component only.
