"""Mission 7 (Phase 28 blocker, MISSION_7_ARCHITECTURE_AUDIT.md section 2):
`/api/v1/entitlements/me` only ever looked at the single legacy
`Entitlement` row, so a user entitled via a bundle or a promotion/trial
(V2-only sources merged by `capability_service.resolve_effective_entitlements`)
showed as `entitled=False` to their own product's backend, even though
the V2 engine already knew about the access correctly - it just had no
bearer-authenticated, self-serve route. `/api/v1/capabilities/me` closes
that gap; these tests prove the OLD gap (still real on `/entitlements/me`)
and the NEW endpoint's correctness against the same data, including the
same per-product isolation `/entitlements/me` already guarantees.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
from urllib.parse import parse_qs, urlparse

from app.database.models import Product, User
from app.services import bundle_service, oidc_service


def _pkce_pair():
    verifier = secrets.token_urlsafe(64)[:64]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def _register_product_client(db_session, product_id: str, redirect_uri: str):
    db_session.add(Product(id=product_id, name=product_id.title(), domain=f"{product_id}.example", status="live"))
    db_session.flush()
    bootstrap = User(email=f"bootstrap-{product_id}@example.com", password_hash="x", email_verified=True)
    db_session.add(bootstrap)
    db_session.flush()
    client_obj, secret = oidc_service.register_client(
        db_session, bootstrap, client_id=f"demo-{product_id}", name=product_id, product_id=product_id,
        redirect_uris=[redirect_uri],
    )
    db_session.commit()
    return client_obj.client_id, secret


def _authenticate_into_client(client, client_id: str, client_secret: str, redirect_uri: str) -> dict:
    verifier, challenge = _pkce_pair()
    r = client.get(
        "/oauth/authorize",
        params={
            "response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri,
            "code_challenge": challenge, "code_challenge_method": "S256",
        },
        follow_redirects=False,
    )
    assert r.status_code == 302, r.text
    code = parse_qs(urlparse(r.headers["location"]).query)["code"][0]

    token_r = client.post("/oauth/token", data={
        "grant_type": "authorization_code", "client_id": client_id, "client_secret": client_secret,
        "code": code, "redirect_uri": redirect_uri, "code_verifier": verifier,
    })
    assert token_r.status_code == 200
    return token_r.json()


def test_bundle_only_access_is_invisible_to_entitlements_me_but_visible_to_capabilities_me(client, db_session):
    admin = User(email="bootstrap-capmine@example.com", password_hash="x", email_verified=True)
    db_session.add(admin)
    db_session.flush()

    client_id, secret = _register_product_client(db_session, "capmine-product", "http://localhost:9301/callback")

    signup_r = client.post(
        "/api/v1/auth/signup", json={"email": "capmineuser@example.com", "password": "correct-horse-battery"},
    )
    assert signup_r.status_code == 201
    target = db_session.get(User, signup_r.json()["id"])

    from app.services import entitlement_service
    plan = entitlement_service.get_or_create_plan(db_session, "capmine-product", "creator", "Creator")
    bundle = bundle_service.create_bundle(db_session, admin, "capmine-bundle", "Capmine Bundle")
    bundle_service.add_product_plan(db_session, bundle, plan)
    db_session.commit()
    bundle_service.grant_bundle_access(db_session, admin, target, bundle, source="paddle")
    db_session.commit()

    tokens = _authenticate_into_client(client, client_id, secret, "http://localhost:9301/callback")
    auth_header = {"Authorization": f"Bearer {tokens['access_token']}"}

    # The pre-existing gap: bundle access is real, but /entitlements/me
    # cannot see it - only the single legacy Entitlement row.
    legacy = client.get("/api/v1/entitlements/me", headers=auth_header)
    assert legacy.status_code == 200
    assert legacy.json()["entitled"] is False

    # The fix: /capabilities/me resolves the same user/product through
    # the V2 merge engine and correctly reports the bundle-derived access.
    caps = client.get("/api/v1/capabilities/me", headers=auth_header)
    assert caps.status_code == 200
    body = caps.json()
    assert body["entitled"] is True
    assert body["product_id"] == "capmine-product"
    assert any(s["kind"] == "bundle" and s["plan_id"] == plan.id for s in body["sources"])


def test_capabilities_me_is_scoped_to_the_calling_products_own_client(client, db_session):
    admin = User(email="bootstrap-capscope@example.com", password_hash="x", email_verified=True)
    db_session.add(admin)
    db_session.flush()

    client_a, secret_a = _register_product_client(db_session, "capscope-a", "http://localhost:9302/callback")
    client_b, secret_b = _register_product_client(db_session, "capscope-b", "http://localhost:9303/callback")

    signup_r = client.post(
        "/api/v1/auth/signup", json={"email": "capscopeuser@example.com", "password": "correct-horse-battery"},
    )
    assert signup_r.status_code == 201
    target = db_session.get(User, signup_r.json()["id"])

    from app.services import entitlement_service
    plan_a = entitlement_service.get_or_create_plan(db_session, "capscope-a", "creator", "Creator")
    bundle = bundle_service.create_bundle(db_session, admin, "capscope-bundle", "Capscope Bundle")
    bundle_service.add_product_plan(db_session, bundle, plan_a)
    db_session.commit()
    bundle_service.grant_bundle_access(db_session, admin, target, bundle, source="paddle")
    db_session.commit()

    tokens_a = _authenticate_into_client(client, client_a, secret_a, "http://localhost:9302/callback")
    tokens_b = _authenticate_into_client(client, client_b, secret_b, "http://localhost:9303/callback")

    caps_a = client.get("/api/v1/capabilities/me", headers={"Authorization": f"Bearer {tokens_a['access_token']}"})
    assert caps_a.json()["entitled"] is True

    # Product B's own client, same global user, never sees Product A's
    # bundle-derived access - identical isolation guarantee to /entitlements/me.
    caps_b = client.get("/api/v1/capabilities/me", headers={"Authorization": f"Bearer {tokens_b['access_token']}"})
    assert caps_b.json()["entitled"] is False
    assert caps_b.json()["sources"] == []
