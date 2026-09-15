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

# Paddle Billing reports refunds/chargebacks as `adjustment.created`, with
# `data.action` naming what kind of adjustment it is - never a dedicated
# `transaction.refunded` event type. `action="credit"` (a goodwill balance
# credit, not a refund of a specific transaction) is deliberately excluded:
# it has no `transaction_id` to correlate against and never affects an
# entitlement, so it is left unhandled (stored for audit, otherwise
# ignored) rather than guessed at.
_ADJUSTMENT_ACTION_MAP = {
    "refund": "refunded",
    "chargeback": "disputed",
}


def _parse_paddle_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _adjustment_amount(data: dict) -> tuple[int | None, str | None]:
    """An adjustment's own `totals.total` (its amount, in the adjustment's
    own currency) - structurally identical in shape to a transaction's
    `details.totals.total`, but Paddle documents it at the top level of
    the adjustment object rather than nested under `details`. `None`/`None`
    if absent, never fabricated as 0 (mission-brief: "do NOT fabricate
    unavailable values")."""
    totals = data.get("totals") if isinstance(data.get("totals"), dict) else None
    if not totals or totals.get("total") is None:
        return None, None
    try:
        return int(totals["total"]), data.get("currency_code")
    except (TypeError, ValueError):
        return None, None


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

        current_period_start: datetime | None = None
        current_period_end: datetime | None = None
        cancel_at_period_end: bool | None = None
        provider_transaction_ref: str | None = None
        adjustment_status: str | None = None

        if event_type.startswith("transaction."):
            provider_transaction_ref = data.get("id")
            status = data.get("status")
        elif event_type.startswith("adjustment."):
            # Paddle Billing reports refunds/chargebacks as `adjustment.*`,
            # never a `transaction.refunded` event - see
            # `_ADJUSTMENT_ACTION_MAP`'s own docstring. `transaction_id` is
            # the ORIGINAL transaction being adjusted, not this adjustment's
            # own id - that is exactly what lets a refund be correlated
            # back to the `PaymentRecord` the original transaction created.
            #
            # `data.status` is Paddle's own approval lifecycle for the
            # adjustment itself (verified against a real captured Sandbox
            # event: a fresh `adjustment.created` refund reported
            # `status: "pending_approval"`, NOT an already-completed refund).
            # This is kept separate from `status` below (the action
            # classification "refunded"/"disputed") precisely so
            # `webhook_service` can tell "recorded but not yet approved"
            # apart from "confirmed" - see `_apply_adjustment_event`.
            provider_transaction_ref = data.get("transaction_id")
            status = _ADJUSTMENT_ACTION_MAP.get(data.get("action"))
            adjustment_status = data.get("status")
            amount_cents, currency = _adjustment_amount(data)
        elif event_type.startswith("subscription."):
            status = _PADDLE_STATUS_MAP.get(data.get("status"))
            current_period = data.get("current_billing_period") or {}
            current_period_start = _parse_paddle_datetime(current_period.get("starts_at"))
            current_period_end = _parse_paddle_datetime(current_period.get("ends_at"))
            cancel_at_period_end = (data.get("scheduled_change") or {}).get("action") == "cancel"
        else:
            status = data.get("status")

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
            provider_transaction_ref=provider_transaction_ref,
            current_period_start=current_period_start,
            current_period_end=current_period_end,
            cancel_at_period_end=cancel_at_period_end,
            adjustment_status=adjustment_status,
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
