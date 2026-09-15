# Production Architecture Freeze (Mission 15, Phase 2)

**Status: FROZEN FOR V1 CUTOVER PLANNING. Not deployed.** This document
ratifies the single-VPS coexistence architecture already designed across
Missions 5 and 7 (`PRODUCTION_TOPOLOGY.md`, `MISSION_7_PRODUCTION_TOPOLOGY.md`,
`MISSION_7_ARCHITECTURE_AUDIT.md`, `compose.rc.yml`) as the exact shape this
mission's deployment/cutover package is built against. Nothing below is a
new design — every element cites the prior document or code that already
established it. Where this mission adds detail (labels, an authoritative
port table, an ASCII diagram combining all four hostnames), that is called
out explicitly as new.

No production system was accessed to write this document.

## Component labels

Legend: **PUBLIC** (reachable from the internet, via Cloudflare) · **INTERNAL
ONLY** (Docker-network-only, no host port) · **ADMIN ONLY** (internal, but
additionally requires authenticated Grand Admin/operator access at the
application layer) · **PERSISTENT** (has durable state that must be backed
up/restored) · **DISPOSABLE** (stateless container image; rebuilding it
loses nothing that matters).

| Component | Labels | Notes |
|---|---|---|
| Cloudflare | PUBLIC | Existing, unchanged. Full (strict) TLS to origin. |
| nginx edge (`reverse-proxy`, `compose.rc.yml`) | PUBLIC, DISPOSABLE | Only container with host ports (80/443). Hardened: `read_only`, `cap_drop: ALL`, `no-new-privileges` (`compose.rc.yml` lines 30-82, read directly). |
| Loady frontend (static build, served by the edge) | PUBLIC, DISPOSABLE | Unchanged from today's production. |
| Loady backend (`backend`) | INTERNAL ONLY, PERSISTENT (owns `app-data`/`media-data` volumes: SQLite app/history DBs, downloaded media) | Existing, unchanged container; joins `platform-net` as a *second* network interface only (`PRODUCTION_TOPOLOGY.md` §Networks). |
| Loady Postgres (`postgres`) | INTERNAL ONLY, PERSISTENT | Existing, unchanged. Commercial DB. Never gets a host port. |
| Platform Core backend (`platform-core-backend`) | INTERNAL ONLY, PERSISTENT (mounts the RS256 signing key file) | New. OIDC/OAuth issuer, `/api/v1/*`, `/.well-known/*`, JWKS, `/health`, `/ready`. |
| Platform Core Postgres (`platform-core-postgres`) | INTERNAL ONLY, PERSISTENT (`platform-postgres-data` volume) | New. Never shares a volume, network alias, or backup archive with Loady's Postgres. |
| Account Portal (`platform-core-account-frontend`) | PUBLIC (via edge), DISPOSABLE | New (built Mission 6, wired into topology Mission 7). Static build; nginx serves it on `platform-net`, no backend of its own. |
| Grand Admin (`platform-core-admin-frontend`) | PUBLIC (via edge), but application-layer **ADMIN ONLY** (requires Grand Admin auth), DISPOSABLE | Same static-build pattern as Account Portal. The edge does not itself gate access — the application does (existing Grand Admin auth), so this is public-reachable-but-admin-gated, not network-isolated from the internet. This is an explicit, existing design choice (matches how `admin.loady.cc` already works in staging) and is called out again in Phase 12's reverse-proxy review. |

## Networks (ratified from `PRODUCTION_TOPOLOGY.md` §Networks, unchanged)

