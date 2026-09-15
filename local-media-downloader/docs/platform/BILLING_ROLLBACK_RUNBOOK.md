# Billing Rollback Runbook

Every stage in `BILLING_CUTOVER_RUNBOOK.md` has an independent way back,
listed here from fastest/safest to most involved.

## 1. Instant kill switch: point Paddle's webhook back at Loady only

If Platform Core's billing engine misbehaves at any point after Stage 2
of the cutover runbook, remove Platform Core's webhook destination from
Paddle's dashboard (Sandbox or Live). Loady's own endpoint was never
removed until Stage 5, so this alone restores the pre-cutover state
completely — Loady's own `paddle_service.py` has been running unmodified
this entire time and immediately resumes being the only system Paddle
talks to. No code change, no deploy, no database repair.

If already past Stage 5 (Loady's own endpoint removed), first **re-add**
Loady's endpoint in Paddle's dashboard, then remove Platform Core's. Both
receiving events briefly is harmless (Loady's own idempotent
`BillingEvent` handling and Platform Core's `BillingWebhookEvent`
handling each separately no-op a webhook they've already seen).

## 2. Reconciliation is read-only on Loady — there is nothing to undo there

`loady_paddle_reconciliation_service.py` never writes to Loady's
database, ever — verified by design (SQLAlchemy Core reflection with a
read-only connection use pattern, no `UPDATE`/`INSERT` against any Loady
table anywhere in the module) and by this mission's own live run (Loady's
`commercial.db` file's own row count and content were unchanged before
and after every dry-run and commit-run). This means "rolling back a bad
reconciliation" only ever means undoing Platform Core's own state — Loady
itself is never at risk from this specific tool.

## 3. Undoing a bad commit-run on the Platform Core side

Since a `Subscription` row's `provider_subscription_ref` is the stable
key, undoing a specific reconciled subscription is a direct, scoped
operation:

```sql
DELETE FROM subscription_items WHERE subscription_id = (
  SELECT id FROM subscriptions WHERE provider = 'paddle' AND provider_subscription_ref = '<ref>'
);
DELETE FROM subscriptions WHERE provider = 'paddle' AND provider_subscription_ref = '<ref>';
```

The corresponding legacy `Entitlement` row is not itself deleted by this
— call `entitlement_service.revoke(session, actor, user, "loady", reason="reconciliation rollback")`
(or leave it; a stale-but-inactive Entitlement row is harmless, since
`capability_service.resolve_effective_entitlements` is what every real
access decision actually uses, and it reads the `Subscription` row
directly — once that row is gone, this source stops contributing).

For a bulk rollback of an entire bad reconciliation run, filter by the
audit trail: every subscription this engine ever creates or changes is
recorded via `AuditAction.SUBSCRIPTION_CREATED`/`SUBSCRIPTION_CHANGED`
with `after_state` showing exactly what was written — query
`audit_logs` for the relevant time window to get the exact list of
affected `provider_subscription_ref` values before deleting anything.

## 4. Undoing a bad refund/chargeback application

A refund or chargeback wrongly applied (e.g. a malformed synthetic event,
or — in a real cutover — a shape-mapping bug in `paddle_provider.py`
misclassifying an event) can be reversed directly:

```sql
UPDATE payment_records SET status = 'completed', refunded_amount_cents = NULL
WHERE provider = 'paddle' AND provider_reference = '<transaction-id>';
```

If the refund/chargeback incorrectly revoked an entitlement, re-grant it
directly: `entitlement_service.grant_or_change(session, actor, user,
"loady", "<plan-slug>", EntitlementSource.PADDLE, <period_end>, reason="refund rollback")`.

## 5. Database migration rollback

`b1c3d5e7f9a0` (`Subscription.last_event_occurred_at`) is purely additive
and has a real, tested `downgrade()`:

```bash
python -m alembic downgrade 6e61dba98356
```

This has no effect on any other column and does not need to be reversed
merely to disable the out-of-order guard's *effect* — a `NULL` value in
that column already means "no guard yet" (the very first event for any
subscription), so leaving the column in place is always safe even if this
mission's other changes are rolled back.

## 5a. Rolling back `c2d4e6f8a1b3` (`GiftedAccess.external_ref`, Mission 12)

Also purely additive, also has a real, tested `downgrade()`:

```bash
python -m alembic downgrade b1c3d5e7f9a0
```

Drops the column and its unique constraint only - every `GiftedAccess` row
created before this migration (every admin-granted gift) is completely
unaffected, since `external_ref` was `NULL` for all of them already. Rows
materialized via `gift_service.materialize_external_gift` (Loady-native
gifts) lose only the idempotency key that prevented duplicate re-creation
on a future migration re-run - the gift GRANT itself (`plan_id`, `status`,
`expires_at`, etc.) is untouched, so a downgrade never revokes anyone's
actual access. Re-running the migration/backfill after a later re-upgrade
would re-materialize the same gifts fresh (by then-current Loady data),
not resume from the dropped column.

## 5b. Rolling back the `refunded`/`disputed` Subscription statuses (Mission 12)

No schema change to revert (`Subscription.status` was always free-text).
If `subscription_service.suspend_for_billing_event`'s CALL SITE in
`webhook_service._apply_adjustment_event` is reverted (see §6 below), any
`Subscription` row already sitting at `status="refunded"`/`"disputed"`
simply stops being written by future events but is not itself corrupted -
`capability_service._subscription_contributes` already treats any
status outside its recognized active/canceled set as non-contributing, so
a stray `refunded` row after a code revert still correctly excludes
itself from `resolve_effective_entitlements`, never silently reactivating.

## 6. Rolling back the webhook_service.py code changes themselves

If the fixes in §5 of `BILLING_OWNERSHIP_TRANSITION.md` (out-of-order
guard, refund/chargeback handling, period/plan-change threading) need to
be reverted entirely — e.g. a real Sandbox test reveals one of them
misbehaves against real Paddle event shapes — reverting the commits on
`billing-ownership-transition-v1` is safe and low-risk specifically
because:

- The out-of-order guard's absence (pre-fix behavior) is the ORIGINAL,
  already-running behavior — reverting it returns to exactly what Mission
  6 shipped, not a new state.
- Refund/chargeback handling is purely additive (`adjustment.*` event
  types) — removing it means those events fall back to being stored (for
  audit) and otherwise ignored, exactly Mission 6's original behavior for
  any unhandled event type.
- Period/plan-change threading changes `_apply_subscription_event`'s
  internal logic but not its external signature or the `Subscription`
  schema — reverting it returns to "period/plan never actually update,"
  which is a regression in capability but not a data-corrupting one.

## 7. What never needs rolling back

- **Loady's own Paddle integration** — untouched this entire mission,
  always available as the fallback described in §1. This is now decided
  policy, not just this mission's default: Decision #9
  (`BILLING_OWNERSHIP_TRANSITION.md` §6a) confirms Loady's `Subscription`/
  `BillingEvent` tables are never deleted during cutover, retained
  read-only for exactly this rollback path once Platform Core is
  authoritative.
- **Any live Paddle subscription, customer, or charge** — this mission
  made zero live Paddle API calls; there is nothing Paddle-side to undo.
- **Gifted subscriptions** — the reconciliation engine never writes to a
  gifted Loady subscription or creates a competing entitlement for one;
  there is nothing to roll back there by construction.

## 8. Order of operations for a real incident

1. Kill switch (§1) if Paddle is actively sending events somewhere
   causing harm — immediate, zero-risk.
2. Investigate using `audit_logs` (every write this engine makes is
   recorded) plus `billing_webhook_events.failure_reason` for anything
   that failed outright.
3. Scoped rollback (§3/§4) only for the specific subscriptions/payments
   actually found to be wrong — never a bulk wipe unless the whole run is
   confirmed bad.
4. Code revert (§6) only if the bug is in the reconciliation/webhook logic
   itself, not the data it processed.
