"""Mission 6 (Phases 41-43): the transactional outbox and signed delivery
to subscribed products."""
from __future__ import annotations

from sqlalchemy import select

from app.database.models import OutboxEvent, Product, User
from app.models.enums import GLOBAL_SCOPE, RoleSlug
from app.security import secret_encryption
from app.services import oidc_service, outbox_service, rbac_service


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
    client.webhook_signing_secret_encrypted = secret_encryption.encrypt("obx-shared-secret")
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
    good.webhook_url = "https://good.example/hook"
    good.webhook_signing_secret_encrypted = secret_encryption.encrypt("secret-good")
    bad.webhook_url = "https://bad.example/hook"
    bad.webhook_signing_secret_encrypted = secret_encryption.encrypt("secret-bad")
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
    client.webhook_url = "https://down.example/hook"
    client.webhook_signing_secret_encrypted = secret_encryption.encrypt("secret")
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


def test_admin_can_configure_client_webhook_and_it_actually_delivers(client, db_session):
    r = client.post("/api/v1/auth/signup", json={"email": "admin-obx-config@example.com", "password": "correct-horse-battery"})
    assert r.status_code == 201
    admin = db_session.query(User).filter_by(email="admin-obx-config@example.com").first()
    rbac_service.assign_role(db_session, admin, RoleSlug.SUPER_ADMIN, GLOBAL_SCOPE, granted_by=None)
    product = _product(db_session, "obx-product-configured")
    reg_client, _secret = oidc_service.register_client(db_session, admin, "obx-configured-client", "Configured", product.id, [])
    db_session.commit()

    resp = client.post(f"/api/v1/admin/clients/{reg_client.client_id}/webhook", json={"webhook_url": "https://configured.example/hook"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["webhook_url"] == "https://configured.example/hook"
    signing_secret = body["webhook_signing_secret"]
    assert signing_secret

    outbox_service.enqueue(db_session, "entitlement.changed", product.id, {"user_id": "u5"})
    db_session.commit()

    captured = {}

    def fake_post(url, headers, body_bytes):
        captured["url"], captured["headers"], captured["body"] = url, headers, body_bytes
        return 200

    outbox_service.deliver_pending(db_session, http_post=fake_post)
    db_session.commit()
    assert captured["url"] == "https://configured.example/hook"
    assert outbox_service.verify_signature(signing_secret, captured["body"], captured["headers"]["X-Platform-Signature"])


def test_system_health_reports_outbox_and_webhook_backlog(client, db_session):
    r = client.post("/api/v1/auth/signup", json={"email": "admin-health@example.com", "password": "correct-horse-battery"})
    assert r.status_code == 201
    admin = db_session.query(User).filter_by(email="admin-health@example.com").first()
    rbac_service.assign_role(db_session, admin, RoleSlug.SUPER_ADMIN, GLOBAL_SCOPE, granted_by=None)
    db_session.commit()

    product = _product(db_session, "obx-health-product")
    outbox_service.enqueue(db_session, "entitlement.changed", product.id, {"user_id": "u6"})
    db_session.commit()

    resp = client.get("/api/v1/admin/system-health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["database"] is True
    assert "signing_key_configured" in body
    assert body["outbox"]["pending"] >= 1
    assert "billing_webhooks" in body
