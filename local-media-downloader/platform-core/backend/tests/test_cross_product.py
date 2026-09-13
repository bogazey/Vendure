"""The SSO acceptance test from the mission brief (section 31): one central
account, authenticating into two independent product clients, sharing
exactly one `global_user_id`, with entitlements isolated per product.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
from urllib.parse import parse_qs, urlparse

from app.database.models import Product, User
from app.models.enums import EntitlementSource
from app.services import entitlement_service, oidc_service


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
    entitlement_service.get_or_create_plan(db_session, product_id, "pro", "Pro")
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
    assert not r.headers["location"].startswith("/login"), "expected silent SSO, no re-authentication"
    code = parse_qs(urlparse(r.headers["location"]).query)["code"][0]

    token_r = client.post("/oauth/token", data={
        "grant_type": "authorization_code", "client_id": client_id, "client_secret": client_secret,
        "code": code, "redirect_uri": redirect_uri, "code_verifier": verifier,
    })
    assert token_r.status_code == 200
    return token_r.json()


def test_one_account_two_products_same_global_id_isolated_entitlements(client, db_session):
    client_a, secret_a = _register_product_client(db_session, "cross-a", "http://localhost:9201/callback")
    client_b, secret_b = _register_product_client(db_session, "cross-b", "http://localhost:9202/callback")

    # 1. Create one central account.
    signup_r = client.post("/api/v1/auth/signup", json={"email": "crossuser@example.com", "password": "correct-horse-battery"})
    assert signup_r.status_code == 201
    expected_global_id = signup_r.json()["id"]

    # 2 & 3. Log into Demo Product A, confirm global user ID via id_token/userinfo.
    tokens_a = _authenticate_into_client(client, client_a, secret_a, "http://localhost:9201/callback")
    userinfo_a = client.get("/oauth/userinfo", headers={"Authorization": f"Bearer {tokens_a['access_token']}"})
    assert userinfo_a.status_code == 200
    assert userinfo_a.json()["sub"] == expected_global_id

    # 4 & 5. Open Demo Product B, authenticate through central identity -
    # the existing central session means no login page, no re-entered password.
    tokens_b = _authenticate_into_client(client, client_b, secret_b, "http://localhost:9202/callback")
    userinfo_b = client.get("/oauth/userinfo", headers={"Authorization": f"Bearer {tokens_b['access_token']}"})
    assert userinfo_b.status_code == 200

    # 6 & 7. No second account was created; both products see the exact same id.
    assert userinfo_b.json()["sub"] == expected_global_id
    total_users_with_this_email = db_session.query(User).filter_by(email="crossuser@example.com").count()
    assert total_users_with_this_email == 1

    # 8 & 9. Give Product A an entitlement, verify Product A's own bearer
    # call sees it.
    admin = db_session.query(User).filter_by(email=f"bootstrap-cross-a@example.com").first()
    target = db_session.get(User, expected_global_id)
    entitlement_service.grant_or_change(db_session, admin, target, "cross-a", "pro", EntitlementSource.GIFTED, None, "acceptance test")
    db_session.commit()

    ent_a = client.get("/api/v1/entitlements/me", headers={"Authorization": f"Bearer {tokens_a['access_token']}"})
    assert ent_a.status_code == 200
    assert ent_a.json()["entitled"] is True
    assert ent_a.json()["entitlement"]["product_id"] == "cross-a"

    # 10. Verify Product B does NOT see Product A's entitlement for the same user.
    ent_b = client.get("/api/v1/entitlements/me", headers={"Authorization": f"Bearer {tokens_b['access_token']}"})
    assert ent_b.status_code == 200
    assert ent_b.json()["entitled"] is False

    # 11 & 12. Grant Product B's own entitlement; verify both independently,
    # and that Product A's view is unaffected.
    admin_b = db_session.query(User).filter_by(email=f"bootstrap-cross-b@example.com").first()
    entitlement_service.grant_or_change(db_session, admin_b, target, "cross-b", "pro", EntitlementSource.PADDLE, None, None)
    db_session.commit()

    ent_b_after = client.get("/api/v1/entitlements/me", headers={"Authorization": f"Bearer {tokens_b['access_token']}"})
    assert ent_b_after.json()["entitled"] is True
    assert ent_b_after.json()["entitlement"]["source"] == "paddle"

    ent_a_after = client.get("/api/v1/entitlements/me", headers={"Authorization": f"Bearer {tokens_a['access_token']}"})
    assert ent_a_after.json()["entitled"] is True
    assert ent_a_after.json()["entitlement"]["source"] == "gifted"

    # Both products recorded a membership - and only these two.
    memberships_r = client.get("/api/v1/me/memberships")
    memberships = {m["product_id"] for m in memberships_r.json()}
    assert memberships == {"cross-a", "cross-b"}
