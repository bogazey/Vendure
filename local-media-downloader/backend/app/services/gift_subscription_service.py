"""Admin-managed Gifted Subscriptions: a way for an admin to manually give a
user Pro or Creator access with no customer payment involved at all.

CRITICAL SAFETY RULE (see docs/ANALYTICS.md and COMMERCIAL_ARCHITECTURE.md):
a real, active Paddle subscription always takes precedence and blocks every
function here - see _reject_if_paid. Nothing in this module ever imports or
calls paddle_client/paddle_service; a gifted grant never creates a Paddle
subscription, never charges a card, and is never counted as revenue (see
analytics_service.get_overview/get_revenue, which filter on
Subscription.provider explicitly rather than inferring it).

A gifted Pro/Creator subscription reuses the exact same entitlement path a
real Paddle subscription does (Subscription.status == "active" is all
account_service.get_current_plan/entitlement_service/download_gate_service
look at) - the only difference is `provider` and the absence of any
provider_subscription_id/period dates, which in turn makes
usage_service.get_or_create_current_period fall through to its existing
"no confirmed billing period yet" 30-day rolling window, giving a gifted
subscription the same recurring monthly credit refill a real one gets, with
no special-casing needed there either.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.commercial_models import Subscription, UsagePeriod, User
from app.models.commercial_enums import AdminActionType, AnalyticsEventType, Plan, SubscriptionProvider, SubscriptionStatus
from app.services import analytics_service
from app.services.account_service import account_service
from app.services.admin_audit_service import admin_audit_service
from app.services.plan_policy import get_policy
from app.utils.exceptions import PaidSubscriptionActiveError

_PAID_BLOCK_MESSAGE = "This user has an active paid Paddle subscription. Manage billing through the normal subscription workflow."


def _reject_if_paid(active: Subscription | None) -> None:
    if active is not None and active.provider == SubscriptionProvider.PADDLE.value:
        raise PaidSubscriptionActiveError(_PAID_BLOCK_MESSAGE)


def _sync_gifted_credits_on_plan_change(session: Session, user_id: str, old_plan: str, new_plan: str) -> None:
    """Mirrors paddle_service._sync_usage_period_credits_for_plan_change's
    intent (preserve used credits and any admin bonus, adjust only by the
    plan delta) but keyed on "the user's current non-expired period" rather
    than subscription.current_period_start/end, since a gifted subscription
    has no fixed billing-cycle dates at all - see the module docstring."""
    if old_plan == new_plan or old_plan == Plan.FREE.value or new_plan == Plan.FREE.value:
        return
    now = datetime.now(timezone.utc)
    period = session.execute(
        select(UsagePeriod)
        .where(UsagePeriod.user_id == user_id, UsagePeriod.period_end > now)
        .order_by(UsagePeriod.period_start.desc())
    ).scalars().first()
    if period is None:
        return
    old_credits = get_policy(Plan(old_plan)).monthly_credits or 0
    new_credits = get_policy(Plan(new_plan)).monthly_credits or 0
    period.credits_included = max(0, period.credits_included + (new_credits - old_credits))


def grant_or_change(session: Session, admin: User, target: User, new_plan: Plan, reason: str | None) -> Subscription:
    """Grants a fresh gifted Pro/Creator subscription, or changes an
    existing gifted one between Pro and Creator. Raises
    PaidSubscriptionActiveError and does nothing if the user currently has
    an active Paddle subscription. `new_plan` must be PRO or CREATOR - see
    revoke() for the Free/no-subscription case."""
    if new_plan == Plan.FREE:
        raise ValueError("grant_or_change requires plan=pro or plan=creator; use revoke() for Free.")

    active = account_service.get_active_subscription(session, target.id)
    _reject_if_paid(active)
    # _reject_if_paid already raised for provider == "paddle", so any
    # `active` reaching this point is necessarily provider == "gifted".
    is_new_grant = active is None
    old_plan = active.plan if active is not None else Plan.FREE.value
    old_source = active.provider if active is not None else "none"

    if active is not None:
        subscription = active
        subscription.plan = new_plan.value
        subscription.status = SubscriptionStatus.ACTIVE.value
    else:
        subscription = Subscription(
            user_id=target.id,
            provider=SubscriptionProvider.GIFTED.value,
            plan=new_plan.value,
            status=SubscriptionStatus.ACTIVE.value,
            provider_customer_id=None,
            provider_subscription_id=None,
            current_period_start=None,
            current_period_end=None,
            cancel_at_period_end=False,
        )
        session.add(subscription)
    # Recorded on every grant/change, gifted or re-gifted, so the row
    # always reflects who most recently touched it - the append-only
    # AdminActionLog entry below is the full history, this is just current
    # state (exactly like Paddle's own fields on this same row).
    subscription.granted_by_admin_id = admin.id
    subscription.granted_reason = reason
    session.flush()

    _sync_gifted_credits_on_plan_change(session, target.id, old_plan, new_plan.value)

    action = AdminActionType.GIFT_SUBSCRIPTION_GRANTED if is_new_grant else AdminActionType.GIFT_SUBSCRIPTION_CHANGED
    admin_audit_service.record(
        session, admin, action, target.id,
        {
            "target_email": target.email,
            "previous_plan": old_plan,
            "new_plan": new_plan.value,
            "previous_source": old_source,
            "new_source": SubscriptionProvider.GIFTED.value,
            "reason": reason,
        },
    )
    event_type = (
        AnalyticsEventType.GIFTED_SUBSCRIPTION_GRANTED if is_new_grant else AnalyticsEventType.GIFTED_SUBSCRIPTION_CHANGED
    )
    analytics_service.record_event(
        session, event_type, user_id=target.id, plan=new_plan.value, from_plan=old_plan
    )
    return subscription


def revoke(session: Session, admin: User, target: User, reason: str | None) -> Subscription | None:
    """Revokes an active gifted subscription back to Free. A no-op (returns
    None, writes nothing) if the user has no active subscription at all -
    they are already Free, so there is nothing to revoke and no audit entry
    is warranted. Raises PaidSubscriptionActiveError if the active
    subscription is a real Paddle one."""
    active = account_service.get_active_subscription(session, target.id)
    if active is None:
        return None
    _reject_if_paid(active)

    old_plan = active.plan
    active.status = SubscriptionStatus.CANCELED.value
    active.granted_by_admin_id = admin.id
    active.granted_reason = reason
    session.flush()

    admin_audit_service.record(
        session, admin, AdminActionType.GIFT_SUBSCRIPTION_REVOKED, target.id,
        {
            "target_email": target.email,
            "previous_plan": old_plan,
            "new_plan": Plan.FREE.value,
            "previous_source": SubscriptionProvider.GIFTED.value,
            "new_source": "none",
            "reason": reason,
        },
    )
    analytics_service.record_event(
        session, AnalyticsEventType.GIFTED_SUBSCRIPTION_REVOKED,
        user_id=target.id, plan=Plan.FREE.value, from_plan=old_plan,
    )
    return active
