# Future Production Topology — Loady + Platform Core on the Existing VPS

Status: DESIGN ONLY. Nothing in this document is deployed by Mission 5.
No production system was accessed to write it — it is derived entirely
from this repo's own deployment docs (`docs/DEPLOYMENT.md`,
`docs/LAUNCH_CHECKLIST.md`, `compose.production.yml`, `compose.tls.yml`)
plus the architecture already built and tested in `platform-core/`.

## Constraints taken as given

- Single VPS, currently documented in-repo as a 4-vCPU/8-GB box running
  Ubuntu + Docker, already running production Loady
  (`docker compose -f compose.production.yml -f compose.tls.yml up -d`,
  project name `loady`).
- Cloudflare in front, Full (strict) TLS to the origin, `CF-Connecting-IP`
  / `CF-IPCountry` trusted via `cloudflare-realip.conf`.
- Paddle Live (pending migration per `LAUNCH_CHECKLIST.md`), Better Stack,
  Resend — external services, unaffected by this topology (Platform Core
  never talks to Paddle or Resend; those stay entirely inside Loady).
- Exact host specs (Contabo, Ubuntu 24.04, current disk/CPU headroom) were
  supplied by the user, not read from local docs — see
  `PRODUCTION_CAPACITY_PLAN.md` for the explicit "must be measured on the
  real box before cutover" callout.

## Design goals

1. Zero new public ports beyond what Cloudflare already expects (443, and
   80 for ACME/redirect only).
2. No database is ever publicly reachable — Postgres stays on an internal
   Docker network with no host port mapping, matching how
   `compose.production.yml` already runs Loady's own Postgres.
3. Platform Core's containers are isolated from Loady's containers except
   for the one explicit internal path they need (OIDC discovery/JWKS,
   token exchange, entitlement lookups) — no shared database, no shared
   filesystem.
4. One TLS-terminating edge, not two competing processes fighting over
   host port 443.
5. Reuse the existing `loady` production stack's certificates/Cloudflare
   configuration; add Platform Core alongside it, not instead of it.

## Recommended shape: one edge reverse proxy, two internal backend networks

A single nginx edge container keeps terminating TLS on host `80`/`443`
(exactly as `compose.tls.yml` does today) and adds **name-based virtual
hosts** for the new Platform Core surfaces, proxying to a *second* internal
Docker network that Loady's own backend does not join:

```
                                   Internet (Cloudflare, Full-strict TLS)
                                                  |
                                                  | :443 / :80
                                                  v
                    +---------------------------------------------------+
                    |  nginx edge  (extends existing "loady" reverse-    |
                    |  proxy container; adds two more server{} blocks)  |
                    |  host ports: 80, 443 only  (unchanged from today) |
                    +-----------------+-------------------+-------------+
                         Host: loady.cc      Host: id.loady.cc     Host: admin.loady.cc
                                |                    |                     |
                     +----------+----------+   +-----+----------------------+
                     |  network: default   |   |  network: platform-net     |
                     |  (loady's existing  |   |  (NEW, internal-only,      |
                     |   internal network) |   |   Loady backend also       |
                     |                     |   |   joins this ONE network   |
                     +----------+----------+   |   for server-to-server     |
                                |               |   calls — nothing else)   |
                     +----------v----------+    +-----+---------------+-----+
                     |  loady-backend      |          |               |
                     |  (existing, :8000   |    +-----v------+  +-----v--------------+
                     |   internal only)    |    | platform-  |  | platform-core-      |
                     +----------+----------+    | core-      |  | admin-frontend      |
                                |                | backend    |  | (nginx, static      |
                     +----------v----------+     | (:8000     |  |  Grand Admin build, |
                     |  loady-postgres     |     |  internal) |  |  :80 internal)      |
                     |  (existing, NO host |     +-----+------+  +---------------------+
                     |   port mapping)     |           |
                     +---------------------+     +-----v------+
                                                  | platform-  |
                     Loady SQLite DBs live on     | core-      |
                     the loady-backend            | postgres   |
                     container's own volume       | (NEW, NO   |
                     (app-data), unrelated to      | host port) |
                     Platform Core.                +------------+
```

### Networks

