"""Mission 9/14: pure-function unit tests for `PaddleBillingProvider.
normalize_event` against REAL captured Paddle Sandbox evidence - no
network call, no secret; `normalize_event` only parses an already-received
raw body.

Two real events have now been captured (via `scripts/paddle-sandbox-
evidence/collect_evidence.py`, run by the operator against their own
Sandbox account - never by this codebase, which has no Paddle egress):

1. Mission 9: a real `adjustment.created` refund, `status:
   "pending_approval"` - proved `adjustment.created` is not itself
   completion.
2. Mission 14: the SAME adjustment's real `adjustment.updated`,
   `status: "approved"`, PLUS a real `subscription.updated` (a scheduled
   cancellation) confirming `current_billing_period`/`scheduled_change`
   extraction, both previously built from Paddle's public docs alone.

Fixtures below are shaped byte-for-byte (field names and nesting) after
the real captures, with every identifying value (subscription/customer/
transaction/product/price ids, the linked user id, timestamps) replaced
by clearly-synthetic placeholders - see docs/platform/
BILLING_OWNERSHIP_TRANSITION.md §6d for the sanitization statement.
"""
from __future__ import annotations

import json

from app.services.billing.paddle_provider import PaddleBillingProvider


def _real_shaped_refund_payload(
    *, status: str, event_type: str = "adjustment.created", adjustment_type: str = "partial",
    transaction_id: str = "txn_01hyyyyyyyyyyyyyyyyyyyyyy", subscription_id: str = "sub_01hxxxxxxxxxxxxxxxxxxxxxx",
    event_id: str = "evt_01hzzzzzzzzzzzzzzzzzzzzzzz",
) -> bytes:
    """Shaped from the real captured adjustment evidence. `adjustment_type`
    defaults to `"partial"` because that is what the real top-level
    `data.type` field actually said (Mission 14) - a correction from this
    fixture's original Mission 9 guess of `"full"` at the top level. Real
    evidence showed `type` is NOT the same at every level: the top-level
    adjustment `type` describes the adjustment as a whole relative to the
    original transaction, while each `items[].type` describes that single
    item - here `items[0].type == "full"` (that one item was refunded in
    full) even though the adjustment's own `type` was `"partial"`. Neither
    is read by `normalize_event` today (see its own comments), so this is
    a fixture-fidelity correction, not a behavior change."""
    payload = {
        "event_id": event_id,
        "event_type": event_type,
        "occurred_at": "2026-09-15T00:40:01.288301Z",
        "data": {
            "id": "adj_01hzzzzzzzzzzzzzzzzzzzzzzz",
            "action": "refund",
            "transaction_id": transaction_id,
            "subscription_id": subscription_id,
            "customer_id": "ctm_01hwwwwwwwwwwwwwwwwwwwwww",
            "reason": "other",
            "credit_applied_to_balance": None,
            "currency_code": "USD",
            "status": status,
            "items": [
                {
                    "id": "adjitm_01hzzzzzzzzzzzzzzzzzzzzzzz",
                    "type": "full",
                    "amount": "499",
                    "totals": {"tax": "0", "total": "499", "subtotal": "499"},
                    "item_id": "txnitm_01hzzzzzzzzzzzzzzzzzzzzzzz",
                    "proration": None,
                }
            ],
            "totals": {
                "fee": "75", "tax": "0", "total": "499", "earnings": "424",
                "subtotal": "499", "retained_fee": "75", "currency_code": "USD",
            },
            "payout_totals": {
                "fee": "75", "tax": "0", "total": "499", "earnings": "424",
                "subtotal": "499", "retained_fee": "75", "currency_code": "USD",
            },
            "created_at": "2026-09-15T00:30:52.811065Z",
            "updated_at": "2026-09-15T00:40:01.269444Z",
            "type": adjustment_type,
            "tax_rates_used": [
                {"totals": {"tax": "0", "total": "499", "subtotal": "499"}, "tax_rate": "0"}
            ],
        },
    }
    return json.dumps(payload).encode("utf-8")


