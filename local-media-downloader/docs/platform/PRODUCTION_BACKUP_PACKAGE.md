# Production Backup Package (Mission 15, Phases 19-20)

Consolidates the already-built backup/restore mechanism
(`scripts/platform/backup-before-platform-migration.sh`,
`scripts/platform/verify-backup-restorable.sh`, `PLATFORM_BACKUP_RESTORE.md`)
against Phase 19/20's explicit checklist, and documents the one genuine gap
found and fixed this mission (disk-space preflight).

## Coverage checklist

| Requirement | Status |
|---|---|
| Loady PostgreSQL | `pg_dump -Fc`, encrypted in place (`openssl enc`, AES-256-CBC+PBKDF2), immediately after dumping |
| Loady SQLite (history/app data, `app.db`) | Copied via `docker cp`, encrypted in place, same mechanism |
| Platform Core PostgreSQL | Same `pg_dump` treatment, **skipped gracefully with a clear message** if not yet running (correct behavior pre-deployment) |
| Configuration inventory | Variable **names only**, never values — `docker exec ... env \| cut -d= -f1` |
| Migration versions | `alembic current` captured for both services into `migration_versions.txt` |
| Timestamp | `date -u +%Y%m%dT%H%M%SZ`, embedded in the run directory name |
| Checksum | `sha256sum`/`shasum` over every artifact in the run directory, written to `CHECKSUMS.sha256` |
| Permissions | `chmod 700` on the run directory, `chmod 600` on every artifact, immediately after creation |
| Restore validation | `verify-backup-restorable.sh` — restores into an **isolated** container, confirms row counts/schema, never assumes success from `pg_dump`'s exit code alone |

## Genuine gap found and fixed this mission: no backup-space preflight (Phase 20)

**Finding**: neither `backup-before-platform-migration.sh` nor any other
script checked free disk space before writing a single byte. On the
single-VPS architecture this mission is packaging for — where
`SINGLE_VPS_FAILURE_DOMAIN_REVIEW.md` already identifies disk exhaustion as
the single scariest failure mode (real SQLite corruption risk) — an
oversized backup attempt on a nearly-full disk could itself trigger the
exact outage the backup exists to protect against.

**Fix**: added a mandatory preflight to
`backup-before-platform-migration.sh`, inserted immediately after the
container-liveness checks and **before** `mkdir -p "$OUT_DIR"` (before any
directory is even created, let alone written to):

1. Sum the current size of every real source: Loady Postgres
   (`pg_database_size()`), Loady's `app.db` (`stat -c%s`), and Platform
   Core Postgres (`pg_database_size()`, if running).
2. Apply a 1.5× safety factor plus a fixed 200 MiB floor (covers inventory
   files and filesystem overhead — the encrypted output is comparable in
   size to the plaintext it replaces in place, and the plaintext is
   deleted immediately after each artifact is encrypted, so peak *extra*
   usage at any instant is at most one artifact's size, never the running
   sum of everything already encrypted).
3. `df` the nearest existing ancestor of the requested output directory
   (since it may not exist yet) and compare.
4. `NO-GO` with a clear message and `exit 1` if insufficient — **before**
   any dump, copy, or encryption step runs.

**Regression test added**:
`scripts/platform/test-backup-space-preflight.sh` — stubs `docker` and
`df` to deterministically exercise both the insufficient-space (NO-GO,
exit 1) and sufficient-space (preflight passes, script proceeds to the
next step) cases without needing a real database or a real disk anywhere
near capacity. **Both cases pass** (run this mission: `ALL PASSED`).

## What this backup package explicitly does not newly claim

- It does not claim the backup/restore mechanism has been measured at real
  production data scale — only at small synthetic-staging scale
  (`FINAL_PREPRODUCTION_EVIDENCE_AUDIT.md` §4). The new disk-space
  preflight makes an undersized *destination* fail safely and early; it
  does not change how long a large real backup actually takes, which
  remains `PRODUCTION PREFLIGHT REQUIRED`/`LIVE OBSERVATION ONLY` for
  timing purposes (carried into Phase 40's recovery-time-target document).
- It does not add off-site backup configuration — the mechanism
  (`--offsite`, `BACKUP_OFFSITE_CMD`) already exists and is invocation-
  tested, but no real remote target is configured anywhere
  (`MISSION_7_ARCHITECTURE_AUDIT.md` §5) — a genuine, already-classified
  `INFRASTRUCTURE BLOCKER`/`CREDENTIAL BLOCKER`, not a code gap this
  mission needs to close.
