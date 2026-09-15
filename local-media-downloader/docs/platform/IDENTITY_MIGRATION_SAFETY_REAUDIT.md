# Identity Migration Safety Re-Audit (Mission 15, Phase 30)

Re-confirms every item Phase 30 explicitly lists, against current source
(`loady_migration_service.py`), not against a prior mission's description
of it.

| Property | Status | Evidence |
|---|---|---|
| Immutable `global_user_id` | **CODE VERIFIED** | Assigned once per link, never reassigned on subsequent runs for an already-linked user (`loady_migration_service.py`'s `existing.global_user_id is not None` branch skips re-assignment) |
| Email collision handling | **UNIT TEST VERIFIED** | Matches by `global_user_id` first, then email; an email match with an existing different link is a `conflicted` row, never silently overwritten |
| Argon2 compatibility | **UNIT TEST VERIFIED** (Mission 3, task #96) | Real hash re-verified successfully against Platform Core with zero code changes to the password itself |
| Disabled/unverified/admin/paid/gifted users | **UNIT TEST VERIFIED** | 12 synthetic Loady fixtures (Mission 3, task #98) explicitly cover each category |
| History/usage ownership | **CODE VERIFIED** | `global_user_id` is a side column on `users` only — the migration service's queries never touch history/usage tables, confirmed by reading its full source (no import of/reference to those tables) |
| Idempotency | **UNIT TEST VERIFIED**, with one confirmed exception below | Re-running for an unlinked user is safe (creates/links once); re-running for an already-linked user is safe for identity linkage itself |
| Lapsed-subscription entitlement behavior | **UNIT TEST VERIFIED** | `entitlement_service.grant_or_change`'s `_get_latest_entitlement` lookup deduplicates by the latest row rather than always inserting a new one — `test_regranting_after_expiry_reactivates_the_same_row_not_a_duplicate` (confirmed present, read directly this mission) |

## The recently fixed lapsed-subscription idempotency regression — confirmed still present and covered

The fix (`_get_latest_entitlement`, `entitlement_service.py`) and its
regression test
(`test_regranting_after_expiry_reactivates_the_same_row_not_a_duplicate`,
`tests/test_entitlements.py`) were both read directly this mission and
confirmed present, unmodified, and exercised by the full test suite
(Phase 50 re-run). No regression was introduced by anything else this
mission touched — nothing in this mission's changes (nginx template,
backup script, preflight scripts, `.env.production.example`) touches
`entitlement_service.py` or its tests at all.

## The one confirmed, unfixed exception to idempotency — restated, not re-litigated

**Re-running `run_migration --commit` for an already-linked user
re-derives that user's entitlement from Loady's *current* plan state**,
which can silently downgrade a Grand-Admin-issued gift back to Loady's
plan (e.g. `free`) if the migration is re-run after the gift was granted.
This was identified in a prior mission's audit and explicitly left
unfixed at the time, out of scope. Re-confirmed present in the current
`loady_migration_service.py` by this mission's own reading. **This is
exactly the mechanism `ROLLBACK_TRIGGERS_AND_POINT_OF_NO_RETURN.md`'s
"post-migration Grand Admin account changes" point-of-no-return
consideration is built around** — the practical guidance is: **never
re-run the commit migration with `--commit` after any Grand Admin gift
action for already-migrated users** without first checking for existing
`GiftedAccess` rows for that user. This mission does not fix this in code
(a genuine, but narrow and process-mitigable, gap — not attempted to fix
by the prior mission either, and fixing it now would require redesigning
the migration's entitlement-resolution step, a change beyond this
mission's no-feature-creep scope for something with a documented,
sufficient process mitigation).

## Disposition

No code change was needed or made to `loady_migration_service.py` or
`entitlement_service.py` by this mission — every property Phase 30 asks
to re-audit was already correctly built and tested; the one known gap is
carried forward as a documented operational constraint, not silently
dropped from the record.
