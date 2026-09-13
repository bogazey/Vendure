"""Mission 6 (Phases 41-43): the transactional outbox and signed delivery
to subscribed products."""
from __future__ import annotations

from sqlalchemy import select

from app.database.models import OutboxEvent, Product, User
from app.services import oidc_service, outbox_service


def _admin(db_session, email: str) -> User:
    user = User(email=email, password_hash="x", email_verified=True)
    db_session.add(user)
    db_session.flush()
    return user


def _product(db_session, product_id: str) -> Product:
    if db_session.get(Product, product_id) is None:
        db_session.add(Product(id=product_id, name=product_id, domain=f"{product_id}.example", status="live"))
        db_session.flush()
    return db_session.get(Product, product_id)


def test_event_with_no_subscribed_client_is_marked_delivered_not_failed(db_session):
    # Assertions below check this specific event's own row, not the
    # aggregate counters `deliver_pending` returns - other tests in this
    # shared test database enqueue their own outbox events, so the
    # aggregate totals are not exclusively this test's to assert on.
    product = _product(db_session, "obx-product-a")
    event = outbox_service.enqueue(db_session, "entitlement.changed", product.id, {"user_id": "u1"})
    db_session.commit()

    result = outbox_service.deliver_pending(db_session, http_post=lambda *_: 200)
    db_session.commit()
    assert result["delivered"] >= 1
    assert db_session.get(OutboxEvent, event.id).status == "delivered"


def test_delivered_event_is_signed_and_verifiable(db_session):
    admin = _admin(db_session, "admin-obx1@example.com")
    product = _product(db_session, "obx-product-b")
    client, _secret = oidc_service.register_client(db_session, admin, "obx-client-b", "Obx client", product.id, [])
    client.webhook_url = "https://product.example/webhooks/platform"
    client.webhook_signing_secret = "obx-shared-secret"
    db_session.commit()

    event = outbox_service.enqueue(db_session, "entitlement.changed", product.id, {"user_id": "u2"})
    db_session.commit()

    captured = {}

    def fake_post(url, headers, body):
        captured["url"] = url
        captured["headers"] = headers
        captured["body"] = body
        return 200

    outbox_service.deliver_pending(db_session, http_post=fake_post)
    db_session.commit()
    assert db_session.get(OutboxEvent, event.id).status == "delivered"
    assert captured["url"] == client.webhook_url
    assert outbox_service.verify_signature(
        "obx-shared-secret", captured["body"], captured["headers"]["X-Platform-Signature"]
    )
    # A tampered body must fail verification.
    assert not outbox_service.verify_signature(
        "obx-shared-secret", captured["body"] + b"x", captured["headers"]["X-Platform-Signature"]
    )
    # The wrong secret must also fail verification.
    assert not outbox_service.verify_signature(
        "wrong-secret", captured["body"], captured["headers"]["X-Platform-Signature"]
    )


def test_one_failing_client_does_not_block_delivery_to_another(db_session):
    admin = _admin(db_session, "admin-obx2@example.com")
    product = _product(db_session, "obx-product-c")
    good, _s1 = oidc_service.register_client(db_session, admin, "obx-good", "Good", product.id, [])
    bad, _s2 = oidc_service.register_client(db_session, admin, "obx-bad", "Bad", product.id, [])
    good.webhook_url, good.webhook_signing_secret = "https://good.example/hook", "secret-good"
    bad.webhook_url, bad.webhook_signing_secret = "https://bad.example/hook", "secret-bad"
    db_session.commit()

    event = outbox_service.enqueue(db_session, "entitlement.changed", product.id, {"user_id": "u3"})
    db_session.commit()

    calls = []

    def flaky_post(url, headers, body):
        calls.append(url)
        if "bad.example" in url:
            raise ConnectionError("simulated network failure")
        return 200

    outbox_service.deliver_pending(db_session, http_post=flaky_post)
    db_session.commit()
    # Because one of the two subscribed clients failed, the event as a
    # whole is not "delivered" - but the call to the good client still
    # happened (proving one bad endpoint did not block it) and did not
    # raise out of deliver_pending.
    assert good.webhook_url in calls
    assert bad.webhook_url in calls
    refreshed = db_session.get(OutboxEvent, event.id)
    assert refreshed.status == "pending"  # not yet at max_attempts
    assert refreshed.attempts == 1


def test_event_reaches_failed_status_after_max_attempts(db_session):
    admin = _admin(db_session, "admin-obx3@example.com")
    product = _product(db_session, "obx-product-d")
    client, _s = oidc_service.register_client(db_session, admin, "obx-alwaysfail", "AlwaysFail", product.id, [])
    client.webhook_url, client.webhook_signing_secret = "https://down.example/hook", "secret"
    db_session.commit()

    outbox_service.enqueue(db_session, "entitlement.changed", product.id, {"user_id": "u4"})
    db_session.commit()

    def always_fail(url, headers, body):
        return 500

    from app.config.settings import get_settings

    for _ in range(get_settings().outbox_max_attempts):
        outbox_service.deliver_pending(db_session, http_post=always_fail)
        db_session.commit()

    events = db_session.execute(select(OutboxEvent).where(OutboxEvent.product_id == product.id)).scalars().all()
    assert events[0].status == "failed"
    assert events[0].attempts == get_settings().outbox_max_attempts
