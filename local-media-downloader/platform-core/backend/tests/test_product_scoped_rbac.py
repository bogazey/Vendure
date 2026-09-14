"""Mission 6 continuation (explicitly required): adversarial API tests
proving product-scoped RBAC is enforced at the BACKEND, not merely by
hiding UI controls. A "Loady admin" (RoleAssignment scoped to
`product:rbac-loady`) must be rejected by every route that touches
`rbac-gamey`'s catalog, gifts, subscriptions, payments, clients, or
global roles - and accepted for `rbac-loady`'s own."""
from __future__ import annotations

from app.database.models import OAuthClient, Plan, Product, User
from app.models.enums import GLOBAL_SCOPE, RoleSlug, product_scope
from app.services import catalog_service, oidc_service, rbac_service

LOADY = "rbac-loady"
GAMEY = "rbac-gamey"


def _signup(client, email: str) -> None:
    r = client.post("/api/v1/auth/signup", json={"email": email, "password": "correct-horse-battery"})
    assert r.status_code == 201


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


def _setup_two_products(db_session):
    for pid in (LOADY, GAMEY):
        if db_session.get(Product, pid) is None:
            db_session.add(Product(id=pid, name=pid, domain=f"{pid}.example", status="live"))
    db_session.flush()
    db_session.commit()


def test_loady_admin_can_manage_loady_plans(client, db_session):
    _setup_two_products(db_session)
    _make_product_admin(client, db_session, "loady-admin1@example.com", LOADY)

    resp = client.post(f"/api/v1/admin/catalog/products/{LOADY}/plans", json={"slug": "pro", "name": "Pro"})
    assert resp.status_code == 200, resp.text


def test_loady_admin_cannot_create_gamey_plans(client, db_session):
    _setup_two_products(db_session)
    _make_product_admin(client, db_session, "loady-admin2@example.com", LOADY)

    resp = client.post(f"/api/v1/admin/catalog/products/{GAMEY}/plans", json={"slug": "gamer-plus", "name": "Gamer+"})
    assert resp.status_code == 403


def test_loady_admin_cannot_list_gamey_plans(client, db_session):
    _setup_two_products(db_session)
    _make_product_admin(client, db_session, "loady-admin3@example.com", LOADY)

    resp = client.get(f"/api/v1/admin/catalog/products/{GAMEY}/plans")
    assert resp.status_code == 403


def test_loady_admin_cannot_edit_a_gamey_plan_by_id(client, db_session):
    """The critical IDOR-shaped check: even knowing GAMEY's plan_id
    directly (not going through the product_id path), a Loady-scoped
    admin must still be rejected."""
    _setup_two_products(db_session)
    admin_user = db_session.query(User).filter_by(email="bootstrap@nowhere.example").first()
    system_admin = User(email="system-rbac@example.com", password_hash="x", email_verified=True)
    db_session.add(system_admin)
    db_session.flush()
    gamey_plan = catalog_service.create_plan(db_session, system_admin, GAMEY, "elite", "Elite")
    db_session.commit()

    _make_product_admin(client, db_session, "loady-admin4@example.com", LOADY)
    resp = client.patch(f"/api/v1/admin/catalog/plans/{gamey_plan.id}", json={"name": "Hacked"})
    assert resp.status_code == 403


def test_loady_admin_cannot_create_a_price_on_a_gamey_plan(client, db_session):
    _setup_two_products(db_session)
    system_admin = User(email="system-rbac2@example.com", password_hash="x", email_verified=True)
    db_session.add(system_admin)
    db_session.flush()
    gamey_plan = catalog_service.create_plan(db_session, system_admin, GAMEY, "elite-price-a", "Elite")
    db_session.commit()

    _make_product_admin(client, db_session, "loady-admin5@example.com", LOADY)
    resp = client.post(f"/api/v1/admin/catalog/plans/{gamey_plan.id}/prices", json={
        "provider": "paddle", "currency": "usd", "amount_cents": 999, "interval": "month",
    })
    assert resp.status_code == 403


def test_loady_admin_cannot_retire_a_gamey_price(client, db_session):
    _setup_two_products(db_session)
    system_admin = User(email="system-rbac3@example.com", password_hash="x", email_verified=True)
    db_session.add(system_admin)
    db_session.flush()
    gamey_plan = catalog_service.create_plan(db_session, system_admin, GAMEY, "elite-price-b", "Elite")
    gamey_price = catalog_service.create_price(db_session, system_admin, gamey_plan, provider="paddle", currency="usd", amount_cents=999, interval="month")
    db_session.commit()

    _make_product_admin(client, db_session, "loady-admin6@example.com", LOADY)
    resp = client.post(f"/api/v1/admin/catalog/prices/{gamey_price.id}/retire", json={})
    assert resp.status_code == 403


