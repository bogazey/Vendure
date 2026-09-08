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

from typing import Literal

from fastapi import APIRouter, Depends, Request, HTTPException, Query, Path
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.config.commercial_settings import get_commercial_settings
from app.config.logging_config import get_logger
from app.database.commercial_models import User
from app.models.commercial_schemas import CheckoutRequest, CheckoutResponse
from app.services import paddle_service
from app.services.account_service import account_service
from app.services.paddle_client import paddle_client
from app.services.rate_limit_service import billing_limiter
from app.utils.exceptions import BillingError, InvalidWebhookSignatureError, RateLimitedError

router = APIRouter(prefix="/api/billing", tags=["billing"])
logger = get_logger("billing_api")


def _enforce_billing_limit(user: User) -> None:
    if not billing_limiter.allow(f"user:{user.id}", max_events=30, window_seconds=300):
        raise RateLimitedError("Too many billing requests. Please wait a few minutes and try again.")


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    payload: CheckoutRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> CheckoutResponse:
    _enforce_billing_limit(user)
    if account_service.get_active_subscription(db, user.id):
        raise HTTPException(409, "Manage your existing subscription from Billing.")
    return paddle_service.build_checkout(user, payload.plan, payload.billing_period)


def _owned_subscription(db, user):
    subscription = (account_service.get_active_subscription(db, user.id)
                    or account_service.get_latest_subscription(db, user.id))
    if not subscription or subscription.provider != "paddle" or not subscription.provider_subscription_id:
        raise HTTPException(404, "No billing subscription found.")
    return subscription


def _live_subscription(db, user):
    subscription = _owned_subscription(db, user)
    data = paddle_client.get_subscription(subscription.provider_subscription_id).get("data") or {}
    if data.get("id") != subscription.provider_subscription_id or data.get("customer_id") != subscription.provider_customer_id:
        raise HTTPException(409, "Subscription could not be verified.")
    return subscription, data


@router.post("/subscription/{action}")
def manage_subscription(action: Literal["cancel", "resume", "change-plan"],
                        payload: CheckoutRequest | None = None,
                        user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _enforce_billing_limit(user)
    subscription, live = _live_subscription(db, user)
    if live.get("status") not in ("active", "trialing"):
        raise HTTPException(409, "Subscription cannot be changed in its current state.")
    scheduled = (live.get("scheduled_change") or {}).get("action")
    sid = subscription.provider_subscription_id
    if action == "cancel":
        if scheduled != "cancel":
            if scheduled:
                raise HTTPException(409, "Another change is already scheduled.")
            paddle_client.cancel_subscription(sid)
    elif action == "resume":
        if scheduled != "cancel":
            raise HTTPException(409, "Subscription is not scheduled to cancel.")
        # Removing a scheduled cancellation is NOT Paddle's paused-subscription resume operation.
        paddle_client.update_subscription(sid, {"scheduled_change": None})
    else:
        if payload is None or scheduled:
            raise HTTPException(409, "Choose a plan and remove any scheduled change first.")
        price = paddle_service._price_id_for(payload.plan, payload.billing_period)
        if not price:
            raise BillingError("This plan is not configured.")
        items = live.get("items") or []
        if len(items) != 1 or items[0].get("quantity", 1) != 1 or not paddle_service._plan_and_period_for_price_id((items[0].get("price") or {}).get("id")):
            raise HTTPException(409, "This subscription requires support to change its plan.")
        if items[0]["price"]["id"] != price:
            paddle_client.update_subscription(sid, {
                "items": [{"price_id": price, "quantity": 1}],
                "proration_billing_mode": "prorated_immediately",
                "on_payment_failure": "prevent_change",
            })
    # Never write the subscription here. Only signed webhooks change entitlements.
    return {"status": "pending"}


@router.post("/payment-method")
def update_payment_method(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _enforce_billing_limit(user)
    subscription, live = _live_subscription(db, user)
    settings = get_commercial_settings()
    if live.get("collection_mode") != "automatic" or live.get("status") not in ("active", "past_due"):
        raise HTTPException(409, "Payment method updates are unavailable for this subscription.")
    if not settings.paddle_client_token:
        raise BillingError("Payment checkout is unavailable.")
    transaction = paddle_client.payment_transaction(subscription.provider_subscription_id).get("data") or {}
    if not transaction.get("id"):
        raise BillingError("Payment checkout is unavailable.")
    return {"transaction_id": transaction["id"], "client_token": settings.paddle_client_token,
            "environment": settings.paddle_env}


@router.get("/history")
def payment_history(after: str | None = Query(None, pattern=r"^txn_[a-z0-9]{26}$"),
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _enforce_billing_limit(user)
    subscription = _owned_subscription(db, user)
    result = paddle_client.list_transactions(subscription.provider_subscription_id, after)
    rows = []
    for row in result.get("data") or []:
        if row.get("subscription_id") != subscription.provider_subscription_id:
            continue
        total = ((row.get("details") or {}).get("totals") or {}).get("grand_total", "0")
        rows.append({"id": row["id"], "date": row.get("created_at"), "status": row.get("status"),
                     "total": total, "currency": row.get("currency_code"),
                     "invoice_available": total != "0" and (row.get("status") == "completed" or
                         (row.get("status") == "billed" and row.get("collection_mode") == "manual"))})
    more = ((result.get("meta") or {}).get("pagination") or {}).get("has_more", False)
    return {"items": rows, "next": rows[-1]["id"] if more and rows else None}


@router.get("/history/{transaction_id}/invoice")
def transaction_invoice(transaction_id: str = Path(pattern=r"^txn_[a-z0-9]{26}$"),
                        user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _enforce_billing_limit(user)
    subscription = _owned_subscription(db, user)
    transaction = paddle_client.get_transaction(transaction_id).get("data") or {}
    if transaction.get("subscription_id") != subscription.provider_subscription_id:
        raise HTTPException(404, "Invoice not found.")
    url = (paddle_client.invoice(transaction_id).get("data") or {}).get("url")
    if not url or not url.startswith("https://"):
        raise BillingError("Invoice is unavailable.")
    return {"url": url}


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
