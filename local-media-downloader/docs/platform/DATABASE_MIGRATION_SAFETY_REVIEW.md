# Database Migration Safety Review (Mission 15, Phase 29)

Every Alembic migration in both services was read in full (via a
dedicated research pass this mission, not sampled or inferred from
filenames). Full chain order, per-migration classification, and locking
risk below.

## Loady backend — 12 migrations (chain: `20491e9286b1 → 2b437cf7ea5c → 224af020fc5a → 3a7c1e9f2b6d → 7b2e4f1a9c3d → 9f1c6a4e7d2b → 4c8a1f2e6b9d → 7d2e9a4c1f83 → 8a1e5c3f9b02 → 9c3d7f1a4e56 → 57212c63a9d9 → a13f8e2c6b47`)

All 12 have working, symmetric `downgrade()` implementations — zero
forward-only or `pass`-only downgrades.

**9 of 12 safe to run as a plain `alembic upgrade head`, no special
handling**: `20491e9286b1` (initial schema), `2b437cf7ea5c` (new table),
`3a7c1e9f2b6d` (new table + 4 seed rows — DATA-TRANSFORMING but
config-only, not user data), `7b2e4f1a9c3d` (new table), `9f1c6a4e7d2b`
(NOT NULL add with `server_default=false()` — correct safe pattern),
`4c8a1f2e6b9d` (new table), `9c3d7f1a4e56` (new table), `57212c63a9d9`
(new table), `a13f8e2c6b47` (nullable add — current head).

**3 need production scheduling awareness (LOCKING-RISK — brief write lock
during FK validation or non-`CONCURRENT` index build, not data-unsafe)**:

| Revision | What locks | Recommendation |
|---|---|---|
| `224af020fc5a` | New FK + index on `billing_events` | Check table size; low-traffic window if large |
| `7d2e9a4c1f83` | New FK on `subscriptions` | Same |
| `8a1e5c3f9b02` (`global_user_id`) | **New UNIQUE index on `users`** — likely the largest/hottest table | Highest priority of the three to schedule carefully; this is the exact migration the identity cutover depends on |

**No `nullable=False` without a `server_default` found anywhere** — the
one NOT NULL add on an existing table (`remember_me`) correctly ships
with a default. **No forward-path `DROP COLUMN`/`DROP TABLE` found.** The
one UNIQUE constraint added to an existing table (`global_user_id`) is
safe because the column is brand new (every existing row is `NULL`, and
Postgres treats multiple `NULL`s as non-conflicting for uniqueness).

**Real, actionable finding — stale orphaned revisions**: `backend/alembic/versions/`
contains only 12 `.py` files, but `__pycache__` holds two extra compiled
files with no matching source — `5689146ea1c8_create_commercial_tables`
and `e600701e18eb_create_commercial_tables` (both earlier rewrites of what
became `20491e9286b1`). **If any real database's `alembic_version` row
still points at either of those two IDs, `alembic upgrade head` fails
outright with an unknown-revision error before touching anything else.**
**Action required before cutover**: query the real production
`alembic_version` table and confirm it references a revision that still
exists in `versions/` — this is now an explicit check to add to the
production preflight (see below).

## Platform Core backend — 8 migrations (chain: `f006149cdf49 → 4a35a2c457fb → e76146991275 → 8e2a4ae9d31e → 76e4bdbdea17 → 6e61dba98356 → b1c3d5e7f9a0 → c2d4e6f8a1b3`)

All 8 have working downgrades at the schema level.

**6 of 8 safe to run as a plain `alembic upgrade head`**: `f006149cdf49`
(initial schema), `e76146991275` (`security_epoch` NOT NULL, correct
add-default-then-drop-default pattern), `76e4bdbdea17` (new table +
nullable column), `6e61dba98356` (`is_discoverable` NOT NULL, same safe
pattern), `b1c3d5e7f9a0` (nullable add), `c2d4e6f8a1b3` (UNIQUE
constraint on `gifted_access.external_ref` — safe, column is brand new).

