# Billing Cutover Runbook

**Nothing in this document has been executed against production.** This
is the plan for a future, separate, deliberately-approved effort, built
on the mechanism this mission actually built and proved locally
(`PADDLE_RECONCILIATION_STRATEGY.md`). See `LOADY_PRODUCTION_MIGRATION_PLAN.md`
(Mission 3) for the identity-migration prerequisite this entirely depends
on, and `PADDLE_LIVE_INPUTS_REQUIRED.md` for exactly what a human needs to
provide before Stage 2 below can start.

## Prerequisites

1. **Mission 3's identity migration must already be complete** for every
   user this cutover covers — `orphaned_subscription` in the
   reconciliation report is not a bug to route around, it is the correct,
   safe refusal to reconcile a subscription for a user Platform Core
   cannot yet identify.
2. **Platform Core running in a real, monitored environment** — this
   mission's own local dry runs used SQLite and a throwaway process; a
   real cutover needs Postgres, a real deployed `webhook_service`
   endpoint, and real monitoring on it (see `PRODUCTION_TOPOLOGY.md`/
   `PRODUCTION_READINESS_CHECKLIST.md` from earlier missions for the
   general shape of this).
3. **A real Paddle webhook secret and Sandbox-verified event shapes** —
   this mission's `paddle_provider.py` extraction logic
   (`current_billing_period`, `scheduled_change`, `adjustment.*`) was
   built from Paddle's publicly documented API shape. Mission 9 verified
   the `adjustment.*` refund shape against a real captured Sandbox event
   (and found/fixed a real mismatch — see `BILLING_OWNERSHIP_TRANSITION.md`
   §5.4); `current_billing_period`/`scheduled_change` and the chargeback
   variant of `adjustment.*` remain unverified. See
   `PADDLE_LIVE_INPUTS_REQUIRED.md` item 4 — this must be confirmed in
   Sandbox before Stage 3.
4. **A decision on the refund/chargeback entitlement policy** (§5.2 of
   `BILLING_OWNERSHIP_TRANSITION.md`) — this mission implemented a
   specific default (full refund/chargeback revokes, partial refund does
   not); confirm this is the intended business policy before it runs
   against real customers.

## Stage 1 — Dry-run reconciliation against a REAL data snapshot (read-only)

Never against production directly. Restore a recent production backup
into an isolated environment, then:

```bash
python -m app.scripts.loady_paddle_reconciliation_dry_run \
  --loady-database-url sqlite:////path/to/the/restored/snapshot/commercial.db
```

Review the full report — every category, not just `created`. Specifically:

- `orphaned_subscription` count above zero → those users need Mission 3's
  identity migration run for them first; this is a blocker, not a
  warning, for those specific users (everyone else can proceed).
- `duplicate_local_reference` count above zero → a real Loady data
  integrity issue exists and must be investigated and fixed in Loady's
  own database before continuing; never resolved by guessing here.
- `failed` count above zero → investigate each one individually; do not
  proceed to Stage 2 until this is zero or every failure is understood
  and accepted.

## Stage 2 — Configure Platform Core's real Paddle webhook endpoint (Sandbox first)

1. Register Platform Core's `POST /api/v1/billing/webhooks/paddle` as an
   **additional** webhook destination in Paddle's Sandbox dashboard —
   additional, not a replacement for Loady's own endpoint yet. Paddle
   supports multiple webhook destinations; both receive every event.
2. Drive a real Sandbox subscription through its full lifecycle (create,
   renew, cancel, refund) and confirm Platform Core's `BillingWebhookEvent`/
   `Subscription`/`PaymentRecord` rows match what Loady's own existing,
   trusted webhook handler recorded for the exact same events. Any
   mismatch here is exactly what `paddle_provider.py`'s shape-mapping got
   wrong and must be fixed before touching Paddle Live — see
   `PADDLE_LIVE_INPUTS_REQUIRED.md` item 4.
3. Only once Sandbox parity is confirmed: repeat step 1 against Paddle
   **Live**, still as an *additional* destination — Loady's own endpoint
   keeps running unchanged. This is the point at which Platform Core
   starts receiving real events, but nothing yet depends on it.

## Stage 3 — The real commit reconciliation (backfill)

During a defined low-traffic window, against the real production
database (read-only access is sufficient — see the module's own
docstring, this never writes back to Loady):

```bash
python -m app.scripts.loady_paddle_reconciliation_dry_run \
  --loady-database-url <production-read-replica-or-snapshot-url> --commit
```

Review the committed report the same way as Stage 1. This backfills
Platform Core's billing state to match Loady's own current state, for
every already-identity-migrated user.

## Stage 4 — Verification window (both systems live, neither yet authoritative for a decision)

With Platform Core now receiving real Paddle webhooks (Stage 2) and
having a correct backfilled starting state (Stage 3), let both systems
run in parallel for a defined period (a week is a reasonable starting
point). Compare Loady's own `Subscription` state against Platform Core's
for a sample of users on each new webhook event, using the same
comparison the reconciliation report already demonstrates
(`reconciled_with_change`). Any divergence found here is a real bug to
fix, not a business decision — the two systems processing the same
Paddle event stream must agree.

## Stage 5 — Cut Loady's own webhook endpoint over

Once Stage 4 shows sustained agreement:

1. Remove Loady's own endpoint from Paddle's webhook destinations (both
   Sandbox and Live) — Platform Core is now the only listener.
2. Loady's own `paddle_service.py`/`routes_billing.py` continue to exist
   and continue to serve reads (checkout initiation, billing history) —
   this mission does not require retiring them, and doing so is a
   separate, later decision (see `PADDLE_LIVE_INPUTS_REQUIRED.md`'s
   business-decision list).
3. Monitor `BillingWebhookEvent.status = "failed"` rows closely for the
   first real week — this is the number one signal that something in the
   shape-mapping was wrong despite Sandbox testing.

## Stage 6 — Decide what "Loady stops calling Paddle directly" means (out of scope for this mission)

This mission does not build a checkout-redirect change (Loady's frontend
still calls Loady's own `/api/billing/checkout` today, unchanged). A
future mission would need to either (a) leave checkout creation on
Loady's side indefinitely — a real supportable end-state, since checkout
creation and webhook processing are separable concerns — or (b) move
checkout creation to Platform Core's own (currently unconfigured, no-live-
call) `PaddleBillingProvider.create_checkout`. This mission takes no
position on which; it is listed explicitly as an unresolved business
decision in the final report.

## Rollback readiness

Read `BILLING_ROLLBACK_RUNBOOK.md` and rehearse it before Stage 2 — every
stage above has a corresponding, tested-in-this-mission way back.
