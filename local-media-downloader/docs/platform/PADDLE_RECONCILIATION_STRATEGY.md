# Paddle Reconciliation Strategy

The algorithm behind `app/services/loady_paddle_reconciliation_service.py`
(Platform Core), the CLI at
`app/scripts/loady_paddle_reconciliation_dry_run.py`, and every synthetic
case in `tests/test_loady_paddle_reconciliation.py`. See
`BILLING_OWNERSHIP_TRANSITION.md` for the ownership decisions this
implements.

## 1. The core idea: reconciliation is event replay, not a special code path

Rather than writing bespoke "import Loady's subscription" logic, each
paid (`provider="paddle"`) Loady subscription's **current local
snapshot** is converted into one webhook-shaped "bootstrap" event
(`subscription.created`, timestamped at that row's own `updated_at`) and
fed through `webhook_service.receive_webhook` — the exact same function a
real live Paddle webhook hits. Idempotency (`BillingWebhookEvent`'s
`UNIQUE(provider, provider_event_id)`), out-of-order protection
(`Subscription.last_event_occurred_at`), and refund/chargeback handling
are therefore **inherited**, not reimplemented. Any additional synthetic
events — simulating what real Paddle traffic during the cutover window
would have delivered — are replayed the same way, immediately after
bootstrapping, in delivery order.

This means the reconciliation "algorithm" is genuinely just:

1. For every Loady user with a linked `global_user_id` (Mission 3's
   identity migration is a hard prerequisite):
   a. For every gifted subscription: report it (`gifted_preserved`),
      touch nothing.
   b. For every paid subscription: build and replay its bootstrap event.
2. Replay any additional synthetic events, in order.
3. Commit (or roll back, for a dry run) once, at the end.

## 2. Classification (what the report shows)

| Category | Meaning |
|---|---|
| `created` | No Platform Core `Subscription` existed for this `provider_subscription_ref` before this run. |
| `updated` | One existed, and its status or period changed. |
| `unchanged` | One existed and nothing changed (the idempotent re-run case). |
| `reconciled_with_change` | An **additional** event changed an already-bootstrapped subscription's state — shows the exact before/after values. |
| `gifted_preserved` | A gifted Loady subscription, deliberately untouched; flags `also_has_paid_subscription` when relevant. |
| `orphaned_customer` | A Paddle customer reference with no subscription reference — nothing to reconcile. |
| `orphaned_subscription` | A real paid subscription for a Loady user with no `global_user_id` yet — run the identity migration first. |
| `duplicate_local_reference` | Two Loady rows share the same `provider_subscription_id` — refused, never guessed. |
| `failed` | An unexpected error (e.g. an adjustment referencing an unknown transaction). |

## 3. Live proof (this mission's own run, not simulated)

A real Loady-schema SQLite database was built through Loady's own real
Alembic migrations and real `auth_service.signup()`, seeded with:

- `pro-monthly-mission8@example.com` — active Pro, 30-day period, linked
  to a real Platform Core `User` (simulating Mission 3 having already run).
- `creator-annual-mission8@example.com` — active Creator, 365-day period.
- `canceled-valid-mission8@example.com` — canceled, `current_period_end`
  10 days in the future.
- `unmigrated-paid-mission8@example.com` — a real paid subscription, but
  **no** `global_user_id` (identity migration never run for this user).

**Dry run** (`python -m app.scripts.loady_paddle_reconciliation_dry_run
--loady-database-url ...`):

```
created=3 updated=0 unchanged=0 reconciled_with_change=0 gifted_preserved=0
orphaned_customer=0 orphaned_subscription=1 duplicate_local_reference=0 failed=0
```

Confirmed zero writes by querying the Platform Core SQLite file directly
afterward (`subscriptions: 0`, `entitlements: 0`).

**Commit run**: identical summary, `=== COMMITTED ===`. Direct database
query afterward: 3 `subscriptions` rows, 2 `entitlements` rows (the two
`active` ones — `pro` and `creator`, both `source=paddle`), **0**
`payment_records` (a bootstrap event alone never fabricates a payment —
there is no historical transaction to backfill from, see
`PADDLE_LIVE_INPUTS_REQUIRED.md`). The canceled-but-still-valid
subscription correctly produced **no** legacy `Entitlement` row (that
cache is deliberately only synced for the "grant" direction on first
sight — see below) but IS correctly entitled via the modern
`capability_service.resolve_effective_entitlements`, which reads the
`Subscription` row directly and treats "canceled, period not yet over" as
entitled — confirmed by calling it directly against the live database.

**Second commit run (idempotency)**: `created=0 ... unchanged=3
orphaned_subscription=1`. Direct query: still exactly 3 `subscriptions`
rows, still 2 `entitlements` rows, still 0 `payment_records` — re-running
reconciliation duplicated nothing.

**Mid-cutover real event** (`--additional-events-file`): a
`transaction.completed` event for the active Pro subscription, replayed
on top of the already-bootstrapped state, produced exactly one
`PaymentRecord` (`amount_cents=1900, currency=USD, status=completed`) —
proving the "renewed/paid during cutover" scenario reconciles correctly
without needing any special-casing beyond "replay it after bootstrapping."

## 4. A note on the legacy `Entitlement` cache vs. the modern resolver

`subscription_service._sync_legacy_entitlement` only **grants** the
legacy V1 `Entitlement` row for `trialing`/`active`/`past_due` states; for
`canceled`/`expired`/`paused` it only ever **revokes** (once the period
has truly ended) — it does not proactively grant one just because a
canceled-but-still-valid subscription was reconciled. This is documented,
intentional behavior in the existing code (not something this mission
introduced or needed to fix): the *authoritative* answer to "is this user
entitled right now" is `capability_service.resolve_effective_entitlements`,
which reads the `Subscription` row directly at query time and correctly
implements "access continues through the paid period even after
cancellation" independent of the legacy cache's own timing. Both are
exercised and asserted correctly in this mission's tests.

## 5. Full synthetic case coverage

All 21 required cases plus data-anomaly and idempotency proofs, in
`tests/test_loady_paddle_reconciliation.py` (25 tests) and
`tests/test_billing_out_of_order_and_refunds.py` (16 tests, at the
`webhook_service` layer directly - includes Mission 9's `pending_approval`/
`approved`/`rejected` adjustment-lifecycle cases and Mission 10's proof
that a chargeback ignores that vocabulary and still revokes immediately):

| Case | Test |
|---|---|
| Active Pro monthly / annual | `test_active_pro_monthly`, `test_active_pro_annual` |
| Active Creator monthly / annual | `test_active_creator_monthly`, `test_active_creator_annual` |
| Cancellation at period end | `test_cancellation_at_period_end_keeps_entitlement_active` |
| Already canceled, valid until period end | `test_already_canceled_but_entitlement_valid_until_period_end` |
| Past due | `test_past_due` |
| Payment failed (transition) | `test_payment_failed_transitions_an_active_subscription_to_past_due` |
| Subscription upgraded | `test_subscription_upgraded_mid_cycle` |
| Subscription downgraded | `test_subscription_downgraded_mid_cycle` |
| Plan changed mid-cycle (cadence switch) | `test_plan_changed_mid_cycle_billing_period_switch` |
| Duplicate webhook delivery | `test_duplicate_webhook_delivery` (+ `test_duplicate_local_references`) |
| Delayed webhook | `test_delayed_webhook_still_applies_when_genuinely_newer` |
| Out-of-order webhook | `test_out_of_order_webhook_is_ignored` |
| Refund (full) | `test_full_refund` |
| Partial refund | `test_partial_refund` |
| Chargeback/dispute | `test_chargeback_dispute` |
| User with both paid and gifted | `test_user_with_both_paid_and_gifted_entitlement` |
| Orphaned Paddle customer reference | `test_orphaned_paddle_customer_reference` |
| Orphaned subscription reference | `test_orphaned_subscription_reference_without_identity_migration` |
| Local record disagrees with simulated Paddle state | `test_local_record_disagrees_with_simulated_paddle_state` |
| Duplicate local references | `test_duplicate_local_references` |
| Dry-run zero writes | `test_dry_run_performs_zero_writes` |
| Idempotent re-run | `test_running_reconciliation_twice_is_idempotent` |
| No fabricated payment record | `test_no_payment_record_is_fabricated_for_bootstrap_only_reconciliation` |

## 6. A real transactional pitfall found and fixed while building this

An early version of this engine wrapped each webhook replay in a SQLite
`SAVEPOINT` (`session.begin_nested()`) to protect earlier, still-
uncommitted work in the same reconciliation run from being wiped out by
`webhook_service`'s own internal `session.rollback()` on a duplicate-event
race. **This silently broke dry-run's "zero writes" guarantee**: SQLite
via `pysqlite`/SQLAlchemy's default configuration does not reliably honor
SAVEPOINT rollback boundaries without an additional driver-level
workaround this codebase does not have configured, and rows committed
inside a `begin_nested()` block were found, empirically, to survive an
outer `session.rollback()` (reproduced directly, outside this codebase,
before concluding this). **Fixed** by removing the SAVEPOINT approach
entirely: the reconciliation engine now checks `BillingWebhookEvent` for
an already-journaled event **before** ever calling `receive_webhook`
again for it, so the internal duplicate-race rollback path is never
exercised within a single reconciliation run at all. This is simpler,
avoids the driver pitfall entirely, and is verified by
`test_dry_run_performs_zero_writes` (which failed under the SAVEPOINT
approach and passes under this one).
