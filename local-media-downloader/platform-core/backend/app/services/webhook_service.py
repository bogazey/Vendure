"""Idempotent inbound billing-webhook processing (mission-brief Phase 10)
and the payment ledger (Phase 11).

Idempotency is enforced at the DB level, not just in application logic:
`BillingWebhookEvent(provider, provider_event_id)` has a UNIQUE
constraint (`database/models.py`), so two concurrent deliveries of the
same event race on the same INSERT and only one wins - the loser's
`IntegrityError` is caught here and treated as "already recorded," not an
error, closing the TOCTOU window a plain "SELECT then INSERT" check would
leave open.

Receiving the same event twice therefore can, at most, re-run
`_apply_event` once (the intentional replay path, `replay_failed_event`) -
never twice from two concurrent live deliveries, and
`subscription_service.upsert_subscription` / `_apply_transaction_event`
are themselves idempotent on their own unique keys
(`(provider, provider_subscription_ref)`, `(provider, provider_reference)`)
as a second layer of defense.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database.models import BillingWebhookEvent, PaymentRecord, Plan, SubscriptionItem
from app.models.enums import AuditAction, PaymentStatus
from app.services import audit_service, product_service, subscription_service
from app.services.billing.base import BillingProvider, NormalizedEvent
from app.utils.exceptions import InvalidWebhookSignatureError, NotFoundError

_SUBSCRIPTION_EVENT_TYPES = {
    "subscription.created", "subscription.activated", "subscription.updated",
    "subscription.canceled", "subscription.paused", "subscription.resumed",
}
_TRANSACTION_EVENT_TYPES = {"transaction.completed"}


def receive_webhook(
    session: Session,
    provider: BillingProvider,
    raw_body: bytes,
    headers: dict[str, str],
) -> BillingWebhookEvent:
    """Verify signature, then persist-and-process exactly once. Returns
    the journal row regardless of whether this call was the one that
    first recorded it (mission-brief: "receiving the same provider event
    multiple times must not duplicate subscriptions/payments/
    entitlements")."""
    if not provider.verify_webhook(raw_body, headers):
        raise InvalidWebhookSignatureError("Webhook signature verification failed.")

    event = provider.normalize_event(raw_body)

    journal = BillingWebhookEvent(
        provider=provider.name, provider_event_id=event.provider_event_id, event_type=event.event_type,
        payload=event.raw, status="pending",
    )
    session.add(journal)
    try:
        session.flush()
    except IntegrityError:
        # Already recorded by a concurrent/prior delivery - fetch and
        # return the existing row rather than re-processing.
        session.rollback()
        existing = session.execute(
            select(BillingWebhookEvent).where(
                BillingWebhookEvent.provider == provider.name,
                BillingWebhookEvent.provider_event_id == event.provider_event_id,
            )
        ).scalars().first()
        if existing is not None:
            return existing
        raise

    audit_service.record(
        session, None, AuditAction.WEBHOOK_RECEIVED, "billing_webhook_event", journal.id,
        after_state={"event_type": event.event_type, "provider": provider.name},
    )

    _apply_event(session, provider.name, journal, event)
    return journal


def _apply_event(session: Session, provider_name: str, journal: BillingWebhookEvent, event: NormalizedEvent) -> None:
    try:
        if event.event_type in _SUBSCRIPTION_EVENT_TYPES:
            _apply_subscription_event(session, provider_name, event)
        elif event.event_type in _TRANSACTION_EVENT_TYPES:
            _apply_transaction_event(session, provider_name, event)
        # Any other event type is stored (for audit/idempotency
        # bookkeeping) but otherwise ignored - mirrors Loady's own
        # `paddle_service._HANDLED_EVENT_TYPES` precedent.
        journal.status = "processed"
        journal.processed_at = datetime.now(timezone.utc)
        session.flush()
        audit_service.record(session, None, AuditAction.WEBHOOK_PROCESSED, "billing_webhook_event", journal.id)
    except Exception as exc:  # noqa: BLE001 - a bad/unresolvable event must not crash the endpoint
        journal.status = "failed"
        journal.failure_reason = f"{type(exc).__name__}: {exc}"
        journal.retry_count += 1
        session.flush()


def _resolve_identity(event: NormalizedEvent) -> tuple[str, str, str] | None:
    custom_data = event.custom_data or {}
    user_id, product_id, plan_slug = custom_data.get("user_id"), custom_data.get("product_id"), custom_data.get("plan_slug")
    if user_id and product_id and plan_slug:
        return user_id, product_id, plan_slug
    return None


def _apply_subscription_event(session: Session, provider_name: str, event: NormalizedEvent) -> None:
    if event.provider_subscription_ref is None:
        raise NotFoundError("Subscription event carried no subscription reference.")

    existing = subscription_service.get_subscription_by_ref(session, provider_name, event.provider_subscription_ref)

    if existing is not None:
        # Re-derive the current plan from the existing subscription's item
        # rather than requiring custom_data on every follow-up event -
        # only the very first webhook for a subscription needs it.
        item = session.execute(
            select(SubscriptionItem).where(SubscriptionItem.subscription_id == existing.id)
        ).scalars().first()
        plan = session.get(Plan, item.plan_id) if item else None
        if plan is None:
            raise NotFoundError("Existing subscription has no resolvable plan.")
        subscription_service.upsert_subscription(
            session,
            user_id=existing.user_id, product_id=existing.product_id, plan=plan,
            provider=existing.provider, provider_customer_ref=event.provider_customer_ref or existing.provider_customer_ref,
            provider_subscription_ref=event.provider_subscription_ref,
            status=event.status or existing.status,
            current_period_start=existing.current_period_start, current_period_end=existing.current_period_end,
            cancel_at_period_end=existing.cancel_at_period_end,
        )
        return

    identity = _resolve_identity(event)
    if identity is None:
        raise NotFoundError(
            "First webhook for an unknown subscription carried no custom_data identity - cannot resolve "
            "which user/product/plan this belongs to."
        )
    user_id, product_id, plan_slug = identity
    product_service.get_product(session, product_id)
    plan = session.execute(
        select(Plan).where(Plan.product_id == product_id, Plan.slug == plan_slug)
    ).scalars().first()
    if plan is None:
        raise NotFoundError(f"Product '{product_id}' has no plan '{plan_slug}'.")

    subscription_service.upsert_subscription(
        session,
        user_id=user_id, product_id=product_id, plan=plan,
        provider=provider_name,
        provider_customer_ref=event.provider_customer_ref or "",
        provider_subscription_ref=event.provider_subscription_ref,
        status=event.status or "active",
        current_period_start=None, current_period_end=None,
    )


def _apply_transaction_event(session: Session, provider_name: str, event: NormalizedEvent) -> None:
    """A `transaction.completed` event is what may create a `PaymentRecord`
    (mission-brief Phase 11) - never a subscription event alone, and
    never a gift/free/internal source (those never reach this function at
    all, since nothing in `gift_service`/`entitlement_service` calls into
    billing)."""
    if event.amount_cents is None or event.currency is None:
        raise NotFoundError("Transaction event carried no amount/currency - refusing to fabricate a payment record.")

    subscription = None
    if event.provider_subscription_ref:
        subscription = subscription_service.get_subscription_by_ref(session, provider_name, event.provider_subscription_ref)

    existing = session.execute(
        select(PaymentRecord).where(
            PaymentRecord.provider == provider_name, PaymentRecord.provider_reference == event.provider_event_id
        )
    ).scalars().first()
    if existing is not None:
        return  # idempotent: already recorded

    custom_data = event.custom_data or {}
    user_id = subscription.user_id if subscription else custom_data.get("user_id", "")
    product_id = subscription.product_id if subscription else custom_data.get("product_id", "")
    if not user_id or not product_id:
        raise NotFoundError("Could not resolve which user/product this payment belongs to.")

    record = PaymentRecord(
        user_id=user_id,
        product_id=product_id,
        provider=provider_name,
        provider_reference=event.provider_event_id,
        amount_cents=event.amount_cents,
        currency=event.currency,
        status=PaymentStatus.COMPLETED.value,
        subscription_id=subscription.id if subscription else None,
        occurred_at=event.occurred_at,
    )
    session.add(record)
    session.flush()


def replay_failed_event(session: Session, provider: BillingProvider, webhook_event_id: str) -> BillingWebhookEvent:
    """Manual/administrative replay of a previously-failed webhook
    (mission-brief Phase 10: "build replay support for failed webhook
    processing... replay must not double-create revenue"). Re-processing
    a `transaction.completed` event is safe because
    `_apply_transaction_event` re-checks `(provider, provider_reference)`
    before inserting; re-processing a subscription event is safe because
    `subscription_service.upsert_subscription` is an upsert keyed on
    `(provider, provider_subscription_ref)`."""
    journal = session.get(BillingWebhookEvent, webhook_event_id)
    if journal is None:
        raise NotFoundError("Webhook event not found.")
    if journal.provider != provider.name:
        raise NotFoundError("Provider mismatch for this webhook event.")

    # Re-derive the normalized event the same way the provider would on
    # first delivery, by re-normalizing the stored raw payload - never
    # trusting a hand-reconstructed shape.
    event = provider.normalize_event(json.dumps(journal.payload).encode("utf-8"))

    audit_service.record(session, None, AuditAction.WEBHOOK_REPLAYED, "billing_webhook_event", journal.id)
    _apply_event(session, provider.name, journal, event)
    return journal
