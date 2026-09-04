"""Resolves "what plan is this user actually on right now" from their
subscription rows - the one place that answers that question, so auth,
billing, and the downloader all agree."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.commercial_models import Subscription, User
from app.models.commercial_enums import Plan, SubscriptionStatus

_ACTIVE_STATUSES = {
    SubscriptionStatus.ACTIVE.value,
    SubscriptionStatus.TRIALING.value,
    SubscriptionStatus.PAST_DUE.value,  # still entitled while payment is retried
}


class AccountService:
    def get_active_subscription(self, session: Session, user_id: str) -> Subscription | None:
        return session.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id, Subscription.status.in_(_ACTIVE_STATUSES))
            .order_by(Subscription.updated_at.desc())
        ).scalars().first()

    def get_current_plan(self, session: Session, user_id: str) -> tuple[Plan, Subscription | None]:
        sub = self.get_active_subscription(session, user_id)
        if sub is None:
            return Plan.FREE, None
        try:
            return Plan(sub.plan), sub
        except ValueError:
            return Plan.FREE, sub

    def get_latest_subscription(self, session: Session, user_id: str) -> Subscription | None:
        """Most recent subscription row regardless of status - used for
        display (e.g. "canceled, active until ...") even when it's no longer
        entitling the user to paid features."""
        return session.execute(
            select(Subscription).where(Subscription.user_id == user_id).order_by(Subscription.updated_at.desc())
        ).scalars().first()


account_service = AccountService()
