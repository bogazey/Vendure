"""Promote an existing user to the admin role.

Usage:
    python -m app.scripts.promote_admin <email>

There is deliberately no HTTP endpoint or self-service path for this (see
COMMERCIAL_ARCHITECTURE.md) - promoting an admin is a one-time, operator-run
action against the server's own database.

Safety properties:
- Only promotes a user that already exists (found by exact email match) -
  never creates an account.
- Idempotent: running it again against an existing admin reports that and
  makes no changes, rather than erroring.
- Takes no password, token, or other secret as input, and never prints one.
- Reports a clear "no user found" message rather than silently doing nothing.
"""
from __future__ import annotations

import sys

from sqlalchemy import select

from app.database.commercial_db import get_session_factory
from app.database.commercial_models import User
from app.models.commercial_enums import UserRole


def promote_admin(email: str) -> int:
    """Returns a process exit code: 0 on success (promoted or already
    admin), 1 if no such user exists."""
    session = get_session_factory()()
    try:
        user = session.execute(select(User).where(User.email == email)).scalars().first()
        if user is None:
            print(f"No user found with email: {email}")
            return 1
        if user.role == UserRole.ADMIN.value:
            print(f"{email} is already an admin. No changes made.")
            return 0
        user.role = UserRole.ADMIN.value
        session.commit()
        print(f"{email} has been promoted to admin.")
        return 0
    finally:
        session.close()


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1 or not args[0].strip():
        print("Usage: python -m app.scripts.promote_admin <email>")
        return 2
    return promote_admin(args[0].strip())


if __name__ == "__main__":
    raise SystemExit(main())
