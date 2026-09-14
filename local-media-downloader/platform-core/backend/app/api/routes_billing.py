"""Billing endpoints (mission-brief Phases 9-11):

- `POST /api/v1/billing/webhooks/{provider_name}` - inbound, provider-signed,
  idempotent (see `webhook_service.py`). Deliberately its own generous rate
  limiter (`billing_webhook_limiter`), never the interactive
  `admin_mutation_limiter` - a legitimate provider retrying a delivery must
  never be throttled the way a suspicious admin-session burst would be.
- `POST /api/v1/billing/checkout` - creates a checkout session through
  whichever provider is configured. Against the real `paddle` provider this
  always returns 501 in this mission (no live Paddle call is ever made -
  mission-brief Phase 9/56); it is fully exercised against `provider=fake`
  for local testing.
- `GET /api/v1/billing/subscriptions/me` - the account-portal-facing read
  of the caller's own subscriptions (never another user's).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.database.models import Subscription, User
from app.services import billing, entitlement_service, webhook_service
from app.services.billing.base import BillingProviderNotConfiguredError
from app.services.rate_limit_service import billing_webhook_limiter
from app.utils.exceptions import NotFoundError, ProviderNotConfiguredError, RateLimitedError

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])


@router.post("/webhooks/{provider_name}")
async def receive_webhook(provider_name: str, request: Request, db: Session = Depends(get_db)) -> dict:
    if not billing_webhook_limiter.allow(provider_name, max_events=120, window_seconds=60):
        raise RateLimitedError("Too many webhook deliveries for this provider in a short period.")
    try:
        provider = billing.get_billing_provider(provider_name)
    except ValueError:
        raise NotFoundError(f"Unknown billing provider '{provider_name}'.")

    raw_body = await request.body()
    headers = {key.lower(): value for key, value in request.headers.items()}
    journal = webhook_service.receive_webhook(db, provider, raw_body, headers)
    return {"id": journal.id, "status": journal.status, "event_type": journal.event_type}


@router.post("/checkout")
async def create_checkout(
    payload: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    provider_name = payload.get("provider", "paddle")
    try:
        provider = billing.get_billing_provider(provider_name)
    except ValueError:
        raise NotFoundError(f"Unknown billing provider '{provider_name}'.")

    # Validate the (product_id, plan_slug) pair BEFORE ever calling the
    # provider - a real provider's `create_checkout` would resolve the
    # plan to a processor-side price and charge that amount server-side
    # (never trusting a client-supplied amount), so this plan must
    # already exist in Platform Core's own registry, not merely be
    # whatever string the caller sent (security review finding: an
    # unvalidated product_id/plan_slug was previously passed straight
    # through to the provider).
    plan = entitlement_service.get_plan(db, payload["product_id"], payload["plan_slug"])

    try:
        checkout = provider.create_checkout(
            user_id=user.id,
            product_id=payload["product_id"],
            plan_id=plan.id,
            success_url=payload.get("success_url", ""),
        )
    except BillingProviderNotConfiguredError as exc:
        raise ProviderNotConfiguredError(str(exc))
    return {"url": checkout.url, "provider_reference": checkout.provider_reference}


@router.get("/subscriptions/me")
async def my_subscriptions(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict]:
    subscriptions = db.execute(select(Subscription).where(Subscription.user_id == user.id)).scalars().all()
    return [
        {
            "id": s.id, "product_id": s.product_id, "provider": s.provider, "status": s.status,
            "current_period_start": s.current_period_start.isoformat() if s.current_period_start else None,
            "current_period_end": s.current_period_end.isoformat() if s.current_period_end else None,
            "cancel_at_period_end": s.cancel_at_period_end,
        }
        for s in subscriptions
    ]
