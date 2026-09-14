# Billing Architecture V2

Mission-brief Phases 8-12. See `MISSION_6_SECURITY_REVIEW.md` for the
security review of everything here.

## The provider interface

`app/services/billing/base.py::BillingProvider` - one implementation per
processor:

```python
class BillingProvider(ABC):
    def create_checkout(self, *, user_id, product_id, plan_id, success_url) -> CheckoutSession: ...
    def get_subscription(self, provider_subscription_ref) -> NormalizedSubscription | None: ...
    def cancel_subscription(self, provider_subscription_ref) -> None: ...
    def resume_subscription(self, provider_subscription_ref) -> None: ...
    def change_plan(self, provider_subscription_ref, new_price_ref) -> None: ...
    def open_customer_portal(self, provider_customer_ref) -> str: ...
    def verify_webhook(self, raw_body, headers) -> bool: ...
    def normalize_event(self, raw_body) -> NormalizedEvent: ...
```

`subscription_service`/`webhook_service` only ever see `NormalizedEvent`/
`NormalizedSubscription` - no Paddle-specific field name appears outside
`paddle_provider.py`.

## Two implementations, and why one of them can't do much

`PaddleBillingProvider` implements `verify_webhook` and `normalize_event`
for real - both are pure functions with no network call, ported from
Loady's existing, working `backend/app/services/paddle_service.py::
verify_webhook_signature` (`Paddle-Signature: ts=..;h1=..`, HMAC-SHA256).
Every other method raises `BillingProviderNotConfiguredError` - **no live
Paddle call is made anywhere in this mission** (mission-brief Phase 9/56).

`FakeBillingProvider` is a complete in-memory implementation used by
every test and available for local development - it is how the entire
subscription/webhook/payment pipeline is actually exercised end-to-end in
this mission (see `test_billing_webhooks.py`,
`test_service_and_billing_api.py`, `test_webhook_concurrency.py`).

## Inbound webhook flow

```text
POST /api/v1/billing/webhooks/{provider_name}
  -> billing_webhook_limiter (generous, per-provider, NOT per-admin-mutation)
  -> provider.verify_webhook(raw_body, headers)   [401 INVALID_WEBHOOK_SIGNATURE if it fails]
  -> BillingWebhookEvent row, UNIQUE(provider, provider_event_id)
       - IntegrityError on the insert = already recorded, return the existing row, do not reprocess
  -> provider.normalize_event(raw_body)
  -> subscription.* events  -> subscription_service.upsert_subscription (keyed on (provider, provider_subscription_ref))
     transaction.completed  -> a PaymentRecord IF one doesn't already exist for (provider, provider_reference)
  -> journal.status = processed | failed (failure never crashes the endpoint; it is stored for admin replay)
```

The very first webhook for a subscription that Platform Core has never
seen resolves who it belongs to from the event's `custom_data`
(`{user_id, product_id, plan_slug}`) - `custom_data` is only ever trusted
after signature verification, and only ever originates from a checkout
Platform Core itself created with the *authenticated* caller's own
`user_id` (see the security review, finding "custom_data trust
boundary"). Every subsequent event for an already-known subscription is
resolved by `(provider, provider_subscription_ref)` instead, so
`custom_data` is only load-bearing once per subscription.

## Payment ledger

`PaymentRecord` (extended, not replaced - see `BILLING.md` for the V1
boundary rules, which are unchanged): a row is written **only** by
`webhook_service._apply_transaction_event`, only from a `transaction.
completed` event, only once per `(provider, provider_reference)`. Gift,
free, internal, and promotion access paths have no code path that can
reach this function at all - not merely a convention, a structural
absence of the import (`gift_service.py` never imports
`app.services.billing`).

New columns are all nullable and additive: `subscription_id`,
`tax_cents`, `fee_cents`, `net_cents`, `refunded_amount_cents`,
`occurred_at`. None are fabricated when a provider doesn't supply them -
`None` means "not provided," never `0`.

## Replay

`POST /api/v1/admin/billing/webhooks/{id}/replay` (super-admin only)
re-normalizes the stored raw payload and re-runs processing. Safe against
double-counting because both write paths it can reach are themselves
idempotent on their own unique keys - replaying a `transaction.completed`
event that already produced a `PaymentRecord` is a no-op (verified by
`test_transaction_completed_creates_payment_record_once`, which replays
and re-asserts the count is still 1).

## Revenue metrics (Phase 12) - NOT built

No MRR/ARR/churn/ARPU calculation exists. `GET /api/v1/admin/payments`
lists real, never-fabricated `PaymentRecord` rows; computing aggregate
metrics from them is future work, explicitly deferred rather than
estimated - see the Mission 6 final report.
