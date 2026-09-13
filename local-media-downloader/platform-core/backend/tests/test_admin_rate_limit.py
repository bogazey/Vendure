"""Grand Admin mutation rate limiting (mission 4, phase 10) — bounds how
fast a single admin identity can perform sensitive mutations, so a
compromised session or a runaway script can't hammer the API unbounded."""
from __future__ import annotations

from app.database.models import User
from app.models.enums import GLOBAL_SCOPE, RoleSlug
from app.services import rbac_service


def _make_super_admin(client, db_session, email: str) -> User:
    r = client.post("/api/v1/auth/signup", json={"email": email, "password": "correct-horse-battery"})
    assert r.status_code == 201
    user = db_session.query(User).filter_by(email=email).first()
    rbac_service.assign_role(db_session, user, RoleSlug.SUPER_ADMIN, GLOBAL_SCOPE, granted_by=None)
    db_session.commit()
    return user


def _make_target_user(db_session, email: str) -> User:
    from app.security.passwords import hash_password

    user = User(email=email, password_hash=hash_password("correct-horse-battery"), email_verified=True)
    db_session.add(user)
    db_session.commit()
    return user


def test_admin_mutation_endpoint_is_rate_limited_after_repeated_calls(client, db_session):
    _make_super_admin(client, db_session, "rl-admin@example.com")
    target = _make_target_user(db_session, "rl-target@example.com")

    statuses = []
    for i in range(65):
        r = client.patch(
            f"/api/v1/admin/users/{target.id}/status",
            json={"status": "active" if i % 2 == 0 else "disabled"},
        )
        statuses.append(r.status_code)

    assert 429 in statuses, "expected the admin mutation limiter to eventually kick in"
    # Everything before the limiter engaged should have succeeded normally.
    first_429 = statuses.index(429)
    assert all(s == 200 for s in statuses[:first_429])


def test_admin_mutation_limit_is_scoped_per_admin_not_global(client, db_session):
    admin_a = _make_super_admin(client, db_session, "rl-admin-a@example.com")
    target = _make_target_user(db_session, "rl-target-b@example.com")

    for i in range(60):
        r = client.patch(
            f"/api/v1/admin/users/{target.id}/status",
            json={"status": "active" if i % 2 == 0 else "disabled"},
        )
        assert r.status_code == 200

    # admin_a is now at/near its own limit; a different admin must be
    # unaffected (keyed by admin id, not a shared/global counter).
    client.cookies.clear()
    _make_super_admin(client, db_session, "rl-admin-b@example.com")
    r = client.patch(f"/api/v1/admin/users/{target.id}/status", json={"status": "active"})
    assert r.status_code == 200
