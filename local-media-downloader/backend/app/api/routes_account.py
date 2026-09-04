"""The logged-in user's own account: plan, subscription, usage, features."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.database.commercial_models import User
from app.models.commercial_enums import BillingPeriod, SubscriptionStatus
from app.models.commercial_schemas import AccountOut, SubscriptionOut, UserOut
from app.services.account_service import account_service
from app.services.entitlement_service import entitlement_service
from app.services.usage_service import usage_service

router = APIRouter(prefix="/api/account", tags=["account"])


def _billing_period_from_subscription(subscription) -> BillingPeriod | None:
    if subscription is None or not subscription.current_period_start or not subscription.current_period_end:
        return None
    span_days = (subscription.current_period_end - subscription.current_period_start).days
    return BillingPeriod.ANNUAL if span_days > 60 else BillingPeriod.MONTHLY


@router.get("", response_model=AccountOut)
async def get_account(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> AccountOut:
    plan, subscription = account_service.get_current_plan(db, user.id)
    latest_subscription = account_service.get_latest_subscription(db, user.id)
    usage = usage_service.get_usage_out(db, user, plan, subscription)
    features = entitlement_service.to_features_out(plan)

    display_subscription = subscription or latest_subscription
    subscription_out = SubscriptionOut(
        plan=plan,
        status=SubscriptionStatus(display_subscription.status) if display_subscription else SubscriptionStatus.NONE,
        billing_period=_billing_period_from_subscription(display_subscription),
        current_period_start=display_subscription.current_period_start if display_subscription else None,
        current_period_end=display_subscription.current_period_end if display_subscription else None,
        cancel_at_period_end=display_subscription.cancel_at_period_end if display_subscription else False,
    )

    return AccountOut(
        user=UserOut.model_validate(user, from_attributes=True),
        subscription=subscription_out,
        usage=usage,
        features=features,
    )
