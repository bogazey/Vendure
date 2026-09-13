# Production Rollback Rehearsal (Mission 5, Phases 20-24)

Status: EXECUTED against `loady-staging` / `platform-core-staging` on this
machine. All timings and findings below are measured, not estimated.
Nothing here touched real production.

## Phase 20 — Disaster scenario decision table

For each injected failure, the objective decision (continue / retry /
rollback / restore) and how it was actually exercised in this mission:

| # | Scenario | Decision | Exercised how |
|---|---|---|---|
| A | Migration stopped before commit | **Continue** — dry run made zero writes (verified by direct row-count check); simply re-run when ready. No cleanup needed. | Live (phase 7) |
| B | Migration interrupted mid-transaction | **Retry** — `loady_migration_service` processes phase 1 (identity) fully before phase 2 (memberships/entitlements) begins, and is re-run idempotently end to end; a kill between phases leaves already-resolved `global_user_id` links in place and phase 2 safely re-processes on the next run. | Reasoned from code (`loady_migration_service.py`'s two-phase structure) + confirmed idempotent re-run behavior live (phase 8) |
| C | Platform Core unavailable immediately after migration | **Continue** — Loady's hybrid gate serves the freshly-written cache (`source: "live"` writes the cache unconditionally on the migration's own entitlement calls) for up to `ENTITLEMENT_CACHE_TTL_MINUTES` (15 min); no rollback needed for a short outage. | Live (phase 14) |
| D | Loady restart failure | **Restore** — if Loady's container won't come back up (bad image, bad config), the fix is a container/config-level restore (previous image tag / `.env` from backup), not a database rollback. | Reasoned; not independently forced (would require deliberately breaking the image, out of scope for this pass) |
| E | Platform Core restart failure | **Restore** — same as D, but for Platform Core; Loady's hybrid gate continues serving cached entitlements the whole time this is being fixed (see C), so this is not itself an emergency for Loady's paying users, only for new logins/central-disable propagation. | Live (phases 14-15 prove the "Loady keeps working" half; the "Platform Core itself fails to restart" half is reasoned, not forced) |
| F | Bad configuration (e.g. wrong signing key, wrong encryption key) | **Rollback the config change**, not the database — both failure modes were proven to fail closed without any data corruption, so the fix is "restore the correct config value," never a DB restore. | Live (phases 16-17) |
| G | Database unavailable (either side) | **Continue** (Loady/entitlement reads, via cache) or **wait/restore infra** (any write path, which correctly fails safely with no corruption). | Live (phase 15) |
| H | Incorrect encryption key | **Rollback the key**, not the database — proven to fail closed (falls back to cache, or fails closed if cache is also expired), never crashes, never leaks plaintext, never silently destroys the unreadable row. | Live (phase 17) |

None of these eight scenarios requires a full database rollback by itself
— every one of them is contained by either the hybrid-availability design
(C, E, G) or a simple config/container fix (D, F, H). A full rollback
(phases 21-23 below) is reserved for the scenario none of these are:
**the migration itself produced data you don't trust** (e.g. a
reconciliation failure, or — as this rehearsal actually found — a
migration re-run silently overwriting a post-migration entitlement
change; see Phase 23 below).

## Phase 21 — Rollback execution (real, sequential, as production would run it)

Not a Postgres/Alembic downgrade — the actual layered sequence from
`docs/platform/LOADY_ROLLBACK_PLAN.md`, executed via
`scripts/platform/rollback-platform-migration.sh`:

1. **Layer 1 — kill switch**: `PLATFORM_CLIENT_ID`/`PLATFORM_CLIENT_SECRET`
   blanked in Loady's env file, backend container recreated. Verified via
   `GET /api/auth/platform/status` → `{"enabled": false}`.
2. **Layer 2 — full database restore**: a checksummed backup (taken
   moments earlier with `backup-before-platform-migration.sh` and
   independently verified restorable with `verify-backup-restorable.sh`)
   was restored directly into `loady-staging`'s live Postgres (drop +
   recreate + `pg_restore`), then the backend was restarted against it.

### Validated after rollback

- **Old passwords work**: two real accounts (`login-rehearsal-user`,
  `gate-creator`) logged in successfully via Loady's own local
  `/api/auth/login` — HTTP 200 both — with Platform Core integration
  fully disabled.
- **Users/history/usage remain**: user count unchanged (54); Loady's
  history SQLite file intact and growing normally on new downloads.
- **Plans remain, correctly, for locally-backed subscriptions**: all 18
  synthetic `paddle`-provider `Subscription` rows and all 5 local
  `gifted`-provider rows survived untouched (these were never dependent
  on Platform Core — Loady's own pre-existing gift mechanism, not the
  Platform Core Grand Admin one).
- **Downloads work**: a real download request succeeded (201) against
  the rolled-back stack.
- **Platform Core is no longer required for authentication**: confirmed
  via the `enabled: false` status and successful local-only logins.
