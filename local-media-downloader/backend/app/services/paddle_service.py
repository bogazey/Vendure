"""Checkout price resolution and webhook -> internal state mapping.

The webhook handler is the SOURCE OF TRUTH for subscription state - nothing
here trusts a frontend "checkout succeeded" redirect. See routes_billing.py
for the endpoint that calls into this after verifying the Paddle-Signature
header.
"""
from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.commercial_settings import get_commercial_settings
from app.config.logging_config import get_logger
from app.database.commercial_models import BillingEvent, Subscription, User
from app.models.commercial_enums import BillingEventStatus, BillingPeriod, Plan, SubscriptionStatus
from app.models.commercial_schemas import CheckoutResponse
from app.services import email_service
from app.utils.exceptions import InvalidWebhookSignatureError

logger = get_logger("paddle_service")

# Paddle's own subscription.status values -> our normalized SubscriptionStatus.
_PADDLE_STATUS_MAP = {
    "trialing": SubscriptionStatus.TRIALING,
    "active": SubscriptionStatus.ACTIVE,
    "past_due": SubscriptionStatus.PAST_DUE,
    "paused": SubscriptionStatus.PAUSED,
    "canceled": SubscriptionStatus.CANCELED,
}

# Event types this app acts on. Anything else is stored (for idempotency
# bookkeeping / audit) but otherwise ignored.
_HANDLED_EVENT_TYPES = {
    "subscription.created",
    "subscription.activated",
    "subscription.updated",
    "subscription.canceled",
    "subscription.paused",
    "subscription.resumed",
    "transaction.completed",
    "transaction.payment_failed",
}


def verify_webhook_signature(raw_body: bytes, signature_header: str | None, secret: str) -> bool:
    """Paddle Billing signs webhooks as `Paddle-Signature: ts=<unix>;h1=<hex hmac>`,
    where h1 = HMAC-SHA256(secret, f"{ts}:{raw_body}")."""
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


def _price_id_for(plan: Plan, billing_period: BillingPeriod) -> str:
    settings = get_commercial_settings()
    mapping = {
        (Plan.PRO, BillingPeriod.MONTHLY): settings.paddle_pro_monthly_price_id,
        (Plan.PRO, BillingPeriod.ANNUAL): settings.paddle_pro_annual_price_id,
        (Plan.CREATOR, BillingPeriod.MONTHLY): settings.paddle_creator_monthly_price_id,
        (Plan.CREATOR, BillingPeriod.ANNUAL): settings.paddle_creator_annual_price_id,
    }
    return mapping.get((plan, billing_period), "")


def _plan_and_period_for_price_id(price_id: str) -> tuple[Plan, BillingPeriod] | None:
    settings = get_commercial_settings()
    mapping = {
        settings.paddle_pro_monthly_price_id: (Plan.PRO, BillingPeriod.MONTHLY),
        settings.paddle_pro_annual_price_id: (Plan.PRO, BillingPeriod.ANNUAL),
        settings.paddle_creator_monthly_price_id: (Plan.CREATOR, BillingPeriod.MONTHLY),
        settings.paddle_creator_annual_price_id: (Plan.CREATOR, BillingPeriod.ANNUAL),
    }
    if not price_id:
        return None
    return mapping.get(price_id)


def build_checkout(user: User, plan: Plan, billing_period: BillingPeriod) -> CheckoutResponse:
    settings = get_commercial_settings()
    price_id = _price_id_for(plan, billing_period)
    if not price_id:
        raise ValueError(
            f"No Paddle price configured for {plan.value}/{billing_period.value}. "
            "Set the corresponding PADDLE_*_PRICE_ID environment variable."
        )
    return CheckoutResponse(
        price_id=price_id,
        client_token=settings.paddle_client_token,
        plan=plan,
        billing_period=billing_period,
        custom_data={"user_id": user.id},
    )


def _parse_paddle_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _extract_user_id(data: dict) -> str | None:
    custom_data = data.get("custom_data") or {}
    return custom_data.get("user_id")


