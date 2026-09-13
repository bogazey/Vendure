# Loady Migration Plan (planning only - NOT executed)

**This mission did not touch Loady's production database, code, or
behavior in any way.** Everything below is a plan for a future,
separate, deliberate migration effort - reviewed and approved before any
part of it runs against real data.

## What was actually inspected to write this plan

`local-media-downloader/backend/app/services/security_service.py`,
`auth_service.py`, `app/database/commercial_models.py` (the `User`,
`RefreshToken`, `Subscription` tables), and
`app/services/gift_subscription_service.py` were read in full (see
`ARCHITECTURE.md` §1's audit table for what was found). The findings below
are based on that code, not assumptions.

## 1. Password hashes: CAN migrate without forcing resets

Loady hashes passwords with **Argon2id via `argon2-cffi`'s
`PasswordHasher`** (`security_service.hash_password`). Platform Core's
`app/security/passwords.py` uses the **exact same library with the exact
same default parameters**. An Argon2id hash string
(`$argon2id$v=19$m=...,t=...,p=...$salt$hash`) is self-describing and
verifiable by any Argon2id implementation regardless of which app
generated it - `argon2.PasswordHasher().verify(loady_hash, password)`
would succeed against a Loady-issued hash exactly as it does against a
Platform-Core-issued one, with zero code changes needed.

**Migration approach**: copy `password_hash` verbatim into the new
`users.password_hash` column. The first login after migration works
immediately, no forced reset, no "please reset your password" email
needed. (If Platform Core's Argon2 parameters were ever tuned differently
in the future, `needs_rehash()` - already wired into `auth_service.login`
- would silently upgrade the hash on that user's next successful login,
exactly as Loady's own code already does for its own parameter changes.)

## 2. Email verification, refresh tokens, active sessions

- **Email verification status** (`User.email_verified`): copy directly -
  it's a plain boolean, no re-verification needed.
- **Refresh tokens / active sessions**: **do not migrate these rows.**
  A refresh token is bound to the issuing service's own JWT signing key
  and cookie domain; Loady's existing sessions were issued by Loady's own
  HS256 secret, not Platform Core's RS256 key, and are meaningless to
  Platform Core regardless. The plan is to let existing Loady sessions
  expire naturally (Loady's `refresh_token_ttl_days`, currently 30) while
  users are transparently required to sign in once during the migration
  window - a one-time re-login, not a password reset. This is standard
  practice for any identity-provider migration and avoids ever needing to
  reconstruct a session server-side.
- **Password reset / email verification tokens**: not migrated - any
  in-flight token becomes invalid the moment migration runs; this is
  acceptable (these tokens are single-use and short-lived by design, 1-48
  hours) and is far simpler than trying to re-point an email already sent
  with a Loady URL at a new Platform Core URL.

## 3. Paddle customer IDs and subscription IDs

Loady's `Subscription.provider_customer_id` /
`provider_subscription_id` are **Paddle's own identifiers** - they are not
migrated into Platform Core's identity tables at all; they stay exactly
where they are, inside Loady's own database, because **Loady keeps
managing its own Paddle billing relationship** (mission-brief section 33
asks to plan for this, not to move billing into Platform Core - see
`BILLING.md`'s "identity ≠ entitlement ≠ payment" boundary). What
migrates is a **derived fact**: "this global user currently holds an
active Loady Pro/Creator entitlement, source=paddle" - written as one
`Entitlement` row per currently-active Loady `Subscription`, with
`Entitlement.source = EntitlementSource.PADDLE` and
**no** Paddle id copied onto it (Platform Core has no column for one -
see `ENTITLEMENTS.md`; that information stays authoritative inside
Loady's own `Subscription` table, referenced by the *same* `global_user_id`
so the two systems agree on "who", not on "which Paddle row").

## 4. Free / Pro / Creator plans

Loady's plan slugs (`free`, `pro`, `creator`) become
`Plan(product_id="loady", slug="free"|"pro"|"creator")` rows in Platform
Core (via `entitlement_service.get_or_create_plan`, exactly the pattern
`app/scripts/seed_products.py` already establishes for the ten-product
registry). A Loady user with **no** `Subscription` row (Free, by Loady's
own convention - "Free has no row at all") gets **no** `Entitlement` row
either, for consistency with the same "absence means Free" convention
Loady itself already relies on (`COMMERCIAL_ARCHITECTURE.md` §3).

## 5. Gifted subscriptions

Every Loady `Subscription` with `provider="gifted"` becomes one
`Entitlement` row with `source=EntitlementSource.GIFTED`,
`granted_by` resolved from `Subscription.granted_by_admin_id` (mapped
through the same admin-account migration in step 6), and `reason` copied
from `Subscription.granted_reason`. **This must never reclassify a real
`provider="paddle"` row as gifted, and never the reverse** - the migration
script asserts `provider in {"paddle", "gifted"}` for every row it reads
and refuses to proceed (rather than guessing) if it ever finds anything
else, exactly mirroring the original gifted-subscriptions migration's own
"do not accidentally classify existing Paddle subscriptions as gifted"
rule.

## 6. Admin accounts

A Loady user with `role="admin"` gets a `RoleAssignment(role_slug=
"admin", scope="product:loady")` - **not** `scope="global"`. Loady's
notion of "admin" only ever meant "admin of Loady" - it must not silently
become a Grand Admin credential (mission-brief section 46: "no product can
grant itself global admin privileges"). Promoting a specific person to
Grand Admin `super_admin` afterward remains the same manual,
CLI-only, one-at-a-time action (`app/scripts/promote_super_admin.py`) it
already is - never automatic, never derived from a product-scoped role.

## 7. Existing download/history ownership

Loady's `history` table already stores its own `user_id`
(`COMMERCIAL_ARCHITECTURE.md` §4: "a `user_id` column was added to
`history`"). This is Loady's own operational data and **stays in Loady's
own database, referenced by the migrated `global_user_id`** - it is never
copied into Platform Core (mission-brief section 26: product operational
data remains product-owned). The only change Loady's own code would ever
need, post-migration, is reading `global_user_id` from a verified Platform
Core token instead of its own locally-issued one - a `deps.py` swap, not a
data migration.

## Zero-duplicate, idempotent migration script design (mission-brief section 34)

The actual script (not written in this mission - this is its design)
would be `platform-core/backend/app/scripts/migrate_loady_users.py`,
CLI-only, and would:

1. **Match by email, never create blind.** For each Loady `User` row,
   look up `Platform Core users WHERE email = loady_user.email`.
   - If found: this global account already exists (e.g. re-running after
     a partial failure, or the person already has a Platform Core account
     from another product) - do **not** create a duplicate. Only write
     the Loady-specific `ProductMembership`/`Entitlement`/`RoleAssignment`
     rows for that existing `global_user_id`, and skip re-writing anything
     already present (idempotent - see below).
   - If not found: create the `User` row with the copied `password_hash`
     and `email_verified`, generating a fresh `global_user_id`.
2. **Idempotent per Loady user**: before writing a `ProductMembership`,
   `Entitlement`, or `RoleAssignment`, check whether an equivalent row
   already exists (same `user_id`+`product_id` for membership, same
   `user_id`+`product_id`+active-status for entitlement) and update rather
   than insert if so - running the script twice against the same source
   data produces the same end state, not duplicates.
3. **Dry-run capable**: a `--dry-run` flag that performs every lookup and
   prints exactly what it *would* write (create vs. update vs. skip, per
   Loady user) without opening a write transaction - the operator reviews
   this output before the real run.
4. **Auditable**: every real (non-dry-run) write is wrapped in a single
   `audit_service.record()` call per migrated user
   (`action="loady_migration_import"`, `before_state=None`,
   `after_state={"loady_user_id": ..., "global_user_id": ...,
   "entitlements_created": [...]}`), so the migration itself leaves a
   permanent, queryable trail in the same audit log Grand Admin already
   shows.
5. **Resumable**: processes Loady users in a stable order (created_at,
   id) and accepts a `--after-id` flag to resume from a specific Loady
   user id if a prior run was interrupted - combined with idempotency
   above, a resumed run never double-processes an already-migrated user
   even without the flag, but the flag makes a large migration's progress
   observable and restartable without re-scanning already-done rows.
6. **Never runs automatically.** Not on Platform Core startup, not on
   Loady startup, not behind any HTTP endpoint - a human runs it
   deliberately, once, reviewing the dry-run output first. This mirrors
   every other privileged CLI-only script in this codebase
   (`promote_super_admin.py`, `register_demo_clients.py`,
   Loady's own `promote_admin.py`).

## What remains explicitly undecided (by design - not this mission's call)

- **When** to run it (a maintenance window vs. a gradual dual-write
  period).
- Whether Loady's backend should, post-migration, verify Platform Core
  tokens directly or keep issuing its own session cookies for a
  transition period while trusting a Platform-Core-issued token as an
  alternative login path.
- Whether to eventually delete the migrated fields from Loady's own
  `User`/`Subscription` tables or leave them in place indefinitely as a
  fallback.

These are product/business decisions that belong to whoever approves the
actual migration, not something this architecture mission should
pre-decide.
