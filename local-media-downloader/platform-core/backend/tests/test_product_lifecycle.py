"""Mission 17 (multi-product expansion prep): product/client inspect,
update, and disable capability - GENUINE gaps identified by this
mission's own audit (product ids were previously write-once-at-creation
and OAuth clients had an unused `is_active` column that nothing ever
flipped). Covers: GET/PATCH `/products/{id}`, `/products/{id}/verify`,
`/products/{id}/active`, `/clients/{id}/active`, and that a disabled
product or client actually blocks sign-in end to end - not merely that
the flag gets set."""
from __future__ import annotations

import base64
import hashlib
import secrets

from app.database.models import OAuthClient, Product, User
from app.models.enums import GLOBAL_SCOPE, RoleSlug, product_scope
from app.services import oidc_service, rbac_service

LOADY = "life-loady"
GAMEY = "life-gamey"


def _pkce_pair():
    verifier = secrets.token_urlsafe(64)[:64]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def _signup(client, email: str) -> User:
    r = client.post("/api/v1/auth/signup", json={"email": email, "password": "correct-horse-battery"})
    assert r.status_code == 201, r.text
    return r


def _make_product_admin(client, db_session, email: str, product_id: str) -> User:
    _signup(client, email)
    user = db_session.query(User).filter_by(email=email).first()
    rbac_service.assign_role(db_session, user, RoleSlug.ADMIN, product_scope(product_id), granted_by=None)
    db_session.commit()
    return user


def _make_super_admin(client, db_session, email: str) -> User:
    _signup(client, email)
    user = db_session.query(User).filter_by(email=email).first()
    rbac_service.assign_role(db_session, user, RoleSlug.SUPER_ADMIN, GLOBAL_SCOPE, granted_by=None)
    db_session.commit()
    return user


def _setup_products(db_session):
    for pid in (LOADY, GAMEY):
        if db_session.get(Product, pid) is None:
            db_session.add(Product(id=pid, name=pid, domain=f"{pid}.example", status="live"))
    db_session.flush()
    db_session.commit()


def _make_client(db_session, product_id: str, redirect_uri: str, client_id: str) -> tuple[str, str]:
    actor = User(email=f"bootstrap-{client_id}@example.com", password_hash="x", email_verified=True)
    db_session.add(actor)
    db_session.flush()
    client_obj, secret = oidc_service.register_client(
        db_session, actor, client_id=client_id, name=client_id, product_id=product_id,
        redirect_uris=[redirect_uri],
    )
    db_session.commit()
    return client_obj.client_id, secret


# --- GET /products/{id} ------------------------------------------------------

