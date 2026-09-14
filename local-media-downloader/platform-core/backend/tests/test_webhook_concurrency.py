"""Mission 6 (Phase 45): concurrency/idempotency - two real threads
deliver the exact same webhook event at the same time, each with its own
DB session/connection (not the shared `db_session` fixture, which would
defeat the point), to actually exercise the IntegrityError race path in
`webhook_service.receive_webhook` rather than just its sequential
fast-path."""
from __future__ import annotations

import json
import threading
import uuid

from sqlalchemy import select

from app.database.db import get_session_factory
from app.database.models import BillingWebhookEvent, Product, Subscription, User
from app.services import entitlement_service
from app.services.billing.fake_provider import FakeBillingProvider


def test_concurrent_identical_webhook_deliveries_create_exactly_one_subscription(db_session):
    user = User(email="concurrent-wh@example.com", password_hash="x", email_verified=True)
    db_session.add(user)
    product_id = "concurrency-wh-product"
    if db_session.get(Product, product_id) is None:
        db_session.add(Product(id=product_id, name=product_id, domain=f"{product_id}.example", status="live"))
    db_session.flush()
    entitlement_service.get_or_create_plan(db_session, product_id, "pro", "Pro")
    db_session.commit()

    event_id = str(uuid.uuid4())
    payload = {
        "event_id": event_id, "event_type": "subscription.created", "occurred_at": "2026-01-01T00:00:00+00:00",
        "subscription_ref": "sub_concurrent_1", "customer_ref": f"cust_{user.id}", "status": "active",
        "custom_data": {"user_id": user.id, "product_id": product_id, "plan_slug": "pro"},
    }
    body = json.dumps(payload).encode("utf-8")
    signature = FakeBillingProvider.sign(body)
    headers = {"fake-signature": signature}

    errors: list[BaseException] = []
    barrier = threading.Barrier(2)

    def deliver():
        from app.services import webhook_service

        session = get_session_factory()()
        try:
            barrier.wait(timeout=5)  # maximize the chance both threads race the same INSERT
            provider = FakeBillingProvider()
            webhook_service.receive_webhook(session, provider, body, headers)
            session.commit()
        except BaseException as exc:  # noqa: BLE001 - capture to fail the test from the main thread
            errors.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=deliver) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, f"concurrent webhook delivery raised: {errors}"

    verify_session = get_session_factory()()
    try:
        journals = verify_session.execute(
            select(BillingWebhookEvent).where(BillingWebhookEvent.provider_event_id == event_id)
        ).scalars().all()
        subscriptions = verify_session.execute(
            select(Subscription).where(Subscription.provider_subscription_ref == "sub_concurrent_1")
        ).scalars().all()
        assert len(journals) == 1, "exactly one webhook journal row, never two, from two concurrent identical deliveries"
        assert len(subscriptions) == 1, "exactly one subscription row, never a duplicate"
    finally:
        verify_session.close()
