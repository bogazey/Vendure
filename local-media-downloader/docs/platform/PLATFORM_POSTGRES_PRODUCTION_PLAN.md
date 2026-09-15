# Platform Core PostgreSQL Production Plan (Mission 15, Phase 10)

## Identity

| Property | Value |
|---|---|
| Database name | `${PLATFORM_POSTGRES_DB}` (operator-chosen, e.g. `platform_core_production`) |
| User | `${PLATFORM_POSTGRES_USER}` |
| Volume | `platform-postgres-data` (declared in `compose.rc.yml`, distinct from Loady's `postgres-data`) |
| Network | `platform-net` only — **no host port**, confirmed via direct read of `compose.rc.yml` (`expose: ["5432"]`, no `ports:`) |
| Image | `postgres:16-alpine`, same version pin as Loady's own instance — no version drift between the two |
| Healthcheck | `pg_isready -U $POSTGRES_USER -d $POSTGRES_DB`, 10s interval, 10 retries |
| Resource limits | 0.50 CPU / 512M memory (`compose.rc.yml`) |

## How this stays distinct from Loady's Postgres (preventing an operator from ever pointing a tool at the wrong one)

- Different container name (`platform-core-postgres` vs `postgres`), different
  network (`platform-net`-only vs `default`-only), different volume, different
  credentials, different database name convention (`platform_core_production`
  vs `loady_production` — deliberately dissimilar prefixes, not just a
  different suffix, specifically so a truncated terminal display or a
  copy-paste error is more likely to be caught by a human reading it).
- Every operator script that touches a database takes the connection target
  as an explicit, named argument/env var — `verify-migration.sh`'s
  `loady_q`/`platform_q` helper functions are two distinct functions with
  two distinct connection targets, never a single parameterized function an
  operator could call with the wrong argument by habit.
- The read-only preflight script (Phase 18) checks both `platform-core-backend`
  and `backend` (Loady) Alembic heads **separately**, never assuming one
  database's healthy migration state implies the other's.

## Connection pool assumptions

Platform Core's SQLAlchemy engine configuration is not tuned beyond
defaults in any code read this mission — no `pool_size`/`max_overflow`
override found in `platform-core/backend/app/database/`. Given the V1
workload (SSO logins, entitlement lookups, Grand Admin, and — once
authorized — billing webhooks, all for a single product's user base), this
is an acceptable default for initial cutover; a real connection-pool tuning
pass is out of scope for this mission (no evidence of it being a proven
bottleneck, and no feature creep) but should be revisited if Phase 41's
post-cutover monitoring shows connection saturation.

## Backup

- Independent `pg_dump` cycle from Loady's Postgres (`PRODUCTION_TOPOLOGY.md`
  §Backups) — **never combined into one archive**: different restore
  procedure, different sensitivity (Platform Core's dump contains password
  hashes and OAuth client secret hashes for *every* ecosystem product, not
  just Loady's users).
- Uses the same encrypted, checksummed, permission-verified mechanism
  already built and proven for Loady's own backups
  (`scripts/platform/backup-before-platform-migration.sh`,
  `verify-backup-restorable.sh`) — extended to a second target database,
  not a new mechanism.
- Restore verification (Phase 19/48) must restore into an isolated
  container and confirm row counts / schema version, exactly as already
  proven for Loady's backup — never assumed successful from `pg_dump`'s
  exit code alone.

## Migration procedure

- Alembic, same tool Loady itself uses. `platform-core-backend`'s own
  entrypoint (`docker-entrypoint.sh`) runs migrations on container start —
  confirmed this is the existing pattern (mirrors Loady's own
  `backend/Dockerfile`/entrypoint convention).
- Migration safety review of every Platform-Core-side Alembic revision is
  Phase 29's job, not repeated here — this document only fixes *where* and
  *how* migrations run, not whether each one is individually safe.
- **Never point a migration or a restore at Loady's database** — enforced
  today only by convention (separate `DATABASE_URL`s, separate scripts),
  not by a hard runtime guard. This mission does not add a new runtime
  guard (no evidence any operator script currently *can* be pointed at the
  wrong database by an ordinary invocation — each script's connection
  target is a distinct named argument, not a shared generic one) — flagged
  here as an accepted, convention-based safeguard, not a code gap.

## Preventing accidental backup/restore against the wrong DB

- `backup-before-platform-migration.sh` and `verify-backup-restorable.sh`
  take the container/database name as an explicit argument, not a
  positional guess — an operator must name `platform-core-postgres`
  explicitly to back it up, and naming it wrong fails immediately with
  "container not found" rather than silently backing up the wrong data
  (Docker container names are unique per host).
- The two databases' backup archives are namespaced by container/timestamp
  in their filenames (existing pattern) — a restore operation naming the
  wrong archive file restores into whichever container the operator
  explicitly targets, which (per the point above) requires an explicit,
  visibly-wrong name to go wrong. This is a process safeguard, not a
  cryptographic one — human error during a manual invocation is still
  possible and is exactly what Phase 27's "command safety" validation
  (hostname/working-dir/target checks before any dangerous command) exists
  to reduce further.
