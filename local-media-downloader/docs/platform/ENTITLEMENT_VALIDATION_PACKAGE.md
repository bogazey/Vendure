# Entitlement Validation Package (Mission 15, Phase 34 support / ENTITLEMENT TEST step)

## What's already proven

| Property | Tier | Evidence |
|---|---|---|
| V1 single-row entitlement resolution | UNIT TEST VERIFIED | `platform-core/backend/tests/test_entitlements.py` |
| V2 capability engine merge (bundles, promotions) | UNIT TEST VERIFIED | `test_capability_engine.py`, `test_capabilities_me.py` |
| Loady's hybrid fallback (`/entitlements/me` → `/capabilities/me`) never weakens fail-closed | UNIT TEST VERIFIED | `backend/tests/test_platform_capabilities_fallback.py` — "never calls `/capabilities/me` when already entitled," "network failure never raises, falls back to the legacy answer" |
| Lapsed-subscription re-grant reuses the same row, not a duplicate | UNIT TEST VERIFIED | `test_regranting_after_expiry_reactivates_the_same_row_not_a_duplicate` — re-confirmed present, `IDENTITY_MIGRATION_SAFETY_REAUDIT.md` |
| Gifted/internal entitlements survive a Paddle revoke of the same product | UNIT TEST VERIFIED | 19 tests, Mission 12 |
| Fail-closed cache behavior under Platform Core outage | LOCAL LIVE-STACK VERIFIED | `ENTITLEMENT_AVAILABILITY.md`, Mission 5 rehearsal |

## Real production check (the ENTITLEMENT TEST runbook step)

For one account of each tier available as a safe test account:

1. Compare plan/credit display before and immediately after migration —
   must be byte-for-byte identical (migration must not change a plan
   value, only where its source of truth lives).
2. For a gifted account specifically: confirm the gift is still visible
   and functioning (this is the one category `IDENTITY_MIGRATION_SAFETY_REAUDIT.md`'s
   known gap concerns — re-running commit after a gift grant is the risk,
   not the first commit itself).
3. Cross-check against Grand Admin's own view of the same account (feeds
   into the ADMIN TEST step).

## Rollback-triggering outcomes (restated from `ROLLBACK_TRIGGERS_AND_POINT_OF_NO_RETURN.md`, not new)

- Any entitlement escalation (more permissive than before, without an
  explicit deliberate grant).
- Any paid or gifted user losing entitlement they held pre-migration.

Both are explicit, unconditional rollback triggers — not judgment calls.