- **No migrated global-identity requirement blocks Loady**: accounts
  keep their `global_user_id` value (rollback does not scrub it — matching
  `LOADY_ROLLBACK_PLAN.md`'s documented choice to treat full unlink as a
  separate, more drastic step) but it is simply never consulted while the
  integration is disabled - confirmed live, not just by code reading.
- **A real, honest limitation surfaced**: `gate-creator`'s Gifted Creator
  entitlement — granted directly through Platform Core/Grand Admin
  **after** the initial migration, with **no corresponding local Loady
  `Subscription` row** — did **not** survive rollback. Requesting a
  Creator-tier download (2160p) after rollback correctly fell back to
  Free (402), because Loady's local database has no record of that grant
  at all; it only ever existed in Platform Core. This is not data loss in
  the sense of anything being deleted — it's an inherent consequence of
  where that grant was stored, and it is the **correct, safe direction to
  fail** (an entitlement disappearing on rollback, never one appearing
  that shouldn't). It should be stated plainly in the cutover runbook:
  *any entitlement change made exclusively through Grand Admin after
  cutover is not preserved by a rollback to the pre-Platform-Core
  architecture.*

## Phase 22 — Measured rollback duration

| Stage | Duration |
|---|---|
| Layer 1 (kill-switch: edit env, recreate container) | 5s |
| Database restoration (drop/create/`pg_restore`) | 51s |
| Container/app switch (restart backend against restored DB) | 14s |
| Validation (login × 2, download, data-integrity queries) | 40s |
| **Total** | **110s (~1 min 50s)** |

**Caveat, stated plainly**: this measures restoring from a backup file
**already sitting on local disk**. A real production recovery-time
estimate must add however long it takes to retrieve the actual backup
from wherever it is stored (see `PRODUCTION_SECRET_INVENTORY.md` /
backup-security section — off-server storage is a stated gap, not yet
implemented) — that retrieval time is the dominant unknown for a real
incident, not the restore mechanics measured here, which scale with
database size (this was a 54-user staging database; a real production
Loady database is larger and `pg_restore` will take correspondingly
longer). Recommend budgeting **10-20 minutes total** for a real
production rollback as a first planning estimate, dominated by backup
retrieval and human decision time, not the mechanical steps.

## Phase 23 — Second migration after rollback (repeatability)

Re-ran `loady_migration_dry_run.py --commit` immediately after the full
restore (with the kill-switch lifted again): **0 created, 52 skipped, 1
conflicted, 1 failed** — identical shape to every prior run, and
critically **zero new Platform Core users or duplicate rows** — a
rollback does not make a second migration impossible.

**A second real finding surfaced here**: re-running the migration for an
already-linked user is not a true no-op — it **re-derives and overwrites
that user's Platform Core entitlement from Loady's current local
subscription state on every run**, not just for newly-created accounts.
This is exactly what silently reset `gate-creator`'s entitlement back to
`free` during this very re-run (their Grand-Admin-only gift was
overwritten to match Loady's own — unrelated — local state, which has
always been Free for that account). The tool's own report already
signals this if read carefully: a row appearing under `SKIPPED` still
carries its **current, just-written** `entitlement_source`/`plan`
fields, which can differ from what it was a moment before the run.

**Recommendation for the cutover runbook**: do not treat
`loady_migration_dry_run.py --commit` as safe to re-run casually after
initial cutover for routine maintenance once any Grand-Admin-only
entitlement changes exist for migrated accounts. It remains the right
tool for backfilling **newly signed-up** accounts, but re-running it
against the **whole** user set will resync every already-linked
account's entitlement to Loady's local truth, silently discarding
Platform-Core-only changes made since the last run. If this needs to
change before cutover, the fix is to make the entitlement-sync step
skip accounts whose entitlement was last modified by a source other than
this migration tool (i.e. compare `Entitlement.reason`/an explicit
migration marker) - not attempted in this mission, tracked as a
MEDIUM-severity follow-up (see `PRODUCTION_READINESS_CHECKLIST.md`).

## Phase 24 — Backup corruption detection

A **copy** of a verified-good backup was corrupted (40 bytes overwritten
mid-file in the Loady Postgres dump). `verify-backup-restorable.sh`
correctly caught it at the checksum-verification step, before any
restore was attempted: `loady_postgres.dump: FAILED`, exit code 1,
`NO-GO: checksum verification failed`. The original, uncorrupted backup
was re-verified restorable immediately afterward to confirm it was never
touched by the test.

## Overall Phase 20-24 result: **PASS**

The rollback mechanism is proven to work, is fast (110s at this scale),
does not lose committed Loady-native data, and does not block a
subsequent re-migration. Two real findings were produced (Platform-Core-
only entitlements aren't preserved by rollback; re-running the migration
resyncs — and can silently downgrade — already-linked accounts'
entitlements) and are carried into `PRODUCTION_READINESS_CHECKLIST.md`
and the cutover runbook rather than hidden.