**2 need special production handling**:

| Revision | Issue | Recommendation |
|---|---|---|
| `4a35a2c457fb` | New FK from `payment_records` to new `subscriptions` table — brief lock while validated | Check `payment_records` size first |
| `8e2a4ae9d31e` | **See critical finding below** — also a moderate combined lock (9-column ALTER + default drops on `plans`, new FK on `subscriptions`) | Verify the finding below before running; low-traffic window regardless |

### Critical finding: `8e2a4ae9d31e` permanently drops `oauth_clients.webhook_signing_secret` in its forward path

This migration's `upgrade()` calls `batch_op.drop_column('webhook_signing_secret')`
on the existing `oauth_clients` table, replacing it with a new
`webhook_signing_secret_encrypted` column — **with no data migration from
the old column to the new one**. The migration's own comment states this
is intentional because "no real webhook secret exists in any
pre-production deployment of this schema yet." **This assumption must be
explicitly re-verified against the real production database before this
migration ever runs there**: if any `oauth_clients` row has a non-null
`webhook_signing_secret` by the time this migration is applied, that
secret is **destroyed irrecoverably** — `downgrade()` re-adds the
plaintext column empty and drops the encrypted one, so the value is lost
in both directions once this has run once.

**Disposition**: this is a **pre-existing migration**, already merged and
already the current production-bound schema (this is not new code written
by this mission, and rewriting a merged historical migration is not a
safe or appropriate fix — Alembic revisions are immutable once any
environment may have run them). The correct mitigation is procedural, not
a code change: **add an explicit pre-migration check** (a plain read-only
`SELECT count(*) FROM oauth_clients WHERE webhook_signing_secret IS NOT
NULL;`) to the production preflight before `alembic upgrade head` is ever
run against the real database, and treat a non-zero result as a hard stop
requiring a manual backfill into `webhook_signing_secret_encrypted` first.
**Added to `production-preflight-inspection.sh`'s scope as a documented
manual step here** rather than silently assumed safe — see the addendum
below.

**No `nullable=False` without a `server_default` found anywhere in
Platform Core's chain either** — every NOT NULL addition to an existing
table (`security_epoch`, `status`/`is_public`/`sort_order`/`upgrade_rank`/
`gifted_eligible`/`trial_eligible`/`updated_at` on `plans`,
`is_discoverable`) uses the correct pattern.

## Addendum: two new pre-cutover checks this finding requires

1. **Before running Loady's migrations against production**: confirm
   `alembic_version` does not reference `5689146ea1c8` or `e600701e18eb`.
   ```sql
   SELECT version_num FROM alembic_version;
   -- must NOT be '5689146ea1c8' or 'e600701e18eb'
   ```
2. **Before running Platform Core's migrations against production, if
   `oauth_clients` already exists and could be populated** (i.e. if this
   revision has not already been applied in a prior deployment):
   ```sql
   SELECT count(*) FROM oauth_clients WHERE webhook_signing_secret IS NOT NULL;
   -- must be 0, or a manual backfill into webhook_signing_secret_encrypted
   -- must happen first
   ```

Both are read-only, safe to run at any time, and are added here as
explicit manual pre-migration checks rather than as new automated script
logic — building automated detection for a migration that (per its own
comment) is not expected to encounter this condition in practice would be
speculative; a documented manual check that an operator runs once, right
before the one time this migration is ever applied to a real database, is
proportionate to the actual risk.

## What this review does not do

It does not rewrite, patch, or add a data-migration step to
`8e2a4ae9d31e` itself — that revision may already be applied in staging or
elsewhere, and Alembic revisions are not meant to be edited after the
fact. The mitigation is a pre-flight check at the point this migration
would actually run against a database that might contain real data,
documented here and in the operator command index (Phase 52).
