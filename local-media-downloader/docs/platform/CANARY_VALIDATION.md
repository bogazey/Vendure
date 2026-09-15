# Canary Validation (Mission 15, Phase 32)

## What this architecture actually supports

**A synthetic/internal Platform Core account, created ahead of the real
migration and used to exercise the full central-login → Loady-callback →
entitlement-lookup → Grand-Admin-visibility path, without involving any
real customer.** This is architecturally supported today, without new
code: `register_loady_client.py`'s pattern (a system-generated account
with `secrets.token_urlsafe(32)` credentials, never logged) is the same
mechanism already used for the migration actor and bootstrap admin
accounts (`PRODUCTION_SECRET_INVENTORY.md`). A staff/test account with a
real, disposable email address, created through Platform Core's own signup
and manually linked to a **non-production** Loady test account (or a
staging Loady instance, per `LOADY_PRODUCTION_MIGRATION_PLAN.md`'s Stage 1
"internal/staff accounts only" step, which already establishes exactly
this pattern for the wider migration rollout) is the safest available
canary.

**This mission does not create this account now** — doing so would touch
infrastructure this mission does not run against (a real or realistic
staging deployment), and Phase 32 asks this mission to document what's
*possible*, not to perform it.

## What is explicitly NOT supported, and not invented

- **No unsupported real-user canary migration.** There is no mechanism to
  migrate "just one real customer" as a trial separate from the full
  commit — `loady_migration_service.run_migration` operates over the
  entire `users` table in one pass (per-row, but as one transaction/report,
  not a selectable single-user dry-run-then-commit-for-real-users
  mechanism). Building a single-real-user-canary mode would be new
  application code for a need Stage 1's staff-account approach (Mission
  3's own design) already satisfies — exactly the kind of speculative
  addition the No Feature Creep rule forbids.
- **No production-data canary.** The canary account must be a real,
  disposable, non-customer account — never a real customer's account
  singled out for early exposure to a still-unproven flow.

## Recommended canary procedure (for the future, separately authorized cutover)

1. Before the identity-migration maintenance window, create one staff
   account in Platform Core (real email the operator controls, e.g. an
   internal alias).
2. Log into Loady's central-login flow with it, end to end, against the
   real production Platform Core deployment (already verified healthy per
   `PRODUCTION_DEPLOYMENT_SEQUENCING.md` Phase 22) — this exercises the
   exact same code path a real migrated user will use, without depending
   on the migration having run at all (a fresh signup doesn't need
   migration to test SSO).
3. Confirm the account is visible and correctly scoped in Grand Admin.
4. This is a pre-migration smoke test, not a substitute for the SSO TEST
   step in `FINAL_PRODUCTION_CUTOVER_RUNBOOK.md` (which specifically tests
   a *migrated* account post-commit) — both are useful, at different
   times, for different purposes.

## Relationship to Free/paid/gifted test coverage (Phase 33's concern, referenced here for completeness)

A single canary account is a smoke test for the *mechanism* (login flow
works at all), not a substitute for exercising Free/paid/gifted account
types specifically — that is `ENTITLEMENT_VALIDATION_PACKAGE.md`'s job,
performed post-migration against real (if minimal) test accounts of each
kind, where such accounts safely exist.
