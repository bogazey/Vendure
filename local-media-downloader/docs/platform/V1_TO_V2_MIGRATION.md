# V1 → V2 Migration

Alembic revision `4a35a2c457fb` (`down_revision = f006149cdf49`, the
original Mission 5 "create platform core tables" migration). Mission-
brief Phase 46.

## What it does

Purely additive:

- 11 new tables: `entitlement_definitions`, `plan_entitlements`,
  `subscriptions`, `subscription_items`, `billing_webhook_events`,
  `gifted_access`, `bundles`, `bundle_product_plans`, `bundle_access`,
  `service_grants`, `outbox_events`.
- 2 new nullable columns on `oauth_clients` (`webhook_url`,
  `webhook_signing_secret`).
- 6 new nullable columns on `payment_records` (`subscription_id`,
  `tax_cents`, `fee_cents`, `net_cents`, `refunded_amount_cents`,
  `occurred_at`) plus a foreign key from `subscription_id` to the new
  `subscriptions` table.

No V1 table is dropped, renamed, or has a column removed. No existing
column's type or nullability changes. No existing row's data is
transformed.

## SQLite compatibility note

The `oauth_clients`/`payment_records` column additions use
`op.batch_alter_table(...)` rather than plain `op.add_column`/
`op.create_foreign_key`, because SQLite cannot `ALTER TABLE ... ADD
CONSTRAINT` a foreign key directly (only Alembic's batch/copy-and-move
mode can do this against SQLite). On PostgreSQL, batch mode transparently
emits the equivalent plain `ALTER TABLE` statements - this is the
portable form for both the local SQLite dev/test database and a future
Postgres deployment, matching mission-brief Phase 46's "must work with a
populated V1 database" on whichever engine that database actually is.

## What was actually verified in this mission

- **Upgrade from a fresh V1-head SQLite database**: applied cleanly
  (`alembic upgrade head` from `f006149cdf49`).
- **Downgrade**: `alembic downgrade -1` cleanly reverses every new table/
  column/constraint back to the exact V1 schema.
- **Re-upgrade**: applying `head` again after the downgrade succeeds
  identically (no leftover state from the round trip).
- **Existing V1 test suite** (77 tests covering identity, SSO, RBAC,
  entitlements, audit, the Loady migration service, session status, the
  JWT signing key) - all still pass, unmodified except for one test whose
  own assertion (`count() == 0` across the entire `PaymentRecord` table)
  was scoped to a specific user id, because Mission 6 now legitimately
  writes `PaymentRecord` rows elsewhere in the same test database from
  real (fake-provider) webhook processing. See
  `MISSION_6_SECURITY_REVIEW.md` if you're looking for this in the
  security findings list - it isn't one; it's a test-isolation fix,
  documented here since it touches a Mission 5 file.

## What was NOT verified in this mission

- **Upgrade against a real PostgreSQL database.** All verification above
  ran against SQLite (this environment's dev/test database engine - see
  `LOCAL_DEVELOPMENT.md`). The migration was written to be dialect-
  portable (see the batch-mode note above) and the same pattern the V1
  migration already used for its own tables, but a real `alembic upgrade
  head` against Postgres was not executed in this mission. **Report this
  as UNTESTED, not passing**, until it is actually run against Postgres
  (mission-brief `PRODUCTION_TOPOLOGY.md`/`STAGING_ARCHITECTURE.md`
  describe where that database lives; this mission did not touch it -
  see Phase 56's "no production access" rule).
- **Upgrade against a populated V1 database with real user/entitlement/
  payment data** (as opposed to an empty freshly-migrated one). Mission
  5's own `PRODUCTION_ROLLBACK_REHEARSAL.md`/rehearsal-artifacts describe
  exercising migrations against realistic data volumes; this mission's
  migration testing used an empty database plus the application test
  suite's own fixtures, not a restored production/staging snapshot.

## Loady compatibility (mission-brief Phase 46's other half)

Nothing in this mission touches `loady_migration_service.py`,
`test_loady_migration.py`'s migration logic, or any of the existing
Loady↔Platform-Core OIDC integration code paths
(`oidc_service.py`, `routes_oauth.py`'s authorization-code grant,
`routes_v1.py`). The full existing Loady migration test suite (16 tests
in `test_loady_migration.py`, `test_loady_hash_compatibility.py`) passes
unmodified. Loady's own backend (`backend/` at the repo root, outside
`platform-core/`) was not touched at all in this mission.