| Network | Members | Purpose |
|---|---|---|
| `default` (existing, unnamed/`loady_default`) | `loady-reverse-proxy`, `loady-backend`, `loady-postgres` | Unchanged. Platform Core containers never join this network. |
| `platform-net` (**new**, internal-only, no external DNS) | `nginx edge` (as a second interface), `loady-backend` (as a second interface), `platform-core-backend`, `platform-core-postgres`, `platform-core-admin-frontend` | Carries only: OIDC discovery/JWKS fetch, authorization-code token exchange, entitlement/status lookups, and edge→backend proxying for `id.*`/`admin.*`. Plaintext HTTP internally is the same accepted single-host limitation already documented in `STAGING_ARCHITECTURE.md`; it does not cross the host boundary. |

`loady-backend` joining a second network is the only topology change to
the existing Loady container; its own network/volumes/ports are otherwise
untouched.

### Ports

| Port | Bound by | Exposure |
|---|---|---|
| 80 | nginx edge | Public (Cloudflare) — ACME/redirect only, same as today |
| 443 | nginx edge | Public (Cloudflare) — Full-strict TLS terminates here, same as today |
| 8000 (loady-backend) | loady-backend | Internal only (unchanged) |
| 8000 (platform-core-backend) | platform-core-backend | Internal only, on `platform-net` |
| 80 (platform-core-admin-frontend) | platform-core-admin-frontend | Internal only, on `platform-net`, proxied via `admin.loady.cc` |
| 5432 (both Postgres instances) | loady-postgres, platform-core-postgres | Internal only — never mapped to a host port, in either stack |

No new *public* port is introduced. Two new *hostnames* are required
(`id.loady.cc`, `admin.loady.cc`) — this is a real Cloudflare DNS change
and is explicitly **not performed** by this mission (see Absolute Safety
Rule). It is tracked as a cutover-preflight task in
`LOADY_PRODUCTION_CUTOVER_RUNBOOK.md`.

### Databases

- `loady-postgres` (existing) — untouched, unchanged schema ownership.
  Loady's two SQLite files (`app.db` commercial/history data, per
  `backend/app/config/paths.py`) continue to live on the `loady-backend`
  container's own `app-data` volume — Platform Core never reads or writes
  either.
- `platform-core-postgres` (**new**) — its own volume
  (`platform-postgres-data`), its own credentials, never shared with
  Loady's Postgres instance or the `loady` project's volumes.

### Secrets, signing keys, encryption keys

- Platform Core's RS256 signing key: a single persistent file, bind-mounted
  read-only into `platform-core-backend` only (mirrors the staging pattern
  in `platform-core/compose.staging.yml`) — never mounted into any other
  container, never placed on the `platform-net` filesystem shared with
  Loady.
- Loady's `TokenEncryptionService` AES-256-GCM key: an env var supplied to
  `loady-backend` only; Platform Core never sees Loady's encrypted refresh
  tokens or this key.
- `PLATFORM_CLIENT_ID` / `PLATFORM_CLIENT_SECRET`: Loady-side env vars
  identifying it to Platform Core as an OAuth client — same mechanism as
  staging, rotated independently of the signing key.
- None of the above are committed, templated with real values, or embedded
  in any compose file — see `PRODUCTION_SECRET_INVENTORY.md`.

### Backups

- `platform-core-postgres` gets its own `pg_dump` cycle, independent of
  Loady's existing backup process — they must not be combined into one
  archive (different restore procedures, different sensitivity: Platform
  Core's dump contains password hashes and OAuth client secrets *hashes*
  for every ecosystem product, not just Loady).
- Backup storage location and encryption requirements are identical for
  both — see `PRODUCTION_SECRET_INVENTORY.md` and the Backup Security
  section (`docs/platform/PLATFORM_BACKUP_RESTORE.md`, extended by Mission
  5's `PRODUCTION_ROLLBACK_REHEARSAL.md`).

## Resource contention note

Platform Core adds two more Postgres processes' worth of memory pressure
(its own + admin-frontend's static nginx, which is negligible) to a VPS
that already runs Loady's backend, Postgres, and reverse proxy. See
`PRODUCTION_CAPACITY_PLAN.md` (Phase 37) for the concrete estimate and
recommended container resource limits — this document only fixes the
*shape*, not the sizing.

## Explicitly out of scope for this document

- Actually creating `id.loady.cc` / `admin.loady.cc` DNS records or
  Cloudflare configuration.
- Actually deploying any of the above to the production VPS.
- Measuring real free RAM/disk/CPU on the production VPS (requires SSH
  access this mission does not have; tracked as a cutover preflight task).
