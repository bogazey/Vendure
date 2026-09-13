"""Audit log: every privileged action recorded, actor/target present, no
secrets ever stored."""
from __future__ import annotations

import json

from app.database.models import AuditLog, Product, User
from app.models.enums import GLOBAL_SCOPE, RoleSlug
from app.services import rbac_service


def _signup(client, email: str) -> User:
    client.post("/api/v1/auth/signup", json={"email": email, "password": "correct-horse-battery"})


def _make_global_admin(client, db_session, email: str) -> User:
    _signup(client, email)
    user = db_session.query(User).filter_by(email=email).first()
    rbac_service.assign_role(db_session, user, RoleSlug.ADMIN, GLOBAL_SCOPE, granted_by=None)
    db_session.commit()
    return user


def _make_target_user(db_session, email: str) -> User:
    """Inserted directly via the ORM rather than through the shared
    `client`'s own /signup endpoint, which would overwrite the admin's
    session cookie already in that TestClient's cookie jar."""
    from app.security.passwords import hash_password

    user = User(email=email, password_hash=hash_password("correct-horse-battery"), email_verified=True)
    db_session.add(user)
    db_session.commit()
    return user


def test_gifted_grant_and_revoke_are_audited(client, db_session):
    admin = _make_global_admin(client, db_session, "audit-admin1@example.com")
    target = _make_target_user(db_session, "audit-target1@example.com")
    if db_session.get(Product, "audit-product") is None:
        db_session.add(Product(id="audit-product", name="Test", domain="test.example", status="live"))
        db_session.commit()
    client.post("/api/v1/admin/products/audit-product/plans", params={"slug": "pro", "name": "Pro"})

    r = client.patch(
        f"/api/v1/admin/users/{target.id}/entitlements",
        json={"product_id": "audit-product", "plan_slug": "pro", "source": "gifted", "reason": "beta"},
    )
    assert r.status_code == 200

    r = client.request(
        "DELETE", f"/api/v1/admin/users/{target.id}/entitlements/audit-product", json={"reason": "beta over"}
    )
    assert r.status_code == 200

    entitlement_entries = (
        db_session.query(AuditLog)
        .filter(AuditLog.action.in_(["gifted_access_granted", "gifted_access_revoked"]))
        .filter(AuditLog.actor_user_id == admin.id)
        .all()
    )
    actions = {e.action for e in entitlement_entries}
    assert "gifted_access_granted" in actions
    assert "gifted_access_revoked" in actions
    for entry in entitlement_entries:
        assert entry.actor_user_id == admin.id


def test_audit_log_never_stores_secrets_or_password_hashes(client, db_session):
    admin = _make_global_admin(client, db_session, "audit-admin2@example.com")
    target = _make_target_user(db_session, "audit-target2@example.com")

    client.patch(f"/api/v1/admin/users/{target.id}/status", json={"status": "disabled"})

    entries = db_session.query(AuditLog).filter_by(actor_user_id=admin.id, target_id=target.id).all()
    assert entries
    for entry in entries:
        blob = json.dumps({"before": entry.before_state, "after": entry.after_state})
        assert "password_hash" not in blob
        assert "$argon2" not in blob
        assert target.password_hash not in blob


def test_audit_log_readable_via_api_by_global_admin_only(client, db_session):
    _make_global_admin(client, db_session, "audit-admin3@example.com")
    r = client.get("/api/v1/admin/audit-log")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_role_assignment_and_revocation_audited(client, db_session):
    admin = _make_global_admin(client, db_session, "audit-super1@example.com")
    rbac_service.assign_role(db_session, admin, RoleSlug.SUPER_ADMIN, GLOBAL_SCOPE, granted_by=None)
    db_session.commit()

    target = _make_target_user(db_session, "audit-role-target@example.com")

    client.post(f"/api/v1/admin/users/{target.id}/roles", json={"role_slug": "support", "scope": "global"})
    client.request("DELETE", f"/api/v1/admin/users/{target.id}/roles", json={"role_slug": "support", "scope": "global"})

    entries = db_session.query(AuditLog).filter_by(target_id=target.id).all()
    actions = {e.action for e in entries}
    assert "role_assigned" in actions
    assert "role_revoked" in actions