def _upsert_subscription_from_event(session: Session, data: dict) -> None:
    provider_subscription_id = data.get("id")
    if not provider_subscription_id:
        return

    user_id = _extract_user_id(data)
    subscription = session.execute(
        select(Subscription).where(Subscription.provider_subscription_id == provider_subscription_id)
    ).scalars().first()

    if subscription is None:
        if not user_id:
            logger.warning(
                "Webhook for unknown subscription %s carries no custom_data.user_id - cannot link it to a user",
                provider_subscription_id,
            )
            return
        user = session.get(User, user_id)
        if user is None:
            logger.warning("Webhook references unknown user_id %s", user_id)
            return
        subscription = Subscription(user_id=user_id, provider="paddle", provider_subscription_id=provider_subscription_id, plan=Plan.FREE.value)
        session.add(subscription)

    items = data.get("items") or []
    price_id = items[0]["price"]["id"] if items and items[0].get("price") else None
    plan_period = _plan_and_period_for_price_id(price_id) if price_id else None
    if plan_period:
        subscription.plan = plan_period[0].value

    paddle_status = (data.get("status") or "").lower()
    if paddle_status in _PADDLE_STATUS_MAP:
        subscription.status = _PADDLE_STATUS_MAP[paddle_status].value

    subscription.provider_customer_id = data.get("customer_id") or subscription.provider_customer_id
    current_period = data.get("current_billing_period") or {}
    subscription.current_period_start = _parse_paddle_datetime(current_period.get("starts_at")) or subscription.current_period_start
    subscription.current_period_end = _parse_paddle_datetime(current_period.get("ends_at")) or subscription.current_period_end
    subscription.cancel_at_period_end = bool(data.get("scheduled_change"))


def _handle_subscription_canceled(session: Session, data: dict) -> None:
    provider_subscription_id = data.get("id")
    subscription = session.execute(
        select(Subscription).where(Subscription.provider_subscription_id == provider_subscription_id)
    ).scalars().first()
    if subscription is None:
        return
    subscription.status = SubscriptionStatus.CANCELED.value
    user = session.get(User, subscription.user_id)
    if user:
        email_service.send_subscription_canceled_email(
            user.email, subscription.plan, str(subscription.current_period_end or "the end of the current period")
        )


def _handle_payment_failed(session: Session, data: dict) -> None:
    subscription_id = data.get("subscription_id")
    if not subscription_id:
        return
    subscription = session.execute(
        select(Subscription).where(Subscription.provider_subscription_id == subscription_id)
    ).scalars().first()
    if subscription is None:
        return
    subscription.status = SubscriptionStatus.PAST_DUE.value
    user = session.get(User, subscription.user_id)
    if user:
        email_service.send_payment_failed_email(user.email, subscription.plan)


def process_webhook_event(session: Session, event_id: str, event_type: str, data: dict, payload_hash: str) -> str:
    """Idempotently processes one Paddle webhook event. Returns the
    resulting BillingEvent.status ("processed" | "ignored" | "failed").
    Safe to call more than once with the same event_id - a duplicate is a
    guaranteed no-op (checked before any state-changing work happens)."""
    existing = session.get(BillingEvent, event_id)
    if existing is not None:
        logger.info("Webhook event %s already processed at %s - skipping", event_id, existing.processed_at)
        return existing.status

    status = BillingEventStatus.IGNORED.value
    try:
        if event_type in ("subscription.created", "subscription.activated", "subscription.updated", "subscription.resumed"):
            _upsert_subscription_from_event(session, data)
            status = BillingEventStatus.PROCESSED.value
        elif event_type == "subscription.canceled":
            _handle_subscription_canceled(session, data)
            status = BillingEventStatus.PROCESSED.value
        elif event_type == "subscription.paused":
            provider_subscription_id = data.get("id")
            subscription = session.execute(
                select(Subscription).where(Subscription.provider_subscription_id == provider_subscription_id)
            ).scalars().first()
            if subscription:
                subscription.status = SubscriptionStatus.PAUSED.value
            status = BillingEventStatus.PROCESSED.value
        elif event_type == "transaction.completed":
            # Subscription state itself is synced via subscription.* events;
            # a completed transaction doesn't need separate handling here,
            # but is recorded for the audit trail.
            status = BillingEventStatus.PROCESSED.value
        elif event_type == "transaction.payment_failed":
            _handle_payment_failed(session, data)
            status = BillingEventStatus.PROCESSED.value
        else:
            status = BillingEventStatus.IGNORED.value
        session.flush()
    except Exception:
        logger.exception("Failed to process Paddle webhook event %s (%s)", event_id, event_type)
        # Discard whatever partial subscription/user changes this attempt
        # made - we still want to record the event itself as failed (below),
        # just not with half-applied state alongside it.
        session.rollback()
        status = BillingEventStatus.FAILED.value

    session.add(
        BillingEvent(
            provider_event_id=event_id,
            event_type=event_type,
            processed_at=datetime.now(timezone.utc),
            payload_hash=payload_hash,
            status=status,
        )
    )
    session.flush()
    return status
