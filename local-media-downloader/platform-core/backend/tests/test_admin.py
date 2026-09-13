"""Grand Admin authorization boundaries and paid-entitlement protection."""
from __future__ import annotations

from app.database.models import Product, User
from app.models.enums import GLOBAL_SCOPE, RoleSlug
from app.services import rbac_service


def _signup(client, email: str) -> None:
    r = client.post("/api/v1/auth/signup", json={"email": email, "password": "correct-horse-battery"})
    assert r.status_code == 201


def _make_super_admin(client, db_session, email: str) -> User:
    _signup(client, email)
    user = db_session.query(User).filter_by(email=email).first()
    rbac_service.assign_role(db_session, user, RoleSlug.SUPER_ADMIN, GLOBAL_SCOPE, granted_by=None)
    db_session.commit()
    return user


def _make_global_admin(client, db_session, email: str) -> User:
    _signup(client, email)
    user = db_session.query(User).filter_by(email=email).first()
    rbac_service.assign_role(db_session, user, RoleSlug.ADMIN, GLOBAL_SCOPE, granted_by=None)
    db_session.commit()
    return user


def _make_target_user(db_session, email: str) -> User:
    """Inserted directly via the ORM, never through the shared `client`'s
    own /signup endpoint - that would overwrite the admin's session cookie
    already sitting in the same TestClient's cookie jar with the new
    target's session, silently switching who subsequent requests act as."""
    from app.security.passwords import hash_password

    user = User(email=email, password_hash=hash_password("correct-horse-battery"), email_verified=True)
    db_session.add(user)
    db_session.commit()
    return user


def test_anonymous_denied_overview(client):
    r = client.get("/api/v1/admin/overview")
    assert r.status_code == 401


def test_ordinary_user_denied_overview(client):
    _signup(client, "ordinary1@example.com")
    r = client.get("/api/v1/admin/overview")
    assert r.status_code == 403
    assert r.json()["code"] == "FORBIDDEN"


def test_product_scoped_role_does_not_grant_global_admin(client, db_session):
    """A user with role=admin scoped to one product must not be able to use
    the Grand Admin console at all (mission-brief section 46: no product
    can grant itself global admin privileges)."""
    _signup(client, "scoped-admin@example.com")
    user = db_session.query(User).filter_by(email="scoped-admin@example.com").first()
    rbac_service.assign_role(db_session, user, RoleSlug.ADMIN, "product:loady", granted_by=None)
    db_session.commit()

    r = client.get("/api/v1/admin/overview")
    assert r.status_code == 403


def test_global_admin_can_view_overview(client, db_session):
    _make_global_admin(client, db_session, "globaladmin1@example.com")
    r = client.get("/api/v1/admin/overview")
    assert r.status_code == 200
    body = r.json()
    assert "total_users" in body and "gifted_entitlements" in body
    assert body["revenue_available"] is False


def test_global_admin_cannot_assign_roles_only_super_admin_can(client, db_session):
    admin = _make_global_admin(client, db_session, "globaladmin2@example.com")
    target = _make_target_user(db_session, "target-role@example.com")

    r = client.post(f"/api/v1/admin/users/{target.id}/roles", json={"role_slug": "support", "scope": "global"})
    assert r.status_code == 403


def test_super_admin_can_assign_and_revoke_roles(client, db_session):
    _make_super_admin(client, db_session, "superadmin1@example.com")
    target = _make_target_user(db_session, "target-role2@example.com")

    r = client.post(f"/api/v1/admin/users/{target.id}/roles", json={"role_slug": "support", "scope": "global"})
    assert r.status_code == 200
    roles = [ra["role_slug"] for ra in r.json()["roles"]]
    assert "support" in roles

    r = client.request("DELETE", f"/api/v1/admin/users/{target.id}/roles", json={"role_slug": "support", "scope": "global"})
    assert r.status_code == 200
    roles = [ra["role_slug"] for ra in r.json()["roles"]]
    assert "support" not in roles


def test_admin_cannot_disable_own_account(client, db_session):
    admin = _make_global_admin(client, db_session, "selfdisable@example.com")
    r = client.patch(f"/api/v1/admin/users/{admin.id}/status", json={"status": "disabled"})
    assert r.status_code == 403


def test_grant_entitlement_via_admin_api(client, db_session):
    _make_global_admin(client, db_session, "globaladmin3@example.com")
    target = _make_target_user(db_session, "gift-target1@example.com")
    if db_session.get(Product, "admin-test-product") is None:
        db_session.add(Product(id="admin-test-product", name="Test", domain="test.example", status="live"))
        db_session.commit()

    r = client.post("/api/v1/admin/products/admin-test-product/plans", params={"slug": "pro", "name": "Pro"})
    assert r.status_code == 200

    r = client.patch(
        f"/api/v1/admin/users/{target.id}/entitlements",
        json={"product_id": "admin-test-product", "plan_slug": "pro", "source": "gifted", "reason": "beta tester"},
    )
    assert r.status_code == 200
    assert r.json()["source"] == "gifted"


def test_paid_entitlement_cannot_be_silently_overwritten_by_gift(client, db_session):
    _make_global_admin(client, db_session, "globaladmin4@example.com")
    target = _make_target_user(db_session, "paid-target1@example.com")
    if db_session.get(Product, "admin-paid-product") is None:
        db_session.add(Product(id="admin-paid-product", name="Test", domain="test.example", status="live"))
        db_session.commit()
    client.post("/api/v1/admin/products/admin-paid-product/plans", params={"slug": "pro", "name": "Pro"})

    # Simulate a real paid entitlement (as if a payment processor granted it).
    r = client.patch(
        f"/api/v1/admin/users/{target.id}/entitlements",
        json={"product_id": "admin-paid-product", "plan_slug": "pro", "source": "paddle"},
    )
    assert r.status_code == 200

    # Now try to silently replace it with a gifted one through the same control.
    r = client.patch(
        f"/api/v1/admin/users/{target.id}/entitlements",
        json={"product_id": "admin-paid-product", "plan_slug": "pro", "source": "gifted", "reason": "sneaky"},
    )
    assert r.status_code == 403

    r = client.request(
        "DELETE", f"/api/v1/admin/users/{target.id}/entitlements/admin-paid-product", json={"reason": "trying to revoke paid"}
    )
    assert r.status_code == 403
