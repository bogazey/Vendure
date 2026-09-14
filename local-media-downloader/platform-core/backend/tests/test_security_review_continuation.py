"""Mission 6 continuation - security review round 2. Real findings found
and fixed during this pass, each with a regression test."""
from __future__ import annotations

from app.database.models import Product, User
from app.models.enums import GLOBAL_SCOPE, RoleSlug, product_scope
from app.services import catalog_service, rbac_service


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


def test_product_scoped_admin_cannot_fabricate_a_paddle_sourced_entitlement(client, db_session):
    """Finding: making the legacy entitlement-grant route product-scoped
    (so per-product admins could manage their own gifts) would otherwise
    have newly let them ALSO mark an entitlement as paddle-sourced with no
    real payment behind it - inflating paid-subscriber reports. Fixed:
    paddle/lifetime sources require a global admin regardless of product
    scope."""
    product_id = "secreview-product-a"
    if db_session.get(Product, product_id) is None:
        db_session.add(Product(id=product_id, name=product_id, domain=f"{product_id}.example", status="live"))
        db_session.commit()
    scoped_admin = _make_product_admin(client, db_session, "secreview-scoped1@example.com", product_id)
    system_admin = User(email="secreview-system1@example.com", password_hash="x", email_verified=True)
    target = User(email="secreview-target1@example.com", password_hash="x", email_verified=True)
    db_session.add_all([system_admin, target])
    db_session.flush()
    catalog_service.create_plan(db_session, system_admin, product_id, "pro", "Pro")
    db_session.commit()

    resp = client.patch(f"/api/v1/admin/users/{target.id}/entitlements", json={
        "product_id": product_id, "plan_slug": "pro", "source": "paddle", "expires_at": None, "reason": "fabricated",
    })
    assert resp.status_code == 403


def test_product_scoped_admin_can_still_grant_gifted_via_the_same_route(client, db_session):
    """The fix must not regress the legitimate case - a product-scoped
    admin granting a non-revenue source for their own product still works."""
    product_id = "secreview-product-b"
    if db_session.get(Product, product_id) is None:
        db_session.add(Product(id=product_id, name=product_id, domain=f"{product_id}.example", status="live"))
        db_session.commit()
    _make_product_admin(client, db_session, "secreview-scoped2@example.com", product_id)
    system_admin = User(email="secreview-system2@example.com", password_hash="x", email_verified=True)
    target = User(email="secreview-target2@example.com", password_hash="x", email_verified=True)
    db_session.add_all([system_admin, target])
    db_session.flush()
    catalog_service.create_plan(db_session, system_admin, product_id, "pro", "Pro")
    db_session.commit()

    resp = client.patch(f"/api/v1/admin/users/{target.id}/entitlements", json={
        "product_id": product_id, "plan_slug": "pro", "source": "internal", "expires_at": None, "reason": "legit",
    })
    assert resp.status_code == 200


def test_global_admin_can_still_grant_paddle_sourced_entitlements(client, db_session):
    product_id = "secreview-product-c"
    if db_session.get(Product, product_id) is None:
        db_session.add(Product(id=product_id, name=product_id, domain=f"{product_id}.example", status="live"))
        db_session.commit()
    _make_super_admin(client, db_session, "secreview-super1@example.com")
    target = User(email="secreview-target3@example.com", password_hash="x", email_verified=True)
    db_session.add(target)
    db_session.flush()
    admin_for_plan = db_session.query(User).filter_by(email="secreview-super1@example.com").first()
    catalog_service.create_plan(db_session, admin_for_plan, product_id, "pro", "Pro")
    db_session.commit()

    resp = client.patch(f"/api/v1/admin/users/{target.id}/entitlements", json={
        "product_id": product_id, "plan_slug": "pro", "source": "paddle", "expires_at": None, "reason": "real reconciliation",
    })
    assert resp.status_code == 200
