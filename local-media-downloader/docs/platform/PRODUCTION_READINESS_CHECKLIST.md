# Production Readiness Checklist

Status as of Mission 4. Categorized `BLOCKER` (must fix before any real
production migration) / `HIGH` / `MEDIUM` / `LOW`. Items marked ✅ were
verified live in this mission's staging rehearsal, not just implemented.

## Identity

- ✅ **DONE** — Central identity, OAuth Authorization Code + PKCE,
  cross-product SSO, immutable `global_user_id` (Mission 3, re-verified
  live in this mission's cross-container rehearsal).
- `BLOCKER` — Ecosystem-wide logout does not exist (documented limitation
  since `LOADY_IDENTITY_INTEGRATION.md` §6, not addressed in this
  mission). Signing out of Platform Core does not sign a user out of
  Loady or vice versa.

## Database

- ✅ **DONE** — PostgreSQL support built, tested with a real Postgres 16
  container: migrations, connection pooling (`pool_pre_ping`,
  `pool_size=5`, `max_overflow=10`), UTC timestamp handling, restart
  survival, full-stack restart survival.
- `MEDIUM` — Pool sizing (5/10) is a single-worker-process guess, not
  load-tested. Needs real traffic data before production.
- `MEDIUM` — No read replica / connection failover story. Single Postgres
  instance is a single point of failure.

## TLS

- ✅ **DONE (staging only)** — Self-signed TLS terminated at an nginx
  reverse proxy, HTTP→HTTPS redirect, security headers, verified live
  over real HTTPS.
- `BLOCKER` — Self-signed certificate. Production needs a real
  certificate (Let's Encrypt, a commercial CA, or Cloudflare's own edge
  TLS) — not a code change, but not done here either.
- `HIGH` — Internal (service-to-service) traffic between Loady and
  Platform Core runs over plain HTTP on a private docker network in this
  staging design (see `STAGING_ARCHITECTURE.md`). Acceptable for a
  single-host staging rehearsal; a multi-host production deployment needs
  mTLS or an equivalently trusted private network.

## DNS

- Not touched, per mission constraints. `PLATFORM_AUTH_BASE_URL`/
  `PLATFORM_API_BASE_URL` are fully configurable and never hard-code a
  domain — production DNS decisions are unblocked by the architecture,
  but no DNS work has been done.

## Secrets

- ✅ **DONE** — No secret is committed; `.env.staging` added to
  `.gitignore`; signing key and token-encryption key both provisioned out
  of band via scripts that write to a gitignored `secrets/` directory.
- `HIGH` — No secret-manager integration (Vault, AWS/GCP Secrets Manager,
  etc.) — staging uses mounted files and `.env` files, adequate for
  staging, not for production secret rotation/audit requirements.

## Signing keys

- ✅ **DONE** — RS256 key persists across restarts; fails closed in any
  non-`development` `APP_ENV` if the key file is missing; never
  regenerated silently; `kid` supported; verified live (a token issued
  before a restart still verified after it, across two consecutive
  restarts).
- `MEDIUM` — No key **rotation** procedure exists yet (the `kid`
  mechanism supports it structurally, but there is no runbook or code
  path for "add a new key, keep validating tokens signed with the old one
  during a transition window, then retire the old one").

## Token encryption

- ✅ **DONE** — `PlatformOidcToken.refresh_token`/`access_token`
  encrypted at rest with AES-256-GCM; versioned envelope; fails closed
  without a real key outside development; verified live (direct SQL
  query against the staging database showed `v1:...` envelopes, never
  plaintext, after a real cross-container SSO login).
- `MEDIUM` — No migration script has been run against a real legacy
  plaintext dataset (none exists yet in any real deployment) — the
  one-time re-encryption script (`encrypt_platform_oidc_tokens.py`) is
  written and unit-tested but has only been exercised against synthetic
  rows, never a production-scale table.

## Backup

- ✅ **DONE (staging only)** — `pg_dump`/`pg_restore` rehearsed for real
  into a separate database; the `--no-owner` requirement documented from
  a real failure.
- `BLOCKER` — No encryption of the backup file itself, no off-site
  storage, no automation/retention policy (see `PLATFORM_BACKUP_RESTORE.md`).

## Restore

- ✅ **DONE (staging only)** — See above; users, role assignments, and
  `alembic_version` verified present after restore.
- `HIGH` — Only verified for a small, synthetic dataset. Restore time at
  real production data volume is unknown.

## Monitoring

- `HIGH` — No metrics/alerting pipeline. `/health` and `/ready` exist and
  are container-healthcheck-compatible, which is the minimum viable
  signal, but there is no dashboard, no alert-on-`/ready`-failing, and no
  log aggregation beyond structured stdout logging.

## Rate limiting

- ✅ **DONE** — In-memory sliding-window limiter on signup, login,
  password reset, OAuth token, and (new this mission) Grand Admin
  mutation endpoints.
- `HIGH` — Explicitly single-process/in-memory (documented in
  `rate_limit_service.py`'s own docstring, inherited from Loady's
  identical existing pattern). Running more than one backend worker
  process/replica would give each its own independent limit — i.e. the
  effective limit multiplies by worker count. Current staging/production
  Dockerfile runs `--workers 1` specifically to keep this true; scaling
  out requires a Redis-backed (or equivalent shared-state) limiter first.

## Email

- Untouched — `EMAIL_BACKEND=log` (dev/test only) is enforced by mission
  instruction; production Resend configuration was explicitly out of
  scope and not modified.

## Paddle

- Untouched. Loady staging is configured `PADDLE_ENV=sandbox` with all
  keys blank; nothing in this mission calls Paddle Live, and nothing here
  changes Loady's existing hard restriction to Paddle Sandbox.

## Migration

- ✅ **DONE (Mission 3, re-confirmed dormant)** — Loady→Platform Core
  migration mechanism (dry-run, idempotent commit) untouched by this
  mission; production Loady users have still never been migrated.

## Rollback

- Unchanged from Mission 3's `LOADY_ROLLBACK_PLAN.md`. Not re-rehearsed
  in this mission (out of scope: this mission is about staging
  infrastructure, not the migration rollback procedure itself).

## Session revocation

- ✅ **DONE (staging only)** — Bounded central-disable propagation,
  ≤`SESSION_REVALIDATION_INTERVAL_MINUTES` (default 5) after the user's
  next request, given a still-valid access token at check time. See
  `SESSION_REVOCATION.md` for the exact SLA statement, its one known edge
  case, and two real bugs found and fixed via live rehearsal.
- `MEDIUM` — No background sweep; an idle-but-disabled session is only
  re-checked on its next request, which could be arbitrarily far in the
  future for a truly idle session.

## Entitlement availability

- ✅ **DONE (staging only)** — Hybrid model implemented and verified live
  (see `ENTITLEMENT_AVAILABILITY.md`).
- `BLOCKER` (architectural, not a defect) — Not wired into Loady's actual
  live download gate. This is an intentional, carried-forward scoping
  decision from Mission 3, not an oversight — wiring it in is real,
  separate, hot-path-risk work that deserves its own review.

## Grand Admin

- ✅ **DONE** — Central admin login, `super_admin`/product-scoped roles,
  user search, product management, gifted-access grant/revoke, audit
  logs, served as a production static build behind the staging reverse
  proxy; product-scoped-admin-cannot-become-global-admin confirmed
  (Mission 3, unchanged).
- Not re-verified this mission: EN/AR/RTL rendering and unauthorized-access
  UI behavior in a real browser (only the API layer was exercised live;
  the admin-frontend's own unit tests, which do cover i18n/RTL, pass —
  see the mission's final report for exact counts).

## Audit logs

- ✅ **DONE (Mission 3, unchanged)** — Append-only, never contains
  secrets/tokens/password hashes.

## Privacy

- No new PII is collected by anything built in this mission. Existing
  privacy posture (Mission 3, `SECURITY.md`) unchanged.

## Incident recovery

- `HIGH` — No documented incident-response runbook beyond backup/restore.
  What to do if the signing key is compromised, if the token-encryption
  key is compromised, or if Platform Core's database is compromised are
  all unwritten.

## One-time Loady re-login

- Unchanged from Mission 3: migrated users authenticate with their
  existing Loady password on first central login (Argon2id hash
  compatibility already proven); not re-tested this mission since no new
  code touches that path.

## Cross-product SSO

- ✅ **DONE (Mission 3, re-verified live this mission)** — the same
  underlying OAuth/PKCE mechanism proven for Loady in this mission's
  rehearsal is architecturally identical to what already SSOs demo
  products A/B; not independently re-run against the demo products in
  this specific mission's rehearsal (time-boxed choice — see the final
  report).