def _real_shaped_subscription_updated_payload() -> bytes:
    """Shaped from the real captured `subscription.updated` evidence
    (Mission 14) - a scheduled cancellation on an otherwise-active
    subscription. Confirms `current_billing_period.starts_at/ends_at` and
    `scheduled_change.action == "cancel"` are exactly the real field
    names/values `paddle_provider.py` was already extracting, built
    originally from Paddle's public docs alone and never verified against
    a real event before this."""
    payload = {
        "event_id": "evt_01hsubzzzzzzzzzzzzzzzzzzz",
        "event_type": "subscription.updated",
        "occurred_at": "2026-09-15T15:47:36.385668Z",
        "data": {
            "id": "sub_01hxxxxxxxxxxxxxxxxxxxxxx",
            "status": "active",
            "customer_id": "ctm_01hwwwwwwwwwwwwwwwwwwwwww",
            "address_id": "add_01hvvvvvvvvvvvvvvvvvvvvvvv",
            "business_id": None,
            "currency_code": "USD",
            "created_at": "2026-01-06T18:50:13.983Z",
            "updated_at": "2026-09-15T15:47:36.245Z",
            "started_at": "2026-01-06T18:50:13.490969Z",
            "first_billed_at": "2026-01-06T18:50:13.490969Z",
            "next_billed_at": None,
            "paused_at": None,
            "canceled_at": None,
            "discount": None,
            "collection_mode": "automatic",
            "billing_details": None,
            "current_billing_period": {
                "starts_at": "2026-09-06T18:50:13.490969Z",
                "ends_at": "2026-10-06T18:50:13.490969Z",
            },
            "billing_cycle": {"interval": "month", "frequency": 1},
            "scheduled_change": {
                "items": None, "action": "cancel", "resume_at": None,
                "effective_at": "2026-10-06T18:50:13.490969Z",
            },
            "items": [
                {
                    "price": {
                        "id": "pri_01htestzzzzzzzzzzzzzzzzz",
                        "name": "Monthly", "type": "standard", "status": "active",
                        "quantity": {"maximum": 100, "minimum": 1},
                        "tax_mode": "location",
                        "created_at": "2026-01-06T17:40:34.366Z",
                        "product_id": "pro_01htestzzzzzzzzzzzzzzzzz",
                        "unit_price": {"amount": "999", "currency_code": "USD"},
                        "updated_at": "2026-01-06T17:40:34.366Z",
                        "custom_data": None,
                        "description": "Sanitized test plan monthly",
                        "import_meta": None, "trial_period": None,
                        "billing_cycle": {"interval": "month", "frequency": 1},
                        "unit_price_overrides": [],
                    },
                    "status": "active",
                    "product": {
                        "id": "pro_01htestzzzzzzzzzzzzzzzzz",
                        "name": "Sanitized Test Plan", "type": "standard", "status": "active",
                        "image_url": None,
                        "created_at": "2026-01-06T17:40:34.183Z",
                        "updated_at": "2026-01-06T17:40:34.183Z",
                        "custom_data": None,
                        "description": "Sanitized test plan for a regression fixture.",
                        "tax_category": "saas",
                    },
                    "quantity": 1, "recurring": True,
                    "created_at": "2026-01-06T19:39:02.567Z",
                    "updated_at": "2026-01-06T19:41:49.685Z",
                    "trial_dates": None, "next_billed_at": None,
                    "previously_billed_at": "2026-01-06T19:39:02.567Z",
                }
            ],
            "custom_data": {"user_id": "00000000-0000-0000-0000-000000000000"},
            "consent_requirements": [],
            "import_meta": None,
        },
    }
    return json.dumps(payload).encode("utf-8")


class TestAdjustmentNormalizationAgainstRealPayload:
    def test_pending_approval_refund_is_not_treated_as_final(self):
        event = PaddleBillingProvider().normalize_event(_real_shaped_refund_payload(status="pending_approval"))

        assert event.status == "refunded", "action=refund still classifies as a refund-kind event"
        assert event.adjustment_status == "pending_approval", (
            "Paddle's own lifecycle status must be captured separately from the action classification"
        )
        assert event.provider_transaction_ref == "txn_01hyyyyyyyyyyyyyyyyyyyyyy"
        assert event.amount_cents == 499
        assert event.currency == "USD"

    def test_approved_refund_carries_the_same_shape(self):
        """Mission 14: this is now a REAL captured shape (the same
        adjustment's own real adjustment.updated, status=approved), not
        just Mission 9's pending_approval extrapolated forward."""
        event = PaddleBillingProvider().normalize_event(
            _real_shaped_refund_payload(status="approved", event_type="adjustment.updated")
        )

        assert event.status == "refunded"
        assert event.adjustment_status == "approved"
        assert event.amount_cents == 499
        assert event.currency == "USD"
        assert event.provider_transaction_ref == "txn_01hyyyyyyyyyyyyyyyyyyyyyy"

    def test_rejected_refund_carries_the_same_shape(self):
        event = PaddleBillingProvider().normalize_event(
            _real_shaped_refund_payload(status="rejected", event_type="adjustment.updated")
        )

        assert event.status == "refunded"
        assert event.adjustment_status == "rejected"

    def test_non_adjustment_event_has_no_adjustment_status(self):
        payload = {
            "event_id": "evt_transaction",
            "event_type": "transaction.completed",
            "occurred_at": "2026-09-15T00:00:00.000000Z",
            "data": {"id": "txn_1", "status": "completed", "currency_code": "USD",
                      "details": {"totals": {"total": "499"}}},
        }
        event = PaddleBillingProvider().normalize_event(json.dumps(payload).encode("utf-8"))
        assert event.adjustment_status is None


class TestSubscriptionUpdatedNormalizationAgainstRealPayload:
    """Mission 14: the first real captured `subscription.updated` event -
    confirms extraction logic that, until now, was built purely from
    Paddle's public docs and never verified against a real event."""

    def test_current_billing_period_is_extracted_with_the_real_field_names(self):
        event = PaddleBillingProvider().normalize_event(_real_shaped_subscription_updated_payload())

        assert event.current_period_start is not None
        assert event.current_period_end is not None
        assert event.current_period_start.isoformat().startswith("2026-09-06T18:50:13.490969")
        assert event.current_period_end.isoformat().startswith("2026-10-06T18:50:13.490969")

    def test_scheduled_cancellation_sets_cancel_at_period_end(self):
        event = PaddleBillingProvider().normalize_event(_real_shaped_subscription_updated_payload())

        assert event.cancel_at_period_end is True
        assert event.status == "active", "a scheduled cancellation does not itself change subscription.status"

    def test_subscription_reference_and_customer_extracted(self):
        event = PaddleBillingProvider().normalize_event(_real_shaped_subscription_updated_payload())

        assert event.provider_subscription_ref == "sub_01hxxxxxxxxxxxxxxxxxxxxxx"
        assert event.provider_customer_ref == "ctm_01hwwwwwwwwwwwwwwwwwwwwww"
        assert event.amount_cents is None, "a subscription event carries no top-level payment amount"