| Network | Members | Purpose |
|---|---|---|
| `default` (Loady's existing, unnamed) | `reverse-proxy`, `backend` (Loady), `postgres` (Loady) | Unchanged. Platform Core containers never join it. |
| `platform-net` (new, internal-only, no external DNS) | `reverse-proxy` (2nd interface), `backend` (Loady, 2nd interface), `platform-core-backend`, `platform-core-postgres`, `platform-core-account-frontend`, `platform-core-admin-frontend` | OIDC discovery/JWKS, token exchange, entitlement/capability lookups, and edge routing to the three new hostnames. Loady's backend joining this network as a second interface is the *only* topology change made to the existing Loady container. |

## Volumes

| Volume | Backing service | Persistent? |
|---|---|---|
| `app-data` | Loady backend (SQLite app/history DBs) | Yes — existing, unchanged backup process |
| `media-data` | Loady backend (downloaded media cache) | Yes, but not identity/billing-critical — existing retention policy unchanged |
| `postgres-data` | Loady Postgres | Yes — existing backup process |
| `platform-postgres-data` | Platform Core Postgres | Yes — **new**, its own `pg_dump` cycle (`PRODUCTION_TOPOLOGY.md` §Backups); never combined into Loady's archive (different restore procedure, different sensitivity — it holds password hashes and OAuth client secret hashes for every ecosystem product, not just Loady) |

## Signing key / token-encryption key / OAuth config

- **Platform Core RS256 signing key**: one persistent PEM file, bind-mounted
  read-only into `platform-core-backend` only (`JWT_PRIVATE_KEY_PATH=/run/secrets/platform-signing-key.pem`
  per `platform-core/.env.production.example`). Never mounted into any
  other container. Rotation procedure: `KEY_ROTATION_RUNBOOK.md` (JWKS
  overlap, no hard cutover needed for this key specifically).
- **Loady's `TokenEncryptionService` AES-256-GCM key**: a Loady-side env var
  only; Platform Core never sees Loady's encrypted refresh tokens or this
  key. Rotation is a hard cutover (no key-versioning built) — see
  `KEY_ROTATION_RUNBOOK.md`.
- **OAuth client config** (`PLATFORM_CLIENT_ID`/`PLATFORM_CLIENT_SECRET`):
  Loady-side env vars identifying it to Platform Core as a registered OAuth
  client, same mechanism already proven in staging. Rotation is a hard
  cutover (no client-secret versioning built).
- **Service auth** (Loady ↔ Platform Core server-to-server calls): existing
  mechanism per `SERVICE_AUTH.md`, unchanged by this mission.
- **Billing webhook endpoint** (`POST /api/v1/billing/webhooks/paddle`):
  exists in code today (`platform-core/backend/app/api`), verified only
  against `FakeBillingProvider` and Sandbox-shaped fixtures
  (`FINAL_PREPRODUCTION_EVIDENCE_AUDIT.md` §3). Not registered with real
  Paddle Sandbox or Live yet — that is `BILLING_CUTOVER_RUNBOOK.md` Stage 2,
  a separate, later, explicitly-authorized effort per that runbook's own
  prerequisites section, unaffected by this mission's deployment package.

## Combined topology diagram (all four hostnames, one edge — new this mission, combining `PRODUCTION_TOPOLOGY.md`'s diagram with Mission 7's added Account Portal branch)

```
                                    Internet (Cloudflare, Full-strict TLS)
                                                   |
                                          host ports 80 / 443 ONLY
                                                   v
                    +------------------------------------------------------------------+
                    |                      nginx edge (reverse-proxy)                  |
                    |   read_only, cap_drop:ALL, no-new-privileges, healthcheck         |
                    +----------+--------------+------------------+----------------------+
                     Host: loady.cc   Host: id.<domain>   Host: account.<domain>   Host: admin.<domain>
                          |                  |                    |                      |
              +-----------v------+   +-------+---------------------+----------------------+
              |  network:default |   |            network: platform-net (NEW)             |
              +-----------+------+   +-------+---------------------+----------------------+
                          |                   |                    |                      |
              +-----------v------+  +---------v--------+  +--------v-----------+  +--------v-----------+
              | loady-backend    |  | platform-core-   |  | platform-core-     |  | platform-core-     |
              | (:8000 internal, |  | backend          |  | account-frontend   |  | admin-frontend     |
              |  2nd iface on    |  | (:8000 internal, |  | (nginx static,     |  | (nginx static,     |
              |  platform-net)   |  |  PERSISTENT:      |  | :80 internal,      |  | :80 internal,      |
              +-----------+------+  |  signing key file)|  | DISPOSABLE)        |  | ADMIN-ONLY at app  |
                          |         +---------+--------+  +--------------------+  |  layer, DISPOSABLE)|
              +-----------v------+            |                                   +--------------------+
              | loady-postgres   |  +---------v--------+
              | (INTERNAL ONLY,  |  | platform-core-   |
              |  PERSISTENT, NO  |  | postgres          |
              |  host port)      |  | (INTERNAL ONLY,   |
              +------------------+  |  PERSISTENT, NO   |
                                     |  host port,       |
              Loady SQLite DBs live |  own volume)       |
              on loady-backend's    +-------------------+
              own app-data volume,
              unrelated to Platform Core.
```

## Sequencing precondition this freeze assumes (see Phase 22)

Platform Core must be deployed, healthy, and independently verified
**before** any Loady identity migration begins. This architecture supports
that: Platform Core's containers, database, and signing key are entirely
independent of Loady's — nothing about bringing Platform Core up requires
Loady to change state first.

## Port plan (Mission 15, Phase 3 — new this mission)

Exact container/port/exposure/network/route table, read directly from
`compose.rc.yml` (265 lines, read in full) and
`platform-core/reverse-proxy/nginx.production.conf.template` (206 lines,
read in full). No host inspection was used or is needed — every value below
is either a literal in these two files or one of their own declared
env-var defaults.

| Container | Container port | Host port | Exposure | Network(s) | Reverse-proxy route |
|---|---|---|---|---|---|
| `reverse-proxy` | 80, 443 | `${RC_HTTP_PORT:-80}`, `${RC_HTTPS_PORT:-443}` | **PUBLIC** | `default` + `platform-net` | N/A (this *is* the edge) |
| `backend` (Loady) | 8000 | none (`expose` only) | INTERNAL ONLY | `default` + `platform-net` | `${RC_LOADY_HOSTNAME}` → `/api/*`, `/api/progress/stream`; SPA routes → static build |
| `postgres` (Loady) | 5432 | none (`expose` only) | INTERNAL ONLY | `default` only | N/A — never proxied |
| `platform-core-postgres` | 5432 | none (`expose` only) | INTERNAL ONLY | `platform-net` only | N/A — never proxied |
| `platform-core-backend` | 8000 | none (`expose` only) | INTERNAL ONLY | `platform-net` only | `${RC_PLATFORM_AUTH_HOSTNAME}` → `^/(api/|oauth/|\.well-known/)`, `/health`, `/ready`; everything else 404s (no admin UI on this hostname) |
| `platform-core-account-frontend` | 80 | none (`expose` only) | INTERNAL ONLY (edge-fronted, so effectively public via the edge) | `platform-net` only | `${RC_ACCOUNT_HOSTNAME}` → `/` (all paths) |
| `platform-core-admin-frontend` | 80 | none (`expose` only) | INTERNAL ONLY (edge-fronted; **application-layer admin auth is the only gate** — see freeze note above) | `platform-net` only | `${RC_ADMIN_HOSTNAME}` → `/` (all paths) |

**Conflict analysis (static, from repo config only — no host inspection performed or possible in this environment):**

- Only `reverse-proxy` binds host ports, and only two (`80`/`443`) — identical
  to today's Loady-only `compose.production.yml` + `compose.tls.yml`. Bringing
  up `compose.rc.yml` **replaces** (does not add to) the existing `loady`
  project's port bindings — it is designed to be the production stack, not
  an addition beside it (see Phase 22's sequencing: Platform Core is
  deployed and verified before cutover, but the actual production port
  80/443 binding transition from the old `loady` project's `reverse-proxy`
  container to the new `loady-rc` project's `reverse-proxy` container is
  itself a cutover-day step, not something that runs concurrently forever).
- No Platform Core service gets a host port under any configuration in this
  file — `platform-core-postgres`, `platform-core-backend`,
  `platform-core-account-frontend`, `platform-core-admin-frontend` all use
  `expose` only. This satisfies Phase 3's explicit requirement that Platform
  Core's backend/Postgres/Grand Admin never get an accidental public port.
- The Account Portal is a static nginx build with no dev server anywhere in
  its `Dockerfile` (`platform-core/account-frontend/Dockerfile`, multi-stage
  Node 22 build → nginx runtime) — Phase 3's "must not use a Vite dev server
  in production" concern is structurally satisfied, not just a convention.
- **Whether host ports 80/443 are actually free on the real VPS at cutover
  time** (i.e. whether the old `loady` project's `reverse-proxy` has been
  correctly stopped first) cannot be verified here — `PRODUCTION PREFLIGHT
  REQUIRED`, and is check #4 in the Phase 18 read-only preflight script.
- The unrelated staging stack (`platform-core/compose.staging.yml`, host
  port default `8080` per that file vs. `8091` in
  `platform-core/.env.staging.example` — the discrepancy noted in
  `FINAL_PREPRODUCTION_EVIDENCE_AUDIT.md` §8) has no interaction with
  `compose.rc.yml` at all: different project name, different port range,
  never brought up together in any documented procedure.

## Known, accepted V1 limitations (carried forward, not fixed by this mission — see `HUMAN_INPUTS_REQUIRED_BEFORE_PRODUCTION.md` / final blocker classification for disposition)

These are real findings from `MISSION_7_ARCHITECTURE_AUDIT.md`'s classification
table, restated here because they directly shape what "initial production
topology" actually means — they are not silently resolved by freezing the
architecture:

1. **Dual password truth for migrated users.** After identity migration
   links a Loady user to a `global_user_id`, Loady's own `User.password_hash`
   column is *not* removed or made a read-only mirror — Loady still verifies
   passwords locally for its own login route (`MISSION_7_ARCHITECTURE_AUDIT.md`
   §1, classified `must-remove-before-cutover` in that audit's terminology,
   meaning "before a *full* cutover," not before this mission's deployment
   package). Central SSO (Account Portal → Loady OIDC callback) is the *new*
   entry point Mission 6 built, but it does not by itself deprecate Loady's
   existing local login form. **Accepted for V1**: both continue to work in
   parallel; removing Loady's local password path is out of scope for this
   mission (no feature creep) and is not required for "prepared for
   controlled production deployment."
2. **Ecosystem-wide sign-out is bounded, not instant**, by Loady's cached
   OIDC access-token TTL (~15 minutes default). Single-session revoke of
   Platform Core's own first-party cookie *is* immediate (fixed in Mission 7,
   `SESSION_SECURITY.md`). This bound is accepted, documented, and unchanged.
3. **Platform Core's billing stack has never processed a real Paddle event.**
   Loady's own Paddle integration remains the live, production billing path
   for V1 deployment; Platform Core's billing cutover is `BILLING_CUTOVER_RUNBOOK.md`,
   an explicitly separate, later, multi-stage effort with its own prerequisites
   — not a step of this mission's deployment package.
4. **A real off-site backup destination is not configured anywhere** — the
   mechanism (encryption, permissions, retention, restore verification) is
   built and proven; only the actual remote target is unconfigured. Tracked
   as a `CREDENTIAL BLOCKER`/`INFRASTRUCTURE BLOCKER` in Phase 54, not a code
   gap.
5. **A real TLS certificate for the new hostnames does not exist** — needs a
   real DNS decision first (Phase 4/13/14).
