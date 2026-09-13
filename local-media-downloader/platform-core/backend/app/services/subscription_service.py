"""Provider-neutral subscription lifecycle (mission-brief Phase 8), driven
by normalized webhook events (`webhook_service.py` is the only caller in
this codebase, but nothing here imports it - the dependency runs the
other way, keeping this module testable with a hand-built
`NormalizedEvent`/`NormalizedSubscription` and no webhook machinery at
all).

Every subscription upsert also keeps the legacy `Entitlement` single-row
cache in sync (mission-brief Phase 46: existing Loady OIDC integration
and every other current caller of
`entitlement_service.get_active_entitlement` must keep working
unmodified) and enqueues an `entitlement.changed` outbox event
transactionally in the same session (Phase 43)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Plan, Subscription, SubscriptionItem
from app.models.enums import AuditAction, EntitlementSource
from app.services import audit_service, entitlement_service, outbox_service


def get_subscription_by_ref(session: Session, provider: str, provider_subscription_ref: str) -> Subscription | None:
    return session.execute(
        select(Subscription).where(
            Subscription.provider == provider, Subscription.provider_subscription_ref == provider_subscription_ref
        )
    ).scalars().first()


def upsert_subscription(
    session: Session,
    *,
    user_id: str,
    product_id: str,
    plan: Plan,
    provider: str,
    provider_customer_ref: str,
    provider_subscription_ref: str,
    status: str,
    current_period_start: datetime | None,
    current_period_end: datetime | None,
    cancel_at_period_end: bool = False,
) -> Subscription:
    existing = get_subscription_by_ref(session, provider, provider_subscription_ref)
    is_new = existing is None

    if existing is None:
        existing = Subscription(
            user_id=user_id, product_id=product_id, provider=provider,
            provider_customer_ref=provider_customer_ref, provider_subscription_ref=provider_subscription_ref,
            status=status, current_period_start=current_period_start, current_period_end=current_period_end,
            cancel_at_period_end=cancel_at_period_end,
        )
        session.add(existing)
        session.flush()
        session.add(SubscriptionItem(subscription_id=existing.id, plan_id=plan.id, quantity=1))
    else:
        existing.status = status
        existing.current_period_start = current_period_start
        existing.current_period_end = current_period_end
        existing.cancel_at_period_end = cancel_at_period_end
        item = session.execute(
            select(SubscriptionItem).where(SubscriptionItem.subscription_id == existing.id)
        ).scalars().first()
        if item is not None and item.plan_id != plan.id:
            item.plan_id = plan.id  # a plan change (upgrade/downgrade) event
    session.flush()

    _sync_legacy_entitlement(session, existing, plan, status)

    audit_service.record(
        session, None, AuditAction.SUBSCRIPTION_CREATED if is_new else AuditAction.SUBSCRIPTION_CHANGED,
        "subscription", existing.id, product_id,
        after_state={"status": status, "plan_id": plan.id, "provider": provider},
    )
    outbox_service.enqueue(session, "entitlement.changed", product_id, {"user_id": user_id, "product_id": product_id})
    return existing


def cancel_subscription(session: Session, subscription: Subscription, at_period_end: bool = True) -> Subscription:
    from datetime import timezone as _tz
    subscription.cancel_at_period_end = at_period_end
    if not at_period_end:
        subscription.status = "canceled"
        subscription.canceled_at = datetime.now(_tz.utc)
    session.flush()
    audit_service.record(
        session, None, AuditAction.SUBSCRIPTION_CANCELED, "subscription", subscription.id, subscription.product_id,
        after_state={"cancel_at_period_end": at_period_end, "status": subscription.status},
    )
    outbox_service.enqueue(
        session, "entitlement.changed", subscription.product_id,
        {"user_id": subscription.user_id, "product_id": subscription.product_id},
    )
    return subscription


_ACTIVE_LEGACY_STATUSES = {"trialing", "active", "past_due"}


def _sync_legacy_entitlement(session: Session, subscription: Subscription, plan: Plan, status: str) -> None:
    """Best-effort mirror onto the V1 `Entitlement` row so a caller that
    has not been updated to use `capability_service.resolve_effective_
    entitlements` still sees the correct paid/not-paid answer. Never
    downgrades a still-more-authoritative row here - if the legacy row is
    already `paddle`-sourced for a *different* still-current subscription
    this call is not about, this function only ever touches the row for
    the (user, product) pair `subscription` itself belongs to, so there is
    no cross-subscription clobbering."""
    from app.database.models import User

    user = session.get(User, subscription.user_id)
    if user is None:
        return
    if status in _ACTIVE_LEGACY_STATUSES:
        entitlement_service.grant_or_change(
            session, user, user, subscription.product_id, plan.slug, EntitlementSource.PADDLE,
            subscription.current_period_end, reason=f"subscription:{subscription.provider_subscription_ref}",
        )
    elif status in ("canceled", "expired", "paused"):
        # Access-through-period-end is a read-time decision
        # (`capability_service._subscription_contributes`) - the legacy
        # cache is only cleared once the subscription is truly over.
        if subscription.current_period_end is None or subscription.current_period_end <= datetime.now(subscription.current_period_end.tzinfo):
            entitlement_service.revoke(session, user, user, subscription.product_id, reason="subscription_ended")
