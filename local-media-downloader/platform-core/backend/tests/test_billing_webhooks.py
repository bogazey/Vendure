"""Mission 6 (Phases 8-11): webhook signature verification, idempotent
processing, subscription upsert, and the payment ledger - using
`FakeBillingProvider` so nothing here ever calls a real network/Paddle
endpoint."""
from __future__ import annotations

import json
import uuid

from sqlalchemy import select

from app.database.models import BillingWebhookEvent, PaymentRecord, Product, Subscription, User
from app.models.enums import EntitlementSource
from app.services import entitlement_service, webhook_service
from app.services.billing.fake_provider import FakeBillingProvider
from app.utils.exceptions import InvalidWebhookSignatureError


def _product(db_session, product_id: str):
    if db_session.get(Product, product_id) is None:
        db_session.add(Product(id=product_id, name=product_id, domain=f"{product_id}.example", status="live"))
        db_session.flush()
    return db_session.get(Product, product_id)


def _subscription_event(event_id, user_id, product_id, plan_slug, sub_ref, status="active", amount_cents=None, currency=None):
    payload = {
        "event_id": event_id, "event_type": "subscription.created", "occurred_at": "2026-01-01T00:00:00+00:00",
        "subscription_ref": sub_ref, "customer_ref": f"cust_{user_id}", "status": status,
        "custom_data": {"user_id": user_id, "product_id": product_id, "plan_slug": plan_slug},
    }
    if amount_cents is not None:
        payload["amount_cents"] = amount_cents
        payload["currency"] = currency
    return json.dumps(payload).encode("utf-8")


def _transaction_event(event_id, sub_ref, amount_cents, currency, user_id=None, product_id=None):
    payload = {
        "event_id": event_id, "event_type": "transaction.completed", "occurred_at": "2026-01-02T00:00:00+00:00",
        "subscription_ref": sub_ref, "amount_cents": amount_cents, "currency": currency,
    }
    if user_id:
        payload["custom_data"] = {"user_id": user_id, "product_id": product_id}
    return json.dumps(payload).encode("utf-8")


def test_invalid_signature_rejected(db_session, client):

    user = User(email="whsig@example.com", password_hash="x", email_verified=True)
    db_session.add(user)
    db_session.commit()
    provider = FakeBillingProvider()
    body = _subscription_event(str(uuid.uuid4()), user.id, "wh-product-a", "free", "sub_bad")
    try:
        webhook_service.receive_webhook(db_session, provider, body, headers={})
        assert False, "expected InvalidWebhookSignatureError"
    except InvalidWebhookSignatureError:
        pass
    db_session.rollback()


def test_first_webhook_creates_subscription_and_syncs_legacy_entitlement(db_session):

    user = User(email="wh1@example.com", password_hash="x", email_verified=True)
    db_session.add(user)
    product = _product(db_session, "wh-product-b")
    entitlement_service.get_or_create_plan(db_session, product.id, "pro", "Pro")
    db_session.commit()

    provider = FakeBillingProvider()
    body = _subscription_event(str(uuid.uuid4()), user.id, product.id, "pro", "sub_wh1")
    headers = {"fake-signature": provider.sign(body)}
    journal = webhook_service.receive_webhook(db_session, provider, body, headers)
    db_session.commit()

    assert journal.status == "processed"
    subscription = db_session.execute(
        select(Subscription).where(Subscription.provider_subscription_ref == "sub_wh1")
    ).scalars().first()
    assert subscription is not None
    assert subscription.status == "active"

    legacy = entitlement_service.get_active_entitlement(db_session, user.id, product.id)
    assert legacy is not None
    assert legacy.source == EntitlementSource.PADDLE.value


def test_duplicate_webhook_delivery_does_not_duplicate_subscription(db_session):

    user = User(email="wh2@example.com", password_hash="x", email_verified=True)
    db_session.add(user)
    product = _product(db_session, "wh-product-c")
    entitlement_service.get_or_create_plan(db_session, product.id, "pro", "Pro")
    db_session.commit()

    provider = FakeBillingProvider()
    event_id = str(uuid.uuid4())
    body = _subscription_event(event_id, user.id, product.id, "pro", "sub_wh2")
    headers = {"fake-signature": provider.sign(body)}

    webhook_service.receive_webhook(db_session, provider, body, headers)
    db_session.commit()
    journal_count_before = len(db_session.execute(
        select(BillingWebhookEvent).where(BillingWebhookEvent.provider_event_id == event_id)
    ).scalars().all())

    # Exact same event delivered a second time (provider retry).
    webhook_service.receive_webhook(db_session, provider, body, headers)
    db_session.commit()
    journal_count_after = len(db_session.execute(
        select(BillingWebhookEvent).where(BillingWebhookEvent.provider_event_id == event_id)
    ).scalars().all())

    assert journal_count_before == 1
    assert journal_count_after == 1  # never duplicated

    subscriptions = db_session.execute(
        select(Subscription).where(Subscription.provider_subscription_ref == "sub_wh2")
    ).scalars().all()
    assert len(subscriptions) == 1


def test_transaction_completed_creates_payment_record_once(db_session):

    user = User(email="wh3@example.com", password_hash="x", email_verified=True)
    db_session.add(user)
    product = _product(db_session, "wh-product-d")
    entitlement_service.get_or_create_plan(db_session, product.id, "pro", "Pro")
    db_session.commit()

    provider = FakeBillingProvider()
    sub_body = _subscription_event(str(uuid.uuid4()), user.id, product.id, "pro", "sub_wh3")
    webhook_service.receive_webhook(db_session, provider, sub_body, {"fake-signature": provider.sign(sub_body)})
    db_session.commit()

    txn_event_id = str(uuid.uuid4())
    txn_body = _transaction_event(txn_event_id, "sub_wh3", 1999, "USD")
    journal = webhook_service.receive_webhook(db_session, provider, txn_body, {"fake-signature": provider.sign(txn_body)})
    db_session.commit()
    assert journal.status == "processed"

    payments = db_session.execute(
        select(PaymentRecord).where(PaymentRecord.provider_reference == txn_event_id)
    ).scalars().all()
    assert len(payments) == 1
    assert payments[0].amount_cents == 1999
    assert payments[0].user_id == user.id

    # Replaying the exact same transaction event must never double-create revenue.
    replayed = webhook_service.replay_failed_event(db_session, provider, journal.id)
    db_session.commit()
    assert replayed.status == "processed"
    payments_after_replay = db_session.execute(
        select(PaymentRecord).where(PaymentRecord.provider_reference == txn_event_id)
    ).scalars().all()
    assert len(payments_after_replay) == 1


def test_gift_never_creates_a_payment_record(db_session):
    """Structural check for mission-brief Phase 13: gift_service has no
    import of the billing package at all, so this is really just
    confirming no PaymentRecord appears as a side effect of a gift."""
    from app.services import gift_service

    admin = User(email="wh-admin4@example.com", password_hash="x", email_verified=True)
    target = User(email="wh-target4@example.com", password_hash="x", email_verified=True)
    db_session.add_all([admin, target])
    product = _product(db_session, "wh-product-e")
    plan = entitlement_service.get_or_create_plan(db_session, product.id, "pro", "Pro")
    db_session.commit()

    before = len(db_session.execute(select(PaymentRecord)).scalars().all())
    gift_service.grant_gift(db_session, admin, target, plan, "support", None)
    db_session.commit()
    after = len(db_session.execute(select(PaymentRecord)).scalars().all())
    assert before == after
