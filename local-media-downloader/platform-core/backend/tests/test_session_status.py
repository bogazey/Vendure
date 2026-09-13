"""`/api/v1/me/status` (mission 4, phase 12): lets a product's backend
positively distinguish "this account is centrally disabled" from "this
bearer token is invalid/expired" - both a normal `/api/v1` route would
collapse into the same generic 401 via `get_bearer_principal`.
"""
from __future__ import annotations

import base64
import hashlib
import secrets

from app.database.models import Product, User
from app.services import oidc_service


def _pkce_pair():
    verifier = secrets.token_urlsafe(64)[:64]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def _make_product_and_client(db_session, product_id: str, redirect_uri: str):
    if db_session.get(Product, product_id) is None:
        db_session.add(Product(id=product_id, name=product_id.title(), domain=f"{product_id}.example", status="live"))
        db_session.flush()
    actor = User(email=f"bootstrap-{product_id}@example.com", password_hash="x", email_verified=True)
    db_session.add(actor)
    db_session.flush()
    client_obj, secret = oidc_service.register_client(
        db_session, actor, client_id=f"client-{product_id}", name=product_id, product_id=product_id,
        redirect_uris=[redirect_uri],
    )
    db_session.commit()
    return client_obj.client_id, secret


def _mint_access_token(client, db_session, product_id: str, email: str) -> tuple[str, User]:
    client_id, secret = _make_product_and_client(db_session, product_id, f"http://localhost:9999/cb-{product_id}")
    verifier, challenge = _pkce_pair()

    r = client.post("/api/v1/auth/signup", json={"email": email, "password": "correct-horse-battery"})
    assert r.status_code == 201

    r = client.get(
        "/oauth/authorize",
        params={
            "response_type": "code", "client_id": client_id,
            "redirect_uri": f"http://localhost:9999/cb-{product_id}", "code_challenge": challenge,
            "code_challenge_method": "S256", "state": "s",
        },
        follow_redirects=False,
    )
    assert r.status_code == 302
    code = r.headers["location"].split("code=")[1].split("&")[0]

    token_r = client.post("/oauth/token", data={
        "grant_type": "authorization_code", "client_id": client_id, "client_secret": secret,
        "code": code, "redirect_uri": f"http://localhost:9999/cb-{product_id}", "code_verifier": verifier,
    })
    assert token_r.status_code == 200
    user = db_session.query(User).filter_by(email=email).first()
    return token_r.json()["access_token"], user


def test_status_reports_active_for_an_enabled_user(client, db_session):
    access_token, user = _mint_access_token(client, db_session, "status-a", "status-active@example.com")

    r = client.get("/api/v1/me/status", headers={"Authorization": f"Bearer {access_token}"})
    assert r.status_code == 200
    assert r.json() == {"sub": user.id, "status": "active"}


def test_status_reports_disabled_without_a_generic_401_after_central_disable(client, db_session):
    access_token, user = _mint_access_token(client, db_session, "status-b", "status-disabled@example.com")

    user.status = "disabled"
    db_session.commit()

    r = client.get("/api/v1/me/status", headers={"Authorization": f"Bearer {access_token}"})
    assert r.status_code == 200
    assert r.json()["status"] == "disabled"

    # Contrast: a normal resource endpoint DOES gate on status (401) - this
    # confirms /me/status is the deliberate, narrow exception.
    r2 = client.get("/api/v1/entitlements/me", headers={"Authorization": f"Bearer {access_token}"})
    assert r2.status_code == 401


def test_status_rejects_a_missing_bearer_token(client):
    r = client.get("/api/v1/me/status")
    assert r.status_code == 401


def test_status_rejects_an_invalid_bearer_token(client):
    r = client.get("/api/v1/me/status", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401
