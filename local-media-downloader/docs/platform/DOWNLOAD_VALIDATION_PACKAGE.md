# Download Validation Package (Mission 15, Phase 34 / DOWNLOAD TEST step)

## What's already proven

| Property | Tier | Evidence |
|---|---|---|
| Free/paid/gifted authorization at the download gate | UNIT TEST VERIFIED | `backend/tests/test_platform_entitlement_gate.py` |
| Platform entitlement retrieval wired into the gate | UNIT TEST VERIFIED | Same file; Mission 4's phase 9 wiring |
| Cache behavior under Platform Core outage (fail-closed to Free-tier limits, not an error) | LOCAL LIVE-STACK VERIFIED | `ENTITLEMENT_AVAILABILITY.md` |
| Secure file retrieval / per-user storage isolation | UNIT TEST VERIFIED | Traversal/symlink-escape/cross-user isolation tests (earlier mission, tasks #30) |

## Real production check (the DOWNLOAD TEST runbook step)

One small, low-load test download per available test-account tier:

1. Entitled tier → succeeds.
2. A tier that should be blocked for a given content type/quality →
   correctly blocked with the expected error, not a 500.
3. Confirm the download actually originates from the correct, isolated
   per-user storage path (no cross-account leakage).

**No media-abuse/high-load testing during cutover** — per Phase 34's
explicit instruction, this is a functional smoke test, not a load test;
running many downloads to "be thorough" during a live cutover window
risks contending with the exact resource budget
(`PRODUCTION_RESOURCE_BUDGET.md`) this whole package was built to respect.

## Rollback-triggering outcome

Systemic download authorization failure (more than an isolated account) —
restated from `ROLLBACK_TRIGGERS_AND_POINT_OF_NO_RETURN.md`, not new here.
