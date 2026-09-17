"""Mission 17: `GET /admin/oauth-clients` - the Grand Admin OAuth Clients
inventory page's data source. Scoped exactly like `GET /products`
(`admin_visible_product_ids`), distinct from and unchanged by
`GET /clients` (registration-adjacent, stays super_admin-only)."""
from __future__ import annotations

from app.database.models import OAuthClient, Product, User
from app.models.enums import GLOBAL_SCOPE, RoleSlug, product_scope
from app.services import oidc_service, rbac_service

LOADY = "oci-loady"
GAMEY = "oci-gamey"


def _signup(client, email: str) -> None:
    r = client.post("/api/v1/auth/signup", json={"email": email, "password": "correct-horse-battery"})
    assert r.status_code == 201, r.text


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


def _setup_products_and_clients(db_session):
    for pid in (LOADY, GAMEY):
        if db_session.get(Product, pid) is None:
            db_session.add(Product(id=pid, name=pid, domain=f"{pid}.example", status="live"))
    db_session.flush()
    actor = db_session.query(User).filter_by(email="oci-bootstrap@example.com").first()
    if actor is None:
        actor = User(email="oci-bootstrap@example.com", password_hash="x", email_verified=True)
        db_session.add(actor)
        db_session.flush()
    if db_session.get(OAuthClient, f"oci-client-{LOADY}") is None:
        oidc_service.register_client(db_session, actor, f"oci-client-{LOADY}", "Loady Client", LOADY, ["https://l.example/cb"])
    if db_session.get(OAuthClient, f"oci-client-{GAMEY}") is None:
        oidc_service.register_client(db_session, actor, f"oci-client-{GAMEY}", "Gamey Client", GAMEY, ["https://g.example/cb"])
    db_session.commit()


def test_global_admin_sees_every_products_clients(client, db_session):
    _setup_products_and_clients(db_session)
    _make_super_admin(client, db_session, "oci-super1@example.com")

    resp = client.get("/api/v1/admin/oauth-clients")
    assert resp.status_code == 200, resp.text
    product_ids = {row["product_id"] for row in resp.json()}
    assert {LOADY, GAMEY} <= product_ids


def test_product_scoped_admin_sees_only_their_own_products_clients(client, db_session):
    _setup_products_and_clients(db_session)
    _make_product_admin(client, db_session, "oci-loadyadmin1@example.com", LOADY)

    resp = client.get("/api/v1/admin/oauth-clients")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert all(r["product_id"] == LOADY for r in rows)
    assert any(r["client_id"] == f"oci-client-{LOADY}" for r in rows)
    assert not any(r["client_id"] == f"oci-client-{GAMEY}" for r in rows)


def test_response_never_includes_a_secret(client, db_session):
    _setup_products_and_clients(db_session)
    _make_super_admin(client, db_session, "oci-super2@example.com")

    resp = client.get("/api/v1/admin/oauth-clients")
    body_text = resp.text.lower()
    assert "secret" not in body_text
    assert "hash" not in body_text


def test_plain_user_is_rejected(client, db_session):
    _setup_products_and_clients(db_session)
    _signup(client, "oci-plain1@example.com")

    resp = client.get("/api/v1/admin/oauth-clients")
    assert resp.status_code == 403


def test_response_includes_post_logout_redirect_uris_field(client, db_session):
    _setup_products_and_clients(db_session)
    _make_super_admin(client, db_session, "oci-super3@example.com")

    resp = client.get("/api/v1/admin/oauth-clients")
    rows = resp.json()
    assert all("post_logout_redirect_uris" in r for r in rows)
