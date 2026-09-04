"""Checkout initiation and the Paddle webhook endpoint.

Checkout: the backend only ever hands the frontend a price_id + the public
client token - Paddle.js runs the actual checkout UI client-side. The
backend never creates a "checkout session" itself (Paddle Billing doesn't
require that) and never sees card details.

Webhook: POST /api/billing/paddle/webhook is the ONLY source of truth for
subscription state. A successful frontend checkout redirect is never trusted
on its own - the account page will simply keep showing the old plan until
the webhook lands and updates the database.
"""
from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.config.commercial_settings import get_commercial_settings
from app.config.logging_config import get_logger
from app.database.commercial_models import User
from app.models.commercial_schemas import BillingPortalResponse, CheckoutRequest, CheckoutResponse
from app.services import paddle_service
from app.services.account_service import account_service
from app.services.paddle_client import paddle_client
from app.utils.exceptions import BillingError, InvalidWebhookSignatureError

router = APIRouter(prefix="/api/billing", tags=["billing"])
logger = get_logger("billing_api")


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    payload: CheckoutRequest, user: User = Depends(get_current_user)
) -> CheckoutResponse:
    return paddle_service.build_checkout(user, payload.plan, payload.billing_period)


@router.post("/portal", response_model=BillingPortalResponse)
async def create_portal_session(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> BillingPortalResponse:
    """Hands back a Paddle-hosted customer-portal URL for the account page's
    "Manage billing" button - never a custom card-management UI of our own."""
    subscription = account_service.get_latest_subscription(db, user.id)
    if subscription is None or not subscription.provider_customer_id:
        return BillingPortalResponse(url=None)
    try:
        session = paddle_client.create_customer_portal_session(subscription.provider_customer_id)
    except BillingError:
        logger.warning("Could not create Paddle portal session for user %s", user.id)
        return BillingPortalResponse(url=None)
    url = (session.get("data") or {}).get("urls", {}).get("general", {}).get("overview")
    return BillingPortalResponse(url=url)


@router.post("/paddle/webhook", status_code=204, response_model=None)
async def paddle_webhook(request: Request, db: Session = Depends(get_db)) -> None:
    settings = get_commercial_settings()
    raw_body = await request.body()
    signature = request.headers.get("Paddle-Signature")

    if not paddle_service.verify_webhook_signature(raw_body, signature, settings.paddle_webhook_secret):
        # Never log the signature header or the webhook secret - only that
        # verification failed.
        logger.warning("Rejected Paddle webhook: invalid signature")
        raise InvalidWebhookSignatureError("Invalid webhook signature.")

    try:
        payload = json.loads(raw_body)
    except ValueError:
        logger.warning("Rejected Paddle webhook: body is not valid JSON")
        raise InvalidWebhookSignatureError("Malformed webhook payload.")

    event_id = payload.get("event_id") or payload.get("id")
    event_type = payload.get("event_type", "unknown")
    data = payload.get("data") or {}

    if not event_id:
        logger.warning("Rejected Paddle webhook: missing event id")
        raise InvalidWebhookSignatureError("Missing event id.")

    payload_hash = hashlib.sha256(raw_body).hexdigest()
    status = paddle_service.process_webhook_event(db, event_id, event_type, data, payload_hash)
    logger.info("Processed Paddle webhook %s (%s) -> %s", event_id, event_type, status)
