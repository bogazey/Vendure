"""Shared FastAPI dependencies: DB session, central-session user resolution
from the httpOnly cookie, bearer-token resolution for resource endpoints,
and RBAC enforcement."""
from __future__ import annotations

from typing import Iterator, Optional

from fastapi import Cookie, Depends, Header
from sqlalchemy.orm import Session

from app.database.db import get_session_factory
from app.database.models import OAuthClient, User
from app.models.enums import RoleSlug
from app.security.jwt_tokens import decode_session_access_token, introspect_oidc_access_token
from app.services import rbac_service
from app.services.rate_limit_service import admin_mutation_limiter
from app.utils.exceptions import AuthError, ForbiddenError, RateLimitedError

SESSION_ACCESS_COOKIE = "plat_session_access"
SESSION_REFRESH_COOKIE = "plat_session_refresh"


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
    session_access: Optional[str] = Cookie(default=None, alias=SESSION_ACCESS_COOKIE),
) -> Optional[User]:
    if not session_access:
        return None
    payload = decode_session_access_token(session_access)
    if payload is None:
        return None
    user = db.get(User, payload.get("sub"))
    if user is None or user.status != "active":
        return None
    return user


def get_current_user(user: Optional[User] = Depends(get_optional_user)) -> User:
    if user is None:
        raise AuthError("Sign in to continue.")
    return user


def require_global_admin(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> User:
    if not rbac_service.is_global_admin(db, user.id):
        raise ForbiddenError("Grand Admin access required.")
    return user


def require_super_admin(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> User:
    if not rbac_service.is_super_admin(db, user.id):
        raise ForbiddenError("Super admin access required.")
    return user


def rate_limit_admin_mutation(user: User = Depends(get_current_user)) -> None:
    """Applied to Grand Admin mutation routes (mission 4, phase 10) —
    bounds how fast any single admin identity can perform status changes,
    role grants, entitlement grants, or client registration, regardless of
    how the request was made (UI, script, or a stolen session). Keyed by
    admin user id, not IP, since a legitimate admin may operate from a
    shared/rotating office IP. Deliberately generous (60/min): this exists
    to catch a compromised session or a runaway script, not to slow down
    normal interactive admin work."""
    if not admin_mutation_limiter.allow(user.id, max_events=60, window_seconds=60):
        raise RateLimitedError("Too many admin actions in a short period. Please slow down.")


class BearerPrincipal:
    """The verified identity behind an `Authorization: Bearer <token>` call
    made BY a product's backend on behalf of one of its authenticated
    users — never a raw user-supplied claim (mission-brief section 24:
    `sub` is always taken from the verified JWT, `client` is always the
    verified `aud`, never client-supplied headers)."""

    def __init__(self, user: User, client: OAuthClient) -> None:
        self.user = user
        self.client = client


def get_bearer_principal(
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
) -> BearerPrincipal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError("Missing bearer token.")
    token = authorization[len("bearer "):].strip()
    payload = introspect_oidc_access_token(token)
    if payload is None:
        raise AuthError("Invalid or expired access token.")
    user = db.get(User, payload.get("sub"))
    if user is None or user.status != "active":
        raise AuthError("This account is no longer active.")
    client = db.get(OAuthClient, payload.get("aud"))
    if client is None or not client.is_active:
        raise AuthError("Unknown or inactive client.")
    return BearerPrincipal(user=user, client=client)
