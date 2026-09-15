# Paddle Webhook Event Matrix (Mission 15, Phase 16)

Canonical table, built by reading `paddle_provider.py::normalize_event` and
`webhook_service.py` directly (not copied from a prior mission's prose
description). Every event Platform Core's code recognizes today.

| Event type | Business meaning | Code path | Entitlement effect | Payment effect | Idempotency behavior | Evidence level | Production monitoring expectation |
|---|---|---|---|---|---|---|---|
| `subscription.created`/`subscription.updated` (any `data.status`) | Subscription lifecycle change (active/trialing/past_due/paused/canceled, or a scheduled/immediate plan change) | `_apply_subscription_event` (`_SUBSCRIPTION_EVENT_TYPES`) | `subscription_service.upsert_subscription` re-derives the plan from the event's `custom_data.plan_slug` (first event) or the subscription's own current item (follow-up events, unless a valid new `plan_slug` for the same product is present — an upgrade/downgrade) | None directly (subscription status only) | Keyed by `(provider, provider_event_id)` unique constraint on `BillingWebhookEvent`; a duplicate delivery raises `IntegrityError`, caught and treated as already-recorded, not reprocessed | SANDBOX VERIFIED (Mission 14, `current_billing_period`/`scheduled_change` field extraction) | Alert on a sustained rise in `status="past_due"` or `status="failed"` `BillingWebhookEvent` rows for this type |
| `transaction.completed` (and other `transaction.*`) | A successful (or otherwise-stated) one-off/recurring charge | `_apply_transaction_event` (`_TRANSACTION_EVENT_TYPES`) | None directly — entitlement is granted by the *subscription* event's plan resolution, not the transaction itself | Creates/updates the `PaymentRecord` keyed by `provider_reference` (the transaction id); re-delivery is a no-op ("idempotent: already recorded", `webhook_service.py:229`) | Same `BillingWebhookEvent` unique-constraint dedup, plus the `PaymentRecord` reference-based idempotency | DOCUMENTED ONLY (no real captured `transaction.*` Sandbox event audited this mission or prior — only `adjustment.*`/`subscription.updated` have real captures per `FINAL_PREPRODUCTION_EVIDENCE_AUDIT.md` §3) | Alert on any `transaction.completed` that never resolves to a `PaymentRecord` row (would indicate a normalization gap) |
| `adjustment.created`/`adjustment.updated`, `data.action == "refund"` (→ `event.status = "refunded"`) | A refund has been recorded (`pending_approval`) or reached a terminal state (`approved`/`rejected`) | `_apply_adjustment_event` | **Only on `adjustment_status == "approved"`**: revokes the Paddle-funded entitlement for the affected product, preserving any independently-sourced entitlement (gift/internal/lifetime) via `GiftedAccess.external_ref` (Mission 12). `pending_approval` and `rejected` apply **no** entitlement change (`webhook_service.py:303-305`) | On `approved` only: increments `PaymentRecord.refunded_amount_cents`, sets `status="refunded"` if the full amount is now refunded | The `already_refunded` accumulator (`webhook_service.py:324`) makes a redelivered `approved` event a no-op past the first application — UNIT TEST VERIFIED (`test_redelivering_the_same_approved_event_never_double_applies`) | SANDBOX VERIFIED, real captured pending_approval→approved pair (Missions 9/14), zero mismatches | Alert on any `adjustment_status == "rejected"` that still shows an entitlement/payment change (would indicate the gate broke); alert on `PaymentRecord.refunded_amount_cents` exceeding the original transaction amount (should be structurally impossible, but is the sharpest possible signal something is wrong) |
| `adjustment.created`/`adjustment.updated`, `data.action == "chargeback"` (→ `event.status = "disputed"`) | A cardholder dispute | `_apply_adjustment_event` | Immediate suspension on the `disputed` classification itself — **`adjustment_status` is deliberately NOT consulted for this branch** (`webhook_service.py:307`, comment: "WAITING is the risky direction [for a dispute] — the money is already gone"), i.e. no `pending_approval` grace period, unlike refunds | Sets the subscription to `SubscriptionStatus.DISPUTED` / payment to `PaymentStatus.DISPUTED` immediately | Same `BillingWebhookEvent` dedup as every other event type — structurally identical protection, but **never exercised against a real chargeback shape** | **LIVE OBSERVATION ONLY** — no Sandbox chargeback scenario exists to test against (confirmed, Mission 13); code path exists and is unit-tested only against a hand-built fixture shaped from Paddle's public docs, not a real capture | **Highest-priority manual-review alert on every single occurrence** in production — this is the one event type this mission cannot claim is field-verified; the first real one must be manually reviewed against the recorded outcome, not just logged |
| Any other event type (`payment_method.*`, `customer.*`, etc.) | Not business-logic-relevant to entitlements/payments today | Falls through `_apply_event`'s `if/elif` chain to the final `journal.status = "processed"` with no side effect | None | None | Recorded in `BillingWebhookEvent` for audit/idempotency bookkeeping only — mirrors Loady's own `paddle_service._HANDLED_EVENT_TYPES` precedent (i.e. this is a deliberate, precedented pattern, not an oversight) | CODE VERIFIED (the fall-through itself) | No alert needed — this is expected, inert traffic |

## Idempotency guarantee that applies to every row above

`BillingWebhookEvent(provider, provider_event_id)` carries a database-level
unique constraint. A retried delivery of the exact same Paddle event
(same `event_id`) always hits this constraint before any business logic
runs a second time; the `IntegrityError` is caught and treated as
"already recorded," never re-raised to the caller as an error (Paddle
would otherwise interpret a 5xx as "keep retrying forever"). This is the
single mechanism every event type's idempotency in the table above relies
on — it is not reimplemented per event type.

## What this matrix explicitly does not claim

- It does not claim `transaction.*` events have been verified against a
  real Sandbox capture — only `adjustment.*` and `subscription.updated`
  have. This is stated plainly in the table rather than silently implied
  by the matrix's uniform formatting.
- It does not claim the chargeback row is anything more than
  code-that-exists-and-is-unit-tested-against-a-synthetic-fixture. Every
  other row in this matrix has at least one tier of real-evidence backing
  beyond that; this one does not, and this mission does not manufacture
  evidence that cannot exist pre-Live.
