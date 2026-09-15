"""Mission 9: pure-function unit tests for `PaddleBillingProvider.normalize_event`
against a real captured Paddle Sandbox `adjustment.created` refund's confirmed
field values (type=full, action=refund, reason=other, totals.total=499,
status=pending_approval). No network call, no secret - `normalize_event`
only parses an already-received raw body.
"""
from __future__ import annotations

import json

from app.services.billing.paddle_provider import PaddleBillingProvider


def _real_shaped_refund_payload(*, status: str, event_type: str = "adjustment.created") -> bytes:
    """Shaped from Paddle's publicly documented Adjustment object plus the
    real Sandbox-confirmed field values from this mission's evidence."""
    payload = {
        "event_id": "evt_01hzzzzzzzzzzzzzzzzzzzzzzz",
        "event_type": event_type,
        "occurred_at": "2026-09-15T00:00:00.000000Z",
        "data": {
            "id": "adj_01hzzzzzzzzzzzzzzzzzzzzzzz",
            "action": "refund",
            "type": "full",
            "reason": "other",
            "status": status,
            "transaction_id": "txn_01hyyyyyyyyyyyyyyyyyyyyyy",
            "subscription_id": "sub_01hxxxxxxxxxxxxxxxxxxxxxx",
            "customer_id": "ctm_01hwwwwwwwwwwwwwwwwwwwwww",
            "currency_code": "USD",
            "totals": {"subtotal": "499", "tax": "0", "total": "499"},
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
        event = PaddleBillingProvider().normalize_event(
            _real_shaped_refund_payload(status="approved", event_type="adjustment.updated")
        )

        assert event.status == "refunded"
        assert event.adjustment_status == "approved"
        assert event.amount_cents == 499

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
