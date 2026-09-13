"""Bootstrap the first Grand Admin super_admin — CLI-only, existing-user-
only, idempotent, no HTTP path to it whatsoever (same posture as Loady's
`promote_admin` script, and for the same reason: there must be no way for
any account to self-promote via the API).

Usage: python -m app.scripts.promote_super_admin <email>

Exit codes: 0 success (including "already a super admin"), 1 user not
found, 2 bad usage.
"""
from __future__ import annotations

import sys

from sqlalchemy import select

from app.database.db import get_session_factory
from app.database.models import User
from app.database.seed_roles import ensure_roles
from app.models.enums import GLOBAL_SCOPE, RoleSlug
from app.services import rbac_service


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python -m app.scripts.promote_super_admin <email>")
        return 2
    email = sys.argv[1].strip().lower()

    session = get_session_factory()()
    try:
        ensure_roles(session)
        user = session.execute(select(User).where(User.email == email)).scalars().first()
        if user is None:
            print(f"No user found with email '{email}'. They must sign up first.")
            return 1
        if rbac_service.is_super_admin(session, user.id):
            print(f"{email} is already a super_admin.")
            return 0
        rbac_service.assign_role(session, user, RoleSlug.SUPER_ADMIN, GLOBAL_SCOPE, granted_by=None)
        session.commit()
        print(f"{email} ({user.id}) promoted to super_admin.")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
