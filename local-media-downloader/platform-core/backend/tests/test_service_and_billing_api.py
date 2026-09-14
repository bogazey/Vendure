"""HTTP-level tests for the Mission 6 service-auth and billing-webhook
endpoints - through the real FastAPI app (`client` fixture), not by
calling service functions directly, so route wiring/dependencies/rate
limiting are exercised too."""
from __future__ import annotations

import json

from app.database.models import Product, User
from app.models.enums import EntitlementSource
from app.services import entitlement_service, oidc_service, service_auth
from app.services.billing.fake_provider import FakeBillingProvider


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


def test_client_credentials_grant_over_http(client, db_session):
    admin = _admin(db_session, "admin-api-svc1@example.com")
    product = _product(db_session, "api-svc-product-a")
    reg, secret = oidc_service.register_client(db_session, admin, "api-svc-client-a", "Svc A", product.id, [])
    service_auth.grant_scope(db_session, admin, reg, "service:entitlements:read")
    db_session.commit()

    r = client.post("/oauth/token", data={
        "grant_type": "client_credentials", "client_id": reg.client_id, "client_secret": secret,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "service:entitlements:read"
    assert body["token_type"] == "Bearer"


def test_service_route_requires_correct_scope(client, db_session):
    admin = _admin(db_session, "admin-api-svc2@example.com")
    product = _product(db_session, "api-svc-product-b")
    reg, secret = oidc_service.register_client(db_session, admin, "api-svc-client-b", "Svc B", product.id, [])
    # Only memberships scope granted, not entitlements.
    service_auth.grant_scope(db_session, admin, reg, "service:memberships:read")
    db_session.commit()

    token_r = client.post("/oauth/token", data={
        "grant_type": "client_credentials", "client_id": reg.client_id, "client_secret": secret,
    })
    token = token_r.json()["access_token"]

    r = client.get(f"/api/v1/service/entitlements/{admin.id}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_service_entitlements_route_is_scoped_to_callers_own_product(client, db_session):
    admin = _admin(db_session, "admin-api-svc3@example.com")
    target = User(email="target-api-svc3@example.com", password_hash="x", email_verified=True)
    db_session.add(target)
    product_a = _product(db_session, "api-svc-product-c")
    product_b = _product(db_session, "api-svc-product-d")
    entitlement_service.get_or_create_plan(db_session, product_a.id, "pro", "Pro")
    entitlement_service.get_or_create_plan(db_session, product_b.id, "pro", "Pro")
    db_session.flush()

    # target has an active paid entitlement in BOTH products.
    entitlement_service.grant_or_change(db_session, admin, target, product_a.id, "pro", EntitlementSource.PADDLE, None, None)
    entitlement_service.grant_or_change(db_session, admin, target, product_b.id, "pro", EntitlementSource.PADDLE, None, None)

    client_a, secret_a = oidc_service.register_client(db_session, admin, "api-svc-client-c", "Svc C", product_a.id, [])
    service_auth.grant_scope(db_session, admin, client_a, "service:entitlements:read")
    db_session.commit()

    token = client.post("/oauth/token", data={
        "grant_type": "client_credentials", "client_id": client_a.client_id, "client_secret": secret_a,
    }).json()["access_token"]

    r = client.get(f"/api/v1/service/entitlements/{target.id}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    # Product A's service client only ever sees product A's data - there
    # is no parameter on this route to ask about product B at all.
    assert body["product_id"] == product_a.id


def test_billing_webhook_endpoint_rejects_bad_signature(client):
    payload = {"event_id": "evt_api1", "event_type": "subscription.created", "occurred_at": "2026-01-01T00:00:00+00:00"}
    r = client.post(
        "/api/v1/billing/webhooks/fake", content=json.dumps(payload).encode(),
        headers={"fake-signature": "not-a-real-signature"},
    )
    assert r.status_code == 401
    assert r.json()["code"] == "INVALID_WEBHOOK_SIGNATURE"


def test_billing_webhook_endpoint_processes_a_valid_signed_event(client, db_session):
    target = User(email="wh-api1@example.com", password_hash="x", email_verified=True)
    db_session.add(target)
    product = _product(db_session, "api-wh-product-a")
    entitlement_service.get_or_create_plan(db_session, product.id, "pro", "Pro")
    db_session.commit()

    payload = {
        "event_id": "evt_api2", "event_type": "subscription.created", "occurred_at": "2026-01-01T00:00:00+00:00",
        "subscription_ref": "sub_api2", "customer_ref": f"cust_{target.id}", "status": "active",
        "custom_data": {"user_id": target.id, "product_id": product.id, "plan_slug": "pro"},
    }
    body = json.dumps(payload).encode()
    signature = FakeBillingProvider.sign(body)

    r = client.post("/api/v1/billing/webhooks/fake", content=body, headers={"fake-signature": signature})
    assert r.status_code == 200
    assert r.json()["status"] == "processed"

    legacy = entitlement_service.get_active_entitlement(db_session, target.id, product.id)
    assert legacy is not None and legacy.source == EntitlementSource.PADDLE.value


def test_billing_checkout_succeeds_against_fake_provider_with_a_real_plan(client, db_session):
    product = _product(db_session, "api-checkout-product-fake")
    entitlement_service.get_or_create_plan(db_session, product.id, "pro", "Pro")
    db_session.commit()
    r = client.post("/api/v1/auth/signup", json={"email": "checkout-fake@example.com", "password": "correct-horse-battery"})
    assert r.status_code == 201

    resp = client.post("/api/v1/billing/checkout", json={
        "provider": "fake", "product_id": product.id, "plan_slug": "pro", "success_url": "https://example.test/ok",
    })
    assert resp.status_code == 200
    assert resp.json()["url"].startswith("https://example.test/ok")


def test_billing_checkout_rejects_a_plan_that_does_not_exist(client, db_session):
    _product(db_session, "api-checkout-product-a")
    db_session.commit()
    r = client.post("/api/v1/auth/signup", json={"email": "checkout-badplan@example.com", "password": "correct-horse-battery"})
    assert r.status_code == 201

    resp = client.post("/api/v1/billing/checkout", json={
        "provider": "fake", "product_id": "api-checkout-product-a", "plan_slug": "does-not-exist",
        "success_url": "https://example.test/ok",
    })
    assert resp.status_code == 422
    assert resp.json()["code"] == "INVALID_PLAN"


def test_billing_checkout_against_real_paddle_provider_returns_not_configured(client, db_session):
    """Mission-brief Phase 9/56: no live Paddle call is ever made in this
    mission - the route must fail loudly (501), never silently succeed."""
    product = _product(db_session, "api-checkout-product-b")
    entitlement_service.get_or_create_plan(db_session, product.id, "pro", "Pro")
    db_session.commit()
    r = client.post("/api/v1/auth/signup", json={"email": "checkout-user@example.com", "password": "correct-horse-battery"})
    assert r.status_code == 201

    resp = client.post("/api/v1/billing/checkout", json={
        "provider": "paddle", "product_id": product.id, "plan_slug": "pro", "success_url": "https://example.test/ok",
    })
    assert resp.status_code == 501
    assert resp.json()["code"] == "PROVIDER_NOT_CONFIGURED"