def test_loady_admin_cannot_grant_a_gamey_gift(client, db_session):
    _setup_two_products(db_session)
    system_admin = User(email="system-rbac4@example.com", password_hash="x", email_verified=True)
    target = User(email="gift-target-rbac@example.com", password_hash="x", email_verified=True)
    db_session.add_all([system_admin, target])
    db_session.flush()
    catalog_service.create_plan(db_session, system_admin, GAMEY, "elite-gift-a", "Elite")
    db_session.commit()

    _make_product_admin(client, db_session, "loady-admin7@example.com", LOADY)
    resp = client.post(f"/api/v1/admin/users/{target.id}/gifts", json={
        "product_id": GAMEY, "plan_slug": "elite-gift-a", "reason": "should be denied",
    })
    assert resp.status_code == 403


def test_loady_admin_cannot_revoke_a_gamey_gift(client, db_session):
    _setup_two_products(db_session)
    system_admin = User(email="system-rbac5@example.com", password_hash="x", email_verified=True)
    target = User(email="gift-target-rbac2@example.com", password_hash="x", email_verified=True)
    db_session.add_all([system_admin, target])
    db_session.flush()
    gamey_plan = catalog_service.create_plan(db_session, system_admin, GAMEY, "elite2", "Elite2")
    db_session.commit()
    from app.services import gift_service

    gift = gift_service.grant_gift(db_session, system_admin, target, gamey_plan, "legit", None)
    db_session.commit()

    _make_product_admin(client, db_session, "loady-admin8@example.com", LOADY)
    resp = client.request("DELETE", f"/api/v1/admin/gifts/{gift.id}", json={"reason": "malicious"})
    assert resp.status_code == 403


def test_loady_admin_cannot_configure_gamey_client_webhook(client, db_session):
    _setup_two_products(db_session)
    system_admin = User(email="system-rbac6@example.com", password_hash="x", email_verified=True)
    db_session.add(system_admin)
    db_session.flush()
    gamey_client, _secret = oidc_service.register_client(db_session, system_admin, "rbac-gamey-client", "Gamey Client", GAMEY, [])
    db_session.commit()

    _make_product_admin(client, db_session, "loady-admin9@example.com", LOADY)
    resp = client.post(f"/api/v1/admin/clients/{gamey_client.client_id}/webhook", json={"webhook_url": "https://evil.example/hook"})
    assert resp.status_code == 403


def test_loady_admin_cannot_grant_service_scope_to_gamey_client(client, db_session):
    _setup_two_products(db_session)
    system_admin = User(email="system-rbac7@example.com", password_hash="x", email_verified=True)
    db_session.add(system_admin)
    db_session.flush()
    gamey_client, _secret = oidc_service.register_client(db_session, system_admin, "rbac-gamey-client2", "Gamey Client 2", GAMEY, [])
    db_session.commit()

    _make_product_admin(client, db_session, "loady-admin10@example.com", LOADY)
    resp = client.post(f"/api/v1/admin/clients/{gamey_client.client_id}/service-grants", json={"scope": "service:entitlements:read"})
    assert resp.status_code == 403


def test_loady_admin_cannot_register_new_oauth_clients_at_all(client, db_session):
    """Client registration stays super_admin-only even for the admin's
    OWN product - a product admin creating brand-new OAuth clients is a
    higher-privilege bootstrap operation, not a catalog operation."""
    _setup_two_products(db_session)
    _make_product_admin(client, db_session, "loady-admin11@example.com", LOADY)
    resp = client.post("/api/v1/admin/clients", json={
        "client_id": "sneaky-client", "name": "Sneaky", "product_id": LOADY, "redirect_uris": [],
    })
    assert resp.status_code == 403


def test_loady_admin_cannot_assign_global_roles_to_self_or_anyone(client, db_session):
    """The single most important escalation check: a product-scoped admin
    must never be able to grant themselves (or anyone) a GLOBAL role."""
    _setup_two_products(db_session)
    loady_admin = _make_product_admin(client, db_session, "loady-admin12@example.com", LOADY)

    resp = client.post(f"/api/v1/admin/users/{loady_admin.id}/roles", json={
        "role_slug": "super_admin", "scope": "global",
    })
    assert resp.status_code == 403


