"""Mission 6 continuation (webhook hardening, previous security review
finding): invalid-signature deliveries must not share the same rate-limit
budget as legitimate ones - proven by exhausting the invalid-signature
limiter and confirming a legitimately-signed delivery is still accepted
right after."""
from __future__ import annotations

import json

from app.services.billing.fake_provider import FakeBillingProvider
from app.services.rate_limit_service import billing_webhook_invalid_signature_limiter, billing_webhook_limiter


def test_invalid_signatures_get_their_own_stricter_budget(client):
    billing_webhook_invalid_signature_limiter.clear()
    billing_webhook_limiter.clear()

    payload = json.dumps({"event_id": "evt-hardening-1", "event_type": "subscription.created", "occurred_at": "2026-01-01T00:00:00+00:00"}).encode()

    # Flood with invalid signatures - well past the strict 20/min ceiling.
    last_status = None
    for _ in range(25):
        resp = client.post("/api/v1/billing/webhooks/fake", content=payload, headers={"fake-signature": "not-a-real-signature"})
        last_status = resp.status_code
    assert last_status == 429  # the invalid-signature budget is now exhausted

    # A LEGITIMATE, correctly-signed delivery must still succeed - proving
    # the attacker's flood did not consume the legitimate-traffic budget.
    good_payload = json.dumps({
        "event_id": "evt-hardening-2", "event_type": "subscription.created", "occurred_at": "2026-01-01T00:00:00+00:00",
        "subscription_ref": "sub-hardening-2", "customer_ref": "cust-hardening-2", "status": "active",
    }).encode()
    signature = FakeBillingProvider.sign(good_payload)
    good_resp = client.post("/api/v1/billing/webhooks/fake", content=good_payload, headers={"fake-signature": signature})
    # This specific event has no matching product/plan (no custom_data),
    # so it will fail application-level processing - but the important
    # assertion is that it was NOT rejected by the invalid-signature rate
    # limiter (i.e., it got past signature verification and into normal
    # processing, unlike the flood above).
    assert good_resp.status_code == 200
    assert good_resp.json()["status"] == "failed"  # processed, but no identity to resolve - a different failure mode than 429


def test_valid_signature_requests_are_not_throttled_by_the_invalid_bucket(client):
    billing_webhook_invalid_signature_limiter.clear()
    billing_webhook_limiter.clear()

    for i in range(30):
        payload = json.dumps({
            "event_id": f"evt-hardening-valid-{i}", "event_type": "subscription.created",
            "occurred_at": "2026-01-01T00:00:00+00:00",
        }).encode()
        signature = FakeBillingProvider.sign(payload)
        resp = client.post("/api/v1/billing/webhooks/fake", content=payload, headers={"fake-signature": signature})
        assert resp.status_code == 200, f"request {i} unexpectedly rate-limited or rejected: {resp.text}"
