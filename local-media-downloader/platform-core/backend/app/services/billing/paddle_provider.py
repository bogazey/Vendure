"""Paddle Billing adapter. Webhook verification and event normalization are
real, pure functions (no network call) - ported from Loady's own
`backend/app/services/paddle_service.py::verify_webhook_signature`, which
this mirrors exactly (`Paddle-Signature: ts=<unix>;h1=<hex hmac>`,
`h1 = HMAC-SHA256(secret, f"{ts}:{raw_body}")`).

Every other method requires a live Paddle API call and is explicitly not
exercised in this mission (mission-brief Phase 9: "Do not call Paddle Live
during development") - each raises `BillingProviderNotConfiguredError`
rather than silently succeeding.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone

from app.config.settings import get_settings
from app.services.billing.base import (
    BillingProvider,
    BillingProviderNotConfiguredError,
    CheckoutSession,
    NormalizedEvent,
    NormalizedSubscription,
)

# Paddle's own subscription.status values -> Platform Core's SubscriptionStatus.
_PADDLE_STATUS_MAP = {
    "trialing": "trialing",
    "active": "active",
    "past_due": "past_due",
    "paused": "paused",
    "canceled": "canceled",
}


class PaddleBillingProvider(BillingProvider):
    name = "paddle"

    def verify_webhook(self, raw_body: bytes, headers: dict[str, str]) -> bool:
        secret = get_settings().paddle_webhook_secret
        signature_header = headers.get("paddle-signature") or headers.get("Paddle-Signature")
        if not signature_header or not secret:
            return False
        parts: dict[str, str] = {}
        for chunk in signature_header.split(";"):
            if "=" in chunk:
                key, _, value = chunk.partition("=")
                parts[key.strip()] = value.strip()
        ts, h1 = parts.get("ts"), parts.get("h1")
        if not ts or not h1:
            return False
        signed_payload = f"{ts}:{raw_body.decode('utf-8', errors='replace')}"
        computed = hmac.new(secret.encode("utf-8"), signed_payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(computed, h1)

    def normalize_event(self, raw_body: bytes) -> NormalizedEvent:
        payload = json.loads(raw_body)
        data = payload.get("data", {})
        event_type = payload.get("event_type", "")
        occurred_at_raw = payload.get("occurred_at")
        try:
            occurred_at = datetime.fromisoformat(occurred_at_raw.replace("Z", "+00:00")) if occurred_at_raw else datetime.now(timezone.utc)
        except ValueError:
            occurred_at = datetime.now(timezone.utc)

        amount_cents: int | None = None
        currency: str | None = None
        totals = (data.get("details") or {}).get("totals") if isinstance(data.get("details"), dict) else None
        if totals:
            try:
                amount_cents = int(totals.get("total", 0))
            except (TypeError, ValueError):
                amount_cents = None
            currency = data.get("currency_code")

        status = _PADDLE_STATUS_MAP.get(data.get("status")) if event_type.startswith("subscription.") else data.get("status")

        return NormalizedEvent(
            provider_event_id=payload.get("event_id", ""),
            event_type=event_type,
            provider_subscription_ref=data.get("subscription_id") or (data.get("id") if event_type.startswith("subscription.") else None),
            provider_customer_ref=data.get("customer_id"),
            occurred_at=occurred_at,
            amount_cents=amount_cents,
            currency=currency,
            status=status,
            raw=payload,
            custom_data=data.get("custom_data") if isinstance(data.get("custom_data"), dict) else None,
        )

    def create_checkout(self, *, user_id: str, product_id: str, plan_id: str, success_url: str) -> CheckoutSession:
        raise BillingProviderNotConfiguredError(
            "Paddle checkout creation requires a live Paddle API call - not performed in this mission."
        )

    def get_subscription(self, provider_subscription_ref: str) -> NormalizedSubscription | None:
        raise BillingProviderNotConfiguredError(
            "Paddle subscription lookup requires a live Paddle API call - not performed in this mission."
        )

    def cancel_subscription(self, provider_subscription_ref: str) -> None:
        raise BillingProviderNotConfiguredError(
            "Paddle subscription cancellation requires a live Paddle API call - not performed in this mission."
        )

    def resume_subscription(self, provider_subscription_ref: str) -> None:
        raise BillingProviderNotConfiguredError(
            "Paddle subscription resume requires a live Paddle API call - not performed in this mission."
        )

    def change_plan(self, provider_subscription_ref: str, new_price_ref: str) -> None:
        raise BillingProviderNotConfiguredError(
            "Paddle plan change requires a live Paddle API call - not performed in this mission."
        )

    def open_customer_portal(self, provider_customer_ref: str) -> str:
        raise BillingProviderNotConfiguredError(
            "Paddle customer portal URL requires a live Paddle API call - not performed in this mission."
        )
