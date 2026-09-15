# Grand Admin Validation Package (Mission 15, Phase 36 / ADMIN TEST step)

## What's already proven

| Property | Tier | Evidence |
|---|---|---|
| Admin auth, RBAC scoping | UNIT TEST VERIFIED | `platform-core/backend/tests/test_admin.py` |
| Admin rate limiting | UNIT TEST VERIFIED | `test_admin_rate_limit.py` |
| Product-scoped admin cannot become global admin | UNIT TEST VERIFIED | `test_admin.py`'s scoping invariant, cited in `POST_MIGRATION_MONITORING.md`'s 24-hour window |
| Gift grant/revoke via synthetic identity | UNIT TEST VERIFIED | Mission 12's 19 entitlement-source-preservation tests |
| Audit log correctness | UNIT TEST VERIFIED + LOCAL LIVE-STACK VERIFIED | `audit_service.record` call sites confirmed throughout; Mission 5 rehearsal |

## The ADMIN TEST runbook step, specifically

1. Log into Grand Admin with a real admin account against real production
   Platform Core (first real-infrastructure exercise of this login path —
   see `PRODUCTION_DEPLOYMENT_SEQUENCING.md` step 6, ideally already done
   once during PLATFORM CORE VERIFICATION).
2. Look up the canary/test account(s) used in SSO TEST/ENTITLEMENT TEST —
   confirm product membership and entitlement view match what those steps
   already showed.
3. **Never test destructive admin operations (revoke, disable, delete)
   against a real customer account during cutover** — per Phase 36's
   explicit instruction. Use only the designated synthetic/staff test
   account(s) for any grant/revoke exercise.
4. Confirm the audit log records the lookup/action correctly attributed to
   the real admin account performing it.

## Rollback-triggering outcome

Grand Admin unreachable, or showing systemically incorrect
product/entitlement state (not an isolated display glitch) — restated
from `ROLLBACK_TRIGGERS_AND_POINT_OF_NO_RETURN.md`.

## Interaction with the point-of-no-return policy

Per `ROLLBACK_TRIGGERS_AND_POINT_OF_NO_RETURN.md`'s observation-period
policy: avoid exercising real gift/entitlement grant-or-revoke actions on
**migrated real accounts** during this test and the initial observation
window — the synthetic canary account exists precisely so this validation
doesn't need to touch a real one.
