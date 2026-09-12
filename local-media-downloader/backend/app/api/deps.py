"""Shared FastAPI dependencies: DB session, current-user resolution from the
httpOnly access-token cookie, and role enforcement.
"""
from __future__ import annotations

from typing import Iterator, Optional

from fastapi import Cookie, Depends
from sqlalchemy.orm import Session

from app.database.commercial_db import get_session_factory
from app.database.commercial_models import User
from app.models.commercial_enums import UserRole, UserStatus
from app.services import guest_service, security_service
from app.utils.exceptions import AuthError, ForbiddenError

ACCESS_COOKIE_NAME = "lmd_access"
REFRESH_COOKIE_NAME = "lmd_refresh"
GUEST_COOKIE_NAME = "lmd_guest"
VISITOR_COOKIE_NAME = "lmd_visitor"


def get_db() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_optional_user(
    db: Session = Depends(get_db),
    access_token: Optional[str] = Cookie(default=None, alias=ACCESS_COOKIE_NAME),
) -> Optional[User]:
    if not access_token:
        return None
    payload = security_service.decode_access_token(access_token)
    if payload is None:
        return None
    user = db.get(User, payload.get("sub"))
    if user is None or user.status != UserStatus.ACTIVE.value:
        return None
    return user


def get_current_user(user: Optional[User] = Depends(get_optional_user)) -> User:
    if user is None:
        raise AuthError("Sign in to continue.")
    return user


def get_guest_id(
    db: Session = Depends(get_db),
    guest_token: Optional[str] = Cookie(default=None, alias=GUEST_COOKIE_NAME),
) -> Optional[str]:
    """Returns the caller's guest id only if their cookie matches a known,
    server-minted GuestQuota row - never trusts an unrecognized value as an
    identity (see guest_service.resolve_or_create, which is what actually
    mints new ones, called explicitly by the routes that need to)."""
    if not guest_token:
        return None
    if not guest_service.quota_exists(db, guest_token):
        return None
    return guest_token


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.ADMIN.value:
        raise ForbiddenError("Admin access required.")
    return user
