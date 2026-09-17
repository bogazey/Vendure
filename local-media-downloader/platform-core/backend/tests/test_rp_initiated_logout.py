"""Mission 17: RP-Initiated-Logout (`GET /oauth/logout`) - a total gap
before this mission (the audit found zero `post_logout`/`end_session`
matches anywhere in Platform Core, and Loady's own local logout never
signaled Platform Core at all). Covers: valid-redirect-accepted,
invalid-redirect-rejected, and the no-session case, per the mission's own
explicit test list for this task."""
from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from app.database.models import Product, User
from app.services import oidc_service, service_auth
from app.api.deps import SESSION_ACCESS_COOKIE, SESSION_REFRESH_COOKIE


def _make_product_and_client(db_session, product_id: str, post_logout_uris: list[str]):
    if db_session.get(Product, product_id) is None:
        db_session.add(Product(id=product_id, name=product_id, domain=f"{product_id}.example", status="live"))
        db_session.flush()
    actor = User(email=f"bootstrap-{product_id}@example.com", password_hash="x", email_verified=True)
    db_session.add(actor)
    db_session.flush()
    client_obj, _secret = oidc_service.register_client(
        db_session, actor, client_id=f"logout-client-{product_id}", name=product_id, product_id=product_id,
        redirect_uris=["http://localhost:9999/callback"],
    )
    service_auth.set_post_logout_redirect_uris(db_session, actor, client_obj, post_logout_uris)
    db_session.commit()
    return client_obj.client_id


def test_logout_with_no_session_is_a_safe_noop(client, db_session):
    """Calling /oauth/logout without ever having signed in must not
    error - it's what makes "logout-all downstream products" safe to call
    blindly even for products the user never actually visited."""
    resp = client.get("/oauth/logout", follow_redirects=False)
    assert resp.status_code == 200
    assert "signed out" in resp.text.lower()


def test_logout_clears_the_central_session_cookies(client, db_session):
    r = client.post("/api/v1/auth/signup", json={"email": "rpl-user1@example.com", "password": "correct-horse-battery"})
    assert r.status_code == 201
    assert client.cookies.get(SESSION_ACCESS_COOKIE) is not None

    resp = client.get("/oauth/logout", follow_redirects=False)
    assert resp.status_code == 200
    # TestClient drops a cookie whose Set-Cookie response deletes it.
    assert client.cookies.get(SESSION_ACCESS_COOKIE) is None
    assert client.cookies.get(SESSION_REFRESH_COOKIE) is None


def test_logout_rejects_an_unregistered_redirect_uri(client, db_session):
    client_id = _make_product_and_client(db_session, "rpl-a", ["https://rpl-a.example/after-logout"])
    resp = client.get(
        "/oauth/logout",
        params={"client_id": client_id, "post_logout_redirect_uri": "https://evil.example/steal"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert "rejected" in resp.text.lower()


def test_logout_rejects_redirect_uri_with_unknown_client(client, db_session):
    resp = client.get(
        "/oauth/logout",
        params={"client_id": "does-not-exist", "post_logout_redirect_uri": "https://anything.example/x"},
        follow_redirects=False,
    )
    assert resp.status_code == 400


def test_logout_rejects_redirect_uri_with_no_client_id_supplied(client, db_session):
    resp = client.get(
        "/oauth/logout", params={"post_logout_redirect_uri": "https://anything.example/x"}, follow_redirects=False,
    )
    assert resp.status_code == 400


def test_logout_redirects_to_a_registered_uri(client, db_session):
    client_id = _make_product_and_client(db_session, "rpl-b", ["https://rpl-b.example/after-logout"])
    resp = client.get(
        "/oauth/logout",
        params={"client_id": client_id, "post_logout_redirect_uri": "https://rpl-b.example/after-logout"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "https://rpl-b.example/after-logout"


def test_logout_redirect_preserves_state(client, db_session):
    client_id = _make_product_and_client(db_session, "rpl-c", ["https://rpl-c.example/after-logout"])
    resp = client.get(
        "/oauth/logout",
        params={
            "client_id": client_id, "post_logout_redirect_uri": "https://rpl-c.example/after-logout",
            "state": "xyz-123",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    parsed = urlparse(resp.headers["location"])
    assert parse_qs(parsed.query)["state"] == ["xyz-123"]


def test_logout_ends_the_session_even_when_redirecting(client, db_session):
    client_id = _make_product_and_client(db_session, "rpl-d", ["https://rpl-d.example/after-logout"])
    r = client.post("/api/v1/auth/signup", json={"email": "rpl-user2@example.com", "password": "correct-horse-battery"})
    assert r.status_code == 201

    resp = client.get(
        "/oauth/logout",
        params={"client_id": client_id, "post_logout_redirect_uri": "https://rpl-d.example/after-logout"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert client.cookies.get(SESSION_ACCESS_COOKIE) is None

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 401


# --- admin config route -------------------------------------------------

def test_admin_can_set_post_logout_redirect_uris(client, db_session):
    from app.database.models import OAuthClient
    from app.models.enums import RoleSlug, product_scope
    from app.services import rbac_service

    if db_session.get(Product, "rpl-e") is None:
        db_session.add(Product(id="rpl-e", name="rpl-e", domain="rpl-e.example", status="live"))
        db_session.flush()
    actor = User(email="rpl-e-bootstrap@example.com", password_hash="x", email_verified=True)
    db_session.add(actor)
    db_session.flush()
    client_obj, _secret = oidc_service.register_client(
        db_session, actor, client_id="rpl-e-client", name="rpl-e", product_id="rpl-e",
        redirect_uris=["http://localhost:9999/callback"],
    )
    db_session.commit()

    r = client.post("/api/v1/auth/signup", json={"email": "rpl-e-admin@example.com", "password": "correct-horse-battery"})
    assert r.status_code == 201
    admin_user = db_session.query(User).filter_by(email="rpl-e-admin@example.com").first()
    rbac_service.assign_role(db_session, admin_user, RoleSlug.ADMIN, product_scope("rpl-e"), granted_by=None)
    db_session.commit()

    resp = client.post(
        f"/api/v1/admin/clients/{client_obj.client_id}/post-logout-redirect-uris",
        json={"post_logout_redirect_uris": ["https://rpl-e.example/after"]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["post_logout_redirect_uris"] == ["https://rpl-e.example/after"]

    row = db_session.get(OAuthClient, "rpl-e-client")
    db_session.refresh(row)
    assert row.post_logout_redirect_uris == ["https://rpl-e.example/after"]


def test_plain_user_cannot_set_post_logout_redirect_uris(client, db_session):
    client_id = _make_product_and_client(db_session, "rpl-f", [])
    client.post("/api/v1/auth/signup", json={"email": "rpl-f-plain@example.com", "password": "correct-horse-battery"})
    resp = client.post(
        f"/api/v1/admin/clients/{client_id}/post-logout-redirect-uris",
        json={"post_logout_redirect_uris": ["https://rpl-f.example/after"]},
    )
    assert resp.status_code == 403
