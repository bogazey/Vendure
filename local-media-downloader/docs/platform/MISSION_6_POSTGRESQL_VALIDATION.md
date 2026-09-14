# Mission 6 Continuation — Real PostgreSQL Validation

The prior Mission 6 session verified every migration against SQLite only
and explicitly flagged that as insufficient. This section was executed
for real, in this session, against a real PostgreSQL 16 server - not
re-read from a script, not inferred from the SQLite result.

## Isolation (mandatory constraint honored)

A brand-new, fully isolated Docker network (`mission6-net`) and container
(`mission6-catalog-postgres`, image `postgres:16-alpine`, port `15432`
published only to `127.0.0.1`, database `platform_core_mission6`) were
created for this validation only. The pre-existing personal-use stack
(`loady-postgres-1`, `loady-staging-postgres-1`,
`platform-core-staging-postgres-1`, and every other already-running
container discovered via `docker ps` at the start of this session) was
never stopped, started, execed into, or connected to. The container and
network created for this validation were torn down
(`docker rm -f mission6-catalog-postgres && docker network rm
mission6-net`) at the end of this session.

## What was executed and verified

1. **Fresh upgrade**: `alembic upgrade head` against an empty database -
   all 3 Mission 6 migrations (`4a35a2c457fb`, `e76146991275`,
   `8e2a4ae9d31e`) applied cleanly on top of the Mission 5 baseline
   (`f006149cdf49`). Resulting schema: 30 application tables (31 with
   `alembic_version`) - every one of them, confirmed via
   `information_schema.tables`.
2. **Full downgrade to base, then re-upgrade to head**: `alembic
   downgrade base` followed by `alembic upgrade head` - both directions
   ran without error. This specifically exercises the `op.batch_alter_
   table(...)` blocks added for SQLite compatibility: on Postgres, batch
   mode transparently falls back to plain `ALTER TABLE` statements, and
   this run confirms that fallback actually works, not just that it's
   theoretically supposed to.
3. **Populated-table migration safety** (mission-brief Phase 46's actual
   bar): downgraded to the revision immediately before the final
   migration, inserted real rows into `products`/`plans`/`oauth_clients`/
   `users` by hand (including a `users` row exercising the *previous*
   migration's own `security_epoch` NOT NULL column), then re-ran
   `alembic upgrade head`. The pre-existing `plans` row came out with
   correctly backfilled defaults (`status='active'`, `is_public=true`,
   `sort_order=0`, `upgrade_rank=0`, `gifted_eligible=true`,
   `trial_eligible=true`) and the `oauth_clients` row correctly gained
   `webhook_signing_secret_encrypted` (NULL, since it had no prior
   plaintext secret) with the old plaintext column dropped.
4. **Constraints**: verified with real INSERT attempts, not schema
   inspection alone -
   - `uq_plan_product_slug` correctly rejected a duplicate plan slug
     within the same product (`psycopg.errors.UniqueViolation`).
   - `uq_billing_webhook_event` correctly rejected a duplicate
     `(provider, provider_event_id)` pair.
   - The `prices.plan_id` foreign key correctly rejected a price
     referencing a nonexistent plan (`psycopg.errors.ForeignKeyViolation`).
5. **Concurrency - twice**:
   - Five real, independent `psycopg` connections raced to `INSERT` the
     same `(provider, provider_event_id)` webhook-event row
     simultaneously (synchronized with a `threading.Barrier`). Exactly
     one succeeded; the other four hit `UniqueViolation`, confirming
     Postgres's own MVCC/row-locking behavior enforces the same
     invariant true concurrent transactions need (SQLite's single-writer
     serialization can mask a race that would slip through on a
     database that actually allows concurrent writers).
   - The same check was repeated one level up, through the real
     application code path
     (`webhook_service.receive_webhook`, not raw SQL): three concurrent
     threads, each with its own SQLAlchemy session bound to this
     Postgres instance, delivered the identical webhook event
     simultaneously. Exactly one `BillingWebhookEvent` and one
     `Subscription` row resulted - confirming the `IntegrityError`-catch
     idempotency path in `webhook_service.py` (originally only exercised
     against SQLite's `sqlite3.IntegrityError`) also works correctly
     against `psycopg`'s own exception hierarchy.
6. **Backup/restore with full V2 schema coverage** (also closes the
   separate "Backup/Restore V2" mission item - see below): real data was
   seeded across every table category the mission brief listed (users,
   products, plans, plan versions, prices, capabilities, entitlements,
   subscriptions, gifted access, promotions/trials, bundles, payments,
   billing webhook events, sessions/refresh tokens, account closure
   requests, service grants, audit log, outbox), row counts captured,
   `pg_dump -F c` run, restored into a second fresh database
   (`platform_core_mission6_restore`) via `pg_restore --no-owner`, and
   row counts re-captured and compared - all 23 checked tables matched
   exactly (12/12 users, 33/33 audit log entries, and so on for every
   other table).

## What this does NOT cover (reported honestly, not implied)

- The full **application pytest suite** (199 backend + 19 SDK tests)
  still runs against SQLite - `tests/conftest.py` hard-sets
  `DATABASE_URL` to a temp SQLite file at import time. Re-running the
  entire suite against Postgres would require a conftest change
  (parametrizing the database backend) that was judged out of scope for
  this validation pass, whose purpose was proving the *migration and
  schema* are Postgres-safe, not re-deriving already-passing application
  logic on a second database engine.
- **Performance/load testing** under Postgres was not attempted - only
  correctness (constraints, concurrency-safety, migration mechanics).
- **Backup/restore was not exercised through the actual staging
  `backup-before-platform-migration.sh` script** - it was exercised
  directly via `pg_dump`/`pg_restore` against the isolated Mission 6
  container, which is what that script itself wraps; the script's own
  orchestration (Docker Compose service names, `docker cp` sequencing)
  was not re-run since doing so would have required touching either the
  real staging stack (`platform-core-staging-postgres-1`, explicitly
  off-limits) or nontrivially reconfiguring the script for a one-off
  container.
