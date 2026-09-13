# Platform Core + Loady: Staging Architecture (Mission 4)

Written before implementation, per mission instructions, then updated
with what was actually built and verified. Scope: turn Mission 3's
"works locally, SQLite, generated-per-restart keys" prototype into a
production-shaped staging deployment, without touching the live Loady
production VPS, DNS, TLS, Cloudflare, or Paddle Live in any way.

## Audit findings (pre-implementation)

Reviewed: `platform-core/backend`, `platform-core/admin-frontend`,
`compose.production.yml`/`compose.tls.yml` (Loady's own), Platform Core's
`settings.py`/`jwt_keys.py`/`db.py`, CORS, cookies, logging, `/health`,
migration startup, rate limiting, secret handling, Grand Admin auth, and
Loady's `platform_identity_service.py`/`platform_entitlement_service.py`/
`routes_platform_auth.py`. All six Mission 3 docs
(`LOADY_MIGRATION_AUDIT.md`, `LOADY_IDENTITY_INTEGRATION.md`,
`LOADY_MIGRATION_DRY_RUN.md`, `LOADY_ROLLBACK_PLAN.md`,
`LOADY_PRODUCTION_MIGRATION_PLAN.md`, `LOADY_MIGRATION_SECURITY_REVIEW.md`)
were re-read.

Key findings that shaped this mission's implementation:

- Platform Core's RS256 key (`jwt_keys.py`) already persisted to a file
  across restarts in dev — the actual gap was that it silently
  **generated** a throwaway key on first run in *every* `APP_ENV`,
  including a hypothetical staging/production one. Fixed by making that
  fallback development-only and fail-closed everywhere else (phase 3).
- "`platform_oidc_tokens.refresh_token` needs encryption at rest" (Mission
  3's phrasing) turned out to live in **Loady's own** database
  (`backend/app/database/commercial_models.py:PlatformOidcToken`), not
  Platform Core's — Platform Core's own `RefreshToken`/`OAuthRefreshToken`
  tables already store only a SHA-256 hash, exactly like every other
  token in that schema. Loady's copy is the one genuine exception: it
  must be presented back to Platform Core later, so it cannot be a
  one-way hash. `TokenEncryptionService` (phase 4) was built and wired in
  there.
- Rate limiting already existed for Platform Core's signup/login/password
  reset/OAuth-token endpoints (`rate_limit_service.py`); Grand Admin
  mutation endpoints did not have one — added (phase 10).
- Entitlement-availability behavior and central-disable propagation were
  explicitly left as open decisions in Mission 3 — this mission makes and
  implements both decisions (see `ENTITLEMENT_AVAILABILITY.md` and
  `SESSION_REVOCATION.md`).
- The already-running `loady-*` Docker containers on this machine are the
  **local production-parity replica** described in `LOCAL_MAC_TESTING.md`
  (compose.production.yml) — not the real production VPS. They were never
  stopped, rebuilt, or touched by anything in this mission; every staging
  container in this mission runs under a different compose project name,
  network, and set of named volumes.

## Components

```
                         ┌─────────────────────────────┐
   Browser  ───HTTPS───► │ platform-core reverse-proxy  │  (nginx, self-signed
                         │ (TLS termination, security   │   TLS cert for staging;
                         │  headers, path routing)      │   a real cert or an
                         └──────────────┬───────────────┘   upstream TLS proxy/
                                        │                    Cloudflare in prod)
                    ┌───────────────────┼────────────────────┐
                    │ /api/*,/oauth/*,  │ everything else
                    │ /.well-known/*,   │
                    │ /health,/ready    │
                    ▼                   ▼
        ┌───────────────────┐  ┌─────────────────────┐
        │ platform-core      │  │ admin-frontend        │
        │ backend (FastAPI,  │  │ (Grand Admin — Vite    │
        │ uvicorn, non-root) │  │  production build,     │
        └─────────┬──────────┘  │  served by nginx)      │
                  │              └─────────────────────┘
                  ▼
        ┌───────────────────┐
        │ PostgreSQL 16      │  (named volume, health-checked,
        │ (mission 4 ph.2)   │   never published to the host)
        └───────────────────┘

  Loady staging (separate compose project, separate network/volumes):
  reverse-proxy (nginx) → backend (FastAPI) → PostgreSQL 16 (staging)
                              │
                              └──(shared external docker network
                                  `platform-staging-net`)──► platform-core
                                                              backend, by
                                                              service alias
                                                              `platform-core-backend`
                                                              — plain HTTP,
                                                              private network only
```

Same-origin, path-routed design (one staging hostname in front of both
Platform Core's backend and the Grand Admin static build) deliberately
mirrors Loady's own existing production reverse-proxy pattern
(`frontend/nginx.tls.conf`): it keeps session cookies simple (no
cross-subdomain `SameSite`/CORS story) while still leaving room for a
future production deployment to split into `auth.<domain>` /
`admin.<domain>` by changing only `PLATFORM_AUTH_BASE_URL`,
`VITE_PLATFORM_API_BASE_URL`, and `COOKIE_DOMAIN` — nothing here assumes a
single host forever, and no production domain is hard-coded anywhere.

## Cross-service reachability: public vs. internal base URL

A genuine design problem this mission had to solve: the browser needs a
publicly reachable HTTPS URL for the OAuth redirect and to verify the
`iss` claim against, but Loady's *backend* (inside its own container)
cannot reach a self-signed-TLS `platform-staging.local` hostname without
either trusting that certificate or resolving a hostname a container
can't see. Rather than teach every internal `httpx` call about a CA
bundle, `PLATFORM_INTERNAL_BASE_URL` (new setting, phase 13) lets Loady's
backend reach Platform Core over the plain-HTTP shared docker network for
every server-to-server call (token exchange, JWKS fetch,
entitlement/status lookups), while `PLATFORM_AUTH_BASE_URL` remains the
externally reachable HTTPS host used for the browser redirect and kept as
the `iss`/`aud` value both sides verify against. Empty (default) means "no
override" — every existing single-URL deployment and test is unaffected.

**Known limitation carried into `PRODUCTION_READINESS_CHECKLIST.md`**:
this means staging's internal service-to-service traffic (including the
OAuth client secret and access/refresh tokens in transit) is plaintext
over the docker bridge network. Acceptable for a single-host local
staging rehearsal; a real production deployment across multiple hosts
needs either mutual TLS between services or a trusted private network
(VPC) with no other tenants.

## What was verified live (not just unit-tested)

Real Docker containers, real PostgreSQL 16, real self-signed TLS, real
cross-container HTTP:

- Fresh PostgreSQL → `alembic upgrade head` → signup → **process
  restart** → login with the same password still works, and a session
  token issued before the restart still verifies after it.
- **PostgreSQL container restart** → data (users, roles) survives.
- **Full stack restart** (all four platform-core containers at once) →
  data, session cookie, and signing key all survive.
- `pg_dump` → drop schema → `pg_restore --no-owner` into a **separate**
  Postgres container → users, role assignments, and `alembic_version` all
  present and correct (see `PLATFORM_BACKUP_RESTORE.md` for the ownership
  pitfall this surfaced).
- Real cross-container SSO: Loady staging (separate compose project) →
  Platform Core staging, over a shared external docker network — PKCE
  authorization code issued by Platform Core, exchanged by Loady, new
  Loady account created with `global_user_id` matching Platform Core's
  `usr_...` id, and `platform_oidc_tokens.refresh_token`/`access_token`
  stored as `v1:...` **encrypted envelopes**, confirmed by direct SQL
  query — never plaintext.
- Hybrid entitlement model, live: a gifted "creator" entitlement granted
  via the real Grand Admin API showed up through
  `get_entitlement_hybrid` as `source: "live"`; with Platform Core's
  containers stopped, the same call correctly returned the same
  entitlement as `source: "cached", stale: true`; after Platform Core
  came back, a live call correctly overwrote the cache again.
- Central-disable propagation, live: disabling the user via the real
  Grand Admin API, against Loady's real staging session, correctly
  disabled the local account within one revalidation check — this
  surfaced and led to fixing two real bugs (see `SESSION_REVOCATION.md`)
  that unit tests alone had not caught, because they only manifest under
  the actual FastAPI dependency/exception-rollback sequencing.

What was **not** run in this session (stated plainly rather than
implied): a real browser (Playwright/Selenium) driving the flow through
the UI; the full 36-step/24-scenario acceptance and failure matrices
verbatim end-to-end in one pass (a representative, high-value subset was
run for real instead — see the mission's final report for exactly which);
a multi-host deployment; a real (non-self-signed) TLS certificate; DNS or
Cloudflare of any kind.
