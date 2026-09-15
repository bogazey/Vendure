# Production Data Migration Inputs (Mission 15, Phase 17)

**No production database is accessed by this mission.** This states
exactly what the identity-migration tooling (`loady_migration_service.py`,
invoked via `loady_migration_dry_run.py`) needs from Loady's production
data, separating read-only preflight/metadata queries from the actual
migration data flow.

## What the migration tool actually reads (confirmed from `loady_migration_service.py`)

- Loady's `users` table: `id`, `email`, `password_hash`, `email_verified`,
  `is_disabled`/`status`, `created_at`, existing `global_user_id` (if
  already linked from a prior partial run).
- Loady's plan/entitlement state for each user (to seed the initial
  Platform Core entitlement row, `EntitlementSource` derived from whatever
  Loady's own record shows — Paddle-paid, gifted, or free).
- **Never reads**: Paddle customer/subscription/transaction identifiers
  (`LOADY_PRODUCTION_MIGRATION_PLAN.md` §5 — explicitly out of scope,
  those stay in Loady's database permanently), download history contents,
  media files, or any other product data unrelated to identity/entitlement.

## Preflight/metadata queries (read-only, safe to run against a live replica or the restored snapshot) — never the actual migration data itself

These answer "is the data shape what the tool expects" without touching
individual rows:

```sql
-- Row count only, not content
SELECT count(*) FROM users;
-- Duplicate-email detection (a real Loady data-integrity issue the tool
-- would surface as duplicate_local_reference, cheaper to catch here first)
SELECT email, count(*) FROM users GROUP BY email HAVING count(*) > 1;
-- Already-linked count (idempotency sanity - should be 0 before a first
-- production run, non-zero and stable across dry runs is expected after)
SELECT count(*) FROM users WHERE global_user_id IS NOT NULL;
```

## Actual migration data flow (Stage 2/3 of `LOADY_PRODUCTION_MIGRATION_PLAN.md`)

- **Dry run**: `loady_migration_dry_run.py` against a **restored snapshot**
  of production (never the live database directly) — zero writes to
  either database, produces the `created`/`linked`/`skipped`/`conflicted`/
  `failed` report only.
- **Commit**: the same tool with `--commit`, during the defined maintenance
  window, against the real production database — this is the one step
  that actually writes `global_user_id` values back into Loady's `users`
  table and creates the corresponding Platform Core `User`/entitlement
  rows.

## What is never printed, logged, or transmitted by this tooling

- Password hashes (read and re-verified/copied at the storage layer only —
  never displayed in any report, log line, or terminal output; confirmed
  by reading `loady_migration_service.py` and its dry-run report
  structure, which contains only counts and user *identifiers* per
  category, never hash values).
- Any Paddle-issued token, API key, or webhook secret — none of this
  tooling touches Paddle-related tables at all.
- Any session/refresh token.

## Separation of concerns restated (per Phase 17's explicit instruction)

| Kind of query | When it runs | Against what | Writes? |
|---|---|---|---|
| Metadata/preflight (row counts, duplicate detection) | Any time, including before a restore exists (against a live read replica if one exists) | Read replica or restored snapshot | Never |
| Dry-run migration | Stage 2, before the maintenance window | Restored snapshot only | Never |
| Commit migration | Stage 3, during the maintenance window | Real production database | Yes — the one and only writing step in this entire inventory |

This mission does not request, and was not given, any of the above —
every SQL statement in this document is a statement of what the *existing,
already-built* tooling does, verified by reading its source, not something
this mission ran.
