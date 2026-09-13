"""An in-memory billing provider used by tests and local development so the
subscription/webhook pipeline can be exercised end-to-end without any real
network call or live credentials. Never registered as the default provider
for a real product (`app/config/settings.py::billing_default_provider`
defaults to `"paddle"`)."""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone

from app.services.billing.base import (
    BillingProvider,
    CheckoutSession,
    NormalizedEvent,
    NormalizedSubscription,
)

_FAKE_SECRET = "fake-provider-shared-secret"


class FakeBillingProvider(BillingProvider):
    name = "fake"

    def __init__(self) -> None:
        self._subscriptions: dict[str, NormalizedSubscription] = {}

    def create_checkout(self, *, user_id: str, product_id: str, plan_id: str, success_url: str) -> CheckoutSession:
        ref = f"fake_txn_{uuid.uuid4().hex}"
        return CheckoutSession(url=f"{success_url}?ref={ref}", provider_reference=ref)

    def create_subscription(self, *, customer_ref: str, status: str = "active", days: int = 30) -> NormalizedSubscription:
        """Test helper (not part of `BillingProvider`): register a fake
        subscription so `get_subscription`/webhook events can reference it."""
        ref = f"fake_sub_{uuid.uuid4().hex}"
        now = datetime.now(timezone.utc)
        subscription = NormalizedSubscription(
            provider_subscription_ref=ref,
            provider_customer_ref=customer_ref,
            status=status,
            current_period_start=now,
            current_period_end=now + timedelta(days=days),
            cancel_at_period_end=False,
        )
        self._subscriptions[ref] = subscription
        return subscription

    def get_subscription(self, provider_subscription_ref: str) -> NormalizedSubscription | None:
        return self._subscriptions.get(provider_subscription_ref)

    def cancel_subscription(self, provider_subscription_ref: str) -> None:
        sub = self._subscriptions.get(provider_subscription_ref)
        if sub is not None:
            sub.status = "canceled"

    def resume_subscription(self, provider_subscription_ref: str) -> None:
        sub = self._subscriptions.get(provider_subscription_ref)
        if sub is not None:
            sub.status = "active"

    def change_plan(self, provider_subscription_ref: str, new_price_ref: str) -> None:
        return None

    def open_customer_portal(self, provider_customer_ref: str) -> str:
        return f"https://billing.example.test/portal/{provider_customer_ref}"

    def verify_webhook(self, raw_body: bytes, headers: dict[str, str]) -> bool:
        signature = headers.get("fake-signature")
        if not signature:
            return False
        computed = hmac.new(_FAKE_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(computed, signature)

    @staticmethod
    def sign(raw_body: bytes) -> str:
        return hmac.new(_FAKE_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()

    def normalize_event(self, raw_body: bytes) -> NormalizedEvent:
        payload = json.loads(raw_body)
        occurred_at_raw = payload.get("occurred_at")
        occurred_at = (
            datetime.fromisoformat(occurred_at_raw) if occurred_at_raw else datetime.now(timezone.utc)
        )
        return NormalizedEvent(
            provider_event_id=payload["event_id"],
            event_type=payload["event_type"],
            provider_subscription_ref=payload.get("subscription_ref"),
            provider_customer_ref=payload.get("customer_ref"),
            occurred_at=occurred_at,
            amount_cents=payload.get("amount_cents"),
            currency=payload.get("currency"),
            status=payload.get("status"),
            raw=payload,
            custom_data=payload.get("custom_data"),
        )