def test_loady_admin_cannot_assign_themselves_admin_on_gamey_either(client, db_session):
    """Nor can they grant themselves product-scoped admin on a DIFFERENT
    product - role assignment of any kind stays super_admin-only."""
    _setup_two_products(db_session)
    loady_admin = _make_product_admin(client, db_session, "loady-admin13@example.com", LOADY)

    resp = client.post(f"/api/v1/admin/users/{loady_admin.id}/roles", json={
        "role_slug": "admin", "scope": product_scope(GAMEY),
    })
    assert resp.status_code == 403


def test_loady_admin_sees_only_loady_gifts_in_cross_product_listing(client, db_session):
    _setup_two_products(db_session)
    system_admin = User(email="system-rbac8@example.com", password_hash="x", email_verified=True)
    target = User(email="gift-target-rbac3@example.com", password_hash="x", email_verified=True)
    db_session.add_all([system_admin, target])
    db_session.flush()
    loady_plan = catalog_service.create_plan(db_session, system_admin, LOADY, "creator", "Creator")
    gamey_plan = catalog_service.create_plan(db_session, system_admin, GAMEY, "elite3", "Elite3")
    db_session.commit()
    from app.services import gift_service

    gift_service.grant_gift(db_session, system_admin, target, loady_plan, "loady gift", None)
    gift_service.grant_gift(db_session, system_admin, target, gamey_plan, "gamey gift", None)
    db_session.commit()

    _make_product_admin(client, db_session, "loady-admin14@example.com", LOADY)
    resp = client.get(f"/api/v1/admin/users/{target.id}/gifts")
    assert resp.status_code == 200
    products_seen = {g["product_id"] for g in resp.json()}
    assert products_seen == {LOADY}


def test_loady_admin_sees_only_loady_payments_in_cross_product_listing(client, db_session):
    _setup_two_products(db_session)
    from datetime import datetime, timezone

    from app.database.models import PaymentRecord

    db_session.add_all([
        PaymentRecord(user_id="usr_x", product_id=LOADY, provider="paddle", provider_reference="ref1", amount_cents=100, currency="USD", status="completed"),
        PaymentRecord(user_id="usr_x", product_id=GAMEY, provider="paddle", provider_reference="ref2", amount_cents=200, currency="USD", status="completed"),
    ])
    db_session.commit()

    _make_product_admin(client, db_session, "loady-admin15@example.com", LOADY)
    resp = client.get("/api/v1/admin/payments")
    assert resp.status_code == 200
    products_seen = {p["product_id"] for p in resp.json()}
    assert GAMEY not in products_seen


def test_loady_admin_sees_only_loady_in_products_listing(client, db_session):
    """Regression: a product-scoped-only admin (no global role) has no
    other route into Grand Admin's product management UI than this
    listing endpoint - it must return their own product, filtered down
    from the full cross-product list, rather than 403 or leak Gamey."""
    _setup_two_products(db_session)
    _make_product_admin(client, db_session, "loady-admin-list@example.com", LOADY)

    resp = client.get("/api/v1/admin/products")
    assert resp.status_code == 200, resp.text
    ids = {p["id"] for p in resp.json()}
    assert LOADY in ids
    assert GAMEY not in ids


def test_super_admin_can_do_everything_across_both_products(client, db_session):
    """Sanity check the other direction: a global super_admin is not
    blocked by any of the product-scoping added above."""
    _setup_two_products(db_session)
    _make_super_admin(client, db_session, "super-rbac1@example.com")

    for product_id, slug in [(LOADY, "pro-super"), (GAMEY, "elite-super")]:
        resp = client.post(f"/api/v1/admin/catalog/products/{product_id}/plans", json={"slug": slug, "name": slug})
        assert resp.status_code == 200, resp.text


def test_plain_user_with_no_role_at_all_is_rejected_everywhere(client, db_session):
    _setup_two_products(db_session)
    _signup(client, "plain-user-rbac@example.com")

    assert client.get(f"/api/v1/admin/catalog/products/{LOADY}/plans").status_code == 403
    assert client.get("/api/v1/admin/payments").status_code == 403
    assert client.get(f"/api/v1/admin/users/x/gifts").status_code == 403