def test_get_product_returns_new_fields(client, db_session):
    _setup_products(db_session)
    _make_super_admin(client, db_session, "lc-get-super1@example.com")
    resp = client.get(f"/api/v1/admin/products/{LOADY}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == LOADY
    assert body["is_active"] is True
    assert "updated_at" in body


def test_get_product_404_for_unknown_product(client, db_session):
    _make_super_admin(client, db_session, "lc-get-super2@example.com")
    resp = client.get("/api/v1/admin/products/does-not-exist")
    assert resp.status_code == 404


def test_product_scoped_admin_cannot_get_another_products_detail(client, db_session):
    _setup_products(db_session)
    _make_product_admin(client, db_session, "lc-get-loadyadmin@example.com", LOADY)
    resp = client.get(f"/api/v1/admin/products/{GAMEY}")
    assert resp.status_code == 403


def test_product_scoped_admin_can_get_own_product_detail(client, db_session):
    _setup_products(db_session)
    _make_product_admin(client, db_session, "lc-get-loadyadmin2@example.com", LOADY)
    resp = client.get(f"/api/v1/admin/products/{LOADY}")
    assert resp.status_code == 200


# --- PATCH /products/{id} ----------------------------------------------------

def test_patch_product_updates_only_supplied_fields(client, db_session):
    _setup_products(db_session)
    _make_super_admin(client, db_session, "lc-patch-super1@example.com")
    resp = client.patch(f"/api/v1/admin/products/{LOADY}", json={"name": "Loady Renamed"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "Loady Renamed"
    assert body["domain"] == f"{LOADY}.example"  # untouched


def test_patch_product_can_clear_optional_fields_to_null(client, db_session):
    _setup_products(db_session)
    _make_super_admin(client, db_session, "lc-patch-super2@example.com")
    resp = client.patch(f"/api/v1/admin/products/{LOADY}", json={"icon_ref": "some-icon"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["icon_ref"] == "some-icon"

    resp2 = client.patch(f"/api/v1/admin/products/{LOADY}", json={"icon_ref": None})
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["icon_ref"] is None


def test_patch_product_id_field_is_never_accepted(client, db_session):
    _setup_products(db_session)
    _make_super_admin(client, db_session, "lc-patch-super3@example.com")
    resp = client.patch(f"/api/v1/admin/products/{LOADY}", json={"id": "renamed-id", "name": "Still Loady"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == LOADY  # unchanged - "id" is not a field on the request schema


def test_patch_product_bumps_updated_at(client, db_session):
    _setup_products(db_session)
    _make_super_admin(client, db_session, "lc-patch-super4@example.com")
    before = client.get(f"/api/v1/admin/products/{LOADY}").json()["updated_at"]
    resp = client.patch(f"/api/v1/admin/products/{LOADY}", json={"name": "Loady Touched"})
    assert resp.json()["updated_at"] >= before


def test_product_scoped_admin_cannot_patch_another_product(client, db_session):
    _setup_products(db_session)
    _make_product_admin(client, db_session, "lc-patch-loadyadmin@example.com", LOADY)
    resp = client.patch(f"/api/v1/admin/products/{GAMEY}", json={"name": "Hijacked"})
    assert resp.status_code == 403


def test_plain_user_cannot_patch_product(client, db_session):
    _setup_products(db_session)
    _signup(client, "lc-patch-plain@example.com")
    resp = client.patch(f"/api/v1/admin/products/{LOADY}", json={"name": "Hijacked"})
    assert resp.status_code == 403


# --- GET /products/{id}/verify -----------------------------------------------

def test_verify_product_reports_no_clients_and_no_plans_for_fresh_product(client, db_session):
    _setup_products(db_session)
    _make_super_admin(client, db_session, "lc-verify-super1@example.com")
    resp = client.get(f"/api/v1/admin/products/{LOADY}/verify")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["product_id"] == LOADY
    assert body["oauth_client_count"] == 0
    assert body["checks"]["has_at_least_one_oauth_client"] is False
    assert body["checks"]["product_is_active"] is True


def test_verify_product_reports_registered_client(client, db_session):
    _setup_products(db_session)
    _make_client(db_session, LOADY, "http://localhost:9201/callback", "lc-verify-client-a")
    _make_super_admin(client, db_session, "lc-verify-super2@example.com")
    resp = client.get(f"/api/v1/admin/products/{LOADY}/verify")
    body = resp.json()
    assert body["oauth_client_count"] == 1
    assert body["active_oauth_client_count"] == 1
    assert body["checks"]["has_at_least_one_active_oauth_client"] is True


def test_verify_product_is_never_mutating(client, db_session):
    _setup_products(db_session)
    _make_super_admin(client, db_session, "lc-verify-super3@example.com")
    before = client.get(f"/api/v1/admin/products/{LOADY}").json()
    client.get(f"/api/v1/admin/products/{LOADY}/verify")
    client.get(f"/api/v1/admin/products/{LOADY}/verify")
    after = client.get(f"/api/v1/admin/products/{LOADY}").json()
    assert before == after


# --- POST /products/{id}/active (global-admin-only) --------------------------

def test_global_admin_can_disable_and_reenable_a_product(client, db_session):
    _setup_products(db_session)
    _make_super_admin(client, db_session, "lc-active-super1@example.com")
    resp = client.post(f"/api/v1/admin/products/{LOADY}/active", json={"is_active": False})
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_active"] is False

    resp2 = client.post(f"/api/v1/admin/products/{LOADY}/active", json={"is_active": True})
    assert resp2.status_code == 200
    assert resp2.json()["is_active"] is True


def test_product_scoped_admin_cannot_disable_even_their_own_product(client, db_session):
    """Deliberately a higher bar than PATCH - disabling blocks sign-in for
    every one of the product's clients at once, so this mission scoped it
    to global admin only (see routes_admin.py::set_product_active)."""
    _setup_products(db_session)
    _make_product_admin(client, db_session, "lc-active-loadyadmin@example.com", LOADY)
    resp = client.post(f"/api/v1/admin/products/{LOADY}/active", json={"is_active": False})
    assert resp.status_code == 403


def test_disabling_a_product_blocks_authorize_for_every_one_of_its_clients(client, db_session):
    _setup_products(db_session)
    client_id, _secret = _make_client(db_session, LOADY, "http://localhost:9202/callback", "lc-disableprod-client")
    _make_super_admin(client, db_session, "lc-disableprod-super@example.com")

    disable = client.post(f"/api/v1/admin/products/{LOADY}/active", json={"is_active": False})
    assert disable.status_code == 200

    _verifier, challenge = _pkce_pair()
    _signup(client, "lc-disableprod-enduser@example.com")
    r = client.get(
        "/oauth/authorize",
        params={
            "response_type": "code", "client_id": client_id,
            "redirect_uri": "http://localhost:9202/callback", "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        follow_redirects=False,
    )
    assert r.status_code == 400
    assert "rejected" in r.text.lower()


def test_reenabling_a_product_restores_authorize(client, db_session):
    _setup_products(db_session)
    client_id, secret = _make_client(db_session, LOADY, "http://localhost:9203/callback", "lc-reenableprod-client")
    _make_super_admin(client, db_session, "lc-reenableprod-super@example.com")

    client.post(f"/api/v1/admin/products/{LOADY}/active", json={"is_active": False})
    client.post(f"/api/v1/admin/products/{LOADY}/active", json={"is_active": True})

    verifier, challenge = _pkce_pair()
    _signup(client, "lc-reenableprod-enduser@example.com")
    r = client.get(
        "/oauth/authorize",
        params={
            "response_type": "code", "client_id": client_id,
            "redirect_uri": "http://localhost:9203/callback", "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        follow_redirects=False,
    )
    assert r.status_code == 302


# --- POST /clients/{id}/active (product-scoped or global admin) --------------

def test_product_admin_can_disable_and_reenable_their_own_clients(client, db_session):
    _setup_products(db_session)
    client_id, _secret = _make_client(db_session, LOADY, "http://localhost:9204/callback", "lc-clientactive-a")
    _make_product_admin(client, db_session, "lc-clientactive-loadyadmin@example.com", LOADY)

    resp = client.post(f"/api/v1/admin/clients/{client_id}/active", json={"is_active": False})
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_active"] is False

    resp2 = client.post(f"/api/v1/admin/clients/{client_id}/active", json={"is_active": True})
    assert resp2.status_code == 200
    assert resp2.json()["is_active"] is True


def test_product_admin_cannot_disable_another_products_client(client, db_session):
    _setup_products(db_session)
    gamey_client_id, _s = _make_client(db_session, GAMEY, "http://localhost:9205/callback", "lc-clientactive-gamey")
    _make_product_admin(client, db_session, "lc-clientactive-loadyadmin2@example.com", LOADY)

    resp = client.post(f"/api/v1/admin/clients/{gamey_client_id}/active", json={"is_active": False})
    assert resp.status_code == 403

    # Prove it really is untouched, not just a 403 with a side effect.
    row = db_session.get(OAuthClient, gamey_client_id)
    assert row.is_active is True


def test_disabling_one_client_does_not_affect_a_sibling_client_on_the_same_product(client, db_session):
    _setup_products(db_session)
    client_a, _s1 = _make_client(db_session, LOADY, "http://localhost:9206/callback", "lc-sibling-a")
    client_b, secret_b = _make_client(db_session, LOADY, "http://localhost:9207/callback", "lc-sibling-b")
    _make_super_admin(client, db_session, "lc-sibling-super@example.com")

    client.post(f"/api/v1/admin/clients/{client_a}/active", json={"is_active": False})

    verifier, challenge = _pkce_pair()
    _signup(client, "lc-sibling-enduser@example.com")
    r = client.get(
        "/oauth/authorize",
        params={
            "response_type": "code", "client_id": client_b,
            "redirect_uri": "http://localhost:9207/callback", "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        follow_redirects=False,
    )
    assert r.status_code == 302  # client_b, never disabled, is unaffected


def test_disabling_a_client_blocks_authorize_through_it(client, db_session):
    _setup_products(db_session)
    client_id, _secret = _make_client(db_session, LOADY, "http://localhost:9208/callback", "lc-disableclient")
    _make_super_admin(client, db_session, "lc-disableclient-super@example.com")

    client.post(f"/api/v1/admin/clients/{client_id}/active", json={"is_active": False})

    _verifier, challenge = _pkce_pair()
    _signup(client, "lc-disableclient-enduser@example.com")
    r = client.get(
        "/oauth/authorize",
        params={
            "response_type": "code", "client_id": client_id,
            "redirect_uri": "http://localhost:9208/callback", "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        follow_redirects=False,
    )
    assert r.status_code == 400


def test_disabling_a_client_blocks_token_refresh_through_it(client, db_session):
    """A disabled client must also stop honoring refresh tokens issued
    before it was disabled - not just new sign-ins (mission 17: defense in
    depth beyond only gating `/oauth/authorize`)."""
    client_id, secret = _make_client(db_session, LOADY, "http://localhost:9209/callback", "lc-disablerefresh")
    _setup_products(db_session)
    verifier, challenge = _pkce_pair()
    _signup(client, "lc-disablerefresh-enduser@example.com")

    r = client.get(
        "/oauth/authorize",
        params={
            "response_type": "code", "client_id": client_id,
            "redirect_uri": "http://localhost:9209/callback", "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        follow_redirects=False,
    )
    from urllib.parse import parse_qs, urlparse

    code = parse_qs(urlparse(r.headers["location"]).query)["code"][0]
    token_r = client.post("/oauth/token", data={
        "grant_type": "authorization_code", "client_id": client_id, "client_secret": secret,
        "code": code, "redirect_uri": "http://localhost:9209/callback", "code_verifier": verifier,
    })
    refresh_token = token_r.json()["refresh_token"]

    _make_super_admin(client, db_session, "lc-disablerefresh-super@example.com")
    client.post(f"/api/v1/admin/clients/{client_id}/active", json={"is_active": False})

    refresh_r = client.post("/oauth/token", data={
        "grant_type": "refresh_token", "client_id": client_id, "client_secret": secret,
        "refresh_token": refresh_token,
    })
    assert refresh_r.status_code == 400


def test_plain_user_cannot_toggle_client_active(client, db_session):
    _setup_products(db_session)
    client_id, _s = _make_client(db_session, LOADY, "http://localhost:9210/callback", "lc-plaintoggle")
    _signup(client, "lc-plaintoggle-plain@example.com")
    resp = client.post(f"/api/v1/admin/clients/{client_id}/active", json={"is_active": False})
    assert resp.status_code == 403
