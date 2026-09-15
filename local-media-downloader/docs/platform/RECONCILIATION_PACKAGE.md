# Reconciliation Package (Mission 15, Phase 31)

Consolidates `scripts/platform/verify-migration.sh` (read in full — 89
lines) into the exact pre/post invariant list Phase 31 requires. **Never
exposes PII beyond what the migration report itself already prints**
(Phase 24) — every check below is a count or a set-difference, never a
row dump.

## Pre-migration manifest (captured before MIGRATION COMMIT)

- Total Loady user count.
- Count of users already linked (`global_user_id IS NOT NULL`) — should
  be 0 on a true first run, or a stable known number if this is a
  resumed/retried migration.
- Plan/source distribution: count of users per plan (`free`/`pro`/`creator`)
  and per entitlement source (Paddle-paid/gifted/free).
- Disabled-user count, verified-email count.

## Post-migration invariants (`verify-migration.sh`'s actual checks, confirmed by reading the script)

| Invariant | Check | Failure meaning |
|---|---|---|
| Linked-count consistency | Loady's linked-user count equals the count of distinct `global_user_id` values referenced | A user got double-linked, or a link is orphaned — investigate before trusting any other number |
| Platform Core user count sane | `platform_users` count reported | Cross-checked against Loady's linked count — should match exactly (one Platform Core user per linked Loady user, by construction) |
| Entitlement count sane | `platform_entitlements` count reported | Should be consistent with the plan distribution captured pre-migration |
| **Hard invariant: zero payment records** | `payment_records` count **must be exactly 0** | Identity migration never touches billing — any non-zero count here means something wrote billing data during an identity-only migration, which should be structurally impossible; **an unconditional rollback trigger**, not a soft warning |
| Orphan check | Set difference (`comm -23`) between Loady's `global_user_id` set and Platform Core's user-id set | Any entry present in Loady's set but absent from Platform Core's means a link exists on one side without its corresponding record on the other — a rollback trigger |

## Post-migration invariants this document adds (beyond what the script currently checks)

- **Plan/source distribution unchanged**: the pre-migration distribution
  captured above must match the post-migration distribution exactly (a
  migrated user's plan should never change as a side effect of migration
  itself — only entitlement *source of truth* moves, not the plan value).
  Any difference here is the concrete, checkable form of the "entitlement
  escalation"/"paid-user entitlement loss" rollback triggers in
  `ROLLBACK_TRIGGERS_AND_POINT_OF_NO_RETURN.md`.
- **History/usage row counts unchanged**: Loady's own download-history and
  usage-tracking row counts, taken before and after, must be identical —
  the migration touches only `global_user_id` and creates Platform-Core-side
  rows; it must never insert, delete, or modify a Loady history/usage row.
  A difference here is the concrete form of the "history/usage ownership
  mismatch" trigger.
- **Migration-links vs. commit-report agreement**: the `created`+`linked`
  counts from the MIGRATION COMMIT step's own printed report must equal
  the post-migration linked-user count captured here — two independently
  computed numbers that must agree, a stronger check than either alone.
- **Conflicts/failures**: the commit report's own `conflicted`/`failed`
  counts, cross-referenced against this reconciliation pass — any
  conflict/failure not already understood from the MIGRATION DRY RUN step
  is, again, an unconditional rollback trigger.

## Any unexplained mismatch → rollback

Per Phase 31's explicit instruction: this is not softened into "investigate
first" for any invariant above marked hard — `verify-migration.sh` already
enforces this by printing exactly `RECONCILIATION: PASS` or `FAIL` and
exiting accordingly, and `FINAL_PRODUCTION_CUTOVER_RUNBOOK.md`'s
RECONCILIATION step already treats `FAIL` as a stop condition feeding
directly into `ROLLBACK_TRIGGERS_AND_POINT_OF_NO_RETURN.md`.
