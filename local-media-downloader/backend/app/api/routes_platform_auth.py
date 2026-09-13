"""Loady's central-identity sign-in entry points (docs/platform/
LOADY_IDENTITY_INTEGRATION.md). Every route here 404s outright unless
`PLATFORM_CLIENT_ID`/`PLATFORM_CLIENT_SECRET` are configured
(`platform_identity_service.is_configured()`) - this feature is dormant
by default and never partially engages.

Account linking rule (mission: "avoid unsafe automatic account merging
based solely on matching email"): a Loady user is matched by
`global_user_id` FIRST, always. Email is only ever used to link a Loady
user's very own account to its own first central login - never to merge
two different accounts, and never on any login after the first.
"""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Cookie, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.routes_auth import _set_session_cookies
from app.config.commercial_settings import get_commercial_settings
from app.database.commercial_models import User
from app.models.commercial_enums import UserRole, UserStatus
from app.services import platform_entitlement_service, platform_identity_service, security_service
from app.services.auth_service import AuthResult, auth_service
from app.utils.exceptions import AppError, ForbiddenError, InvalidTokenError

router = APIRouter(prefix="/api/auth/platform", tags=["platform-auth"])

_PKCE_VERIFIER_COOKIE = "plat_pkce_verifier"
_PKCE_STATE_COOKIE = "plat_pkce_state"
_NEXT_COOKIE = "plat_next"


class NotConfiguredError(AppError):
    status_code = 404
    code = "NOT_FOUND"


def _require_configured() -> None:
    if not platform_identity_service.is_configured():
        raise NotConfiguredError("Central identity sign-in is not configured.")


def _safe_next(raw: str | None) -> str:
    """Only a same-origin relative path is ever accepted - never an
    absolute URL, and never a protocol-relative `//host/path` (the classic
    open-redirect trick), per the mission's explicit redirect-allowlist
    instruction."""
    if raw and raw.startswith("/") and not raw.startswith("//") and "://" not in raw:
        return raw
    return "/dashboard"


@router.get("/status")
async def platform_status() -> dict:
    """Unauthenticated, non-sensitive: lets the frontend decide whether to
    show a central-identity sign-in option at all, without ever exposing
    the client id/secret or any OIDC terminology."""
    return {"enabled": platform_identity_service.is_configured()}


@router.get("/login")
async def platform_login(next: str | None = Query(default=None)):
    _require_configured()
    settings = get_commercial_settings()
    verifier, challenge = platform_identity_service.generate_pkce_pair()
    state = platform_identity_service.generate_state()
    authorize_url = platform_identity_service.build_authorize_url(challenge, state)

    redirect = RedirectResponse(url=authorize_url, status_code=302)
    redirect.set_cookie(_PKCE_VERIFIER_COOKIE, verifier, httponly=True, max_age=300,
                         secure=settings.cookie_secure, samesite="lax")
    redirect.set_cookie(_PKCE_STATE_COOKIE, state, httponly=True, max_age=300,
                         secure=settings.cookie_secure, samesite="lax")
    redirect.set_cookie(_NEXT_COOKIE, _safe_next(next), httponly=True, max_age=300,
                         secure=settings.cookie_secure, samesite="lax")
    return redirect


def _find_or_link_local_user(db: Session, sub: str, email: str, email_verified: bool) -> User:
    """Resolve the Loady-local account for a central identity's `sub`.
    Raises ForbiddenError on any collision rather than guessing - see
    module docstring."""
    email = email.strip().lower()

    matched = db.execute(select(User).where(User.global_user_id == sub)).scalars().first()
    if matched is not None:
        return matched

    same_email = db.execute(select(User).where(User.email == email)).scalars().first()
    if same_email is not None:
        if same_email.global_user_id is not None:
            # A different central identity already claims this email's
            # account - never silently re-link or merge.
            raise ForbiddenError(
                "This email is already linked to a different central identity account. "
                "Contact support to resolve this before signing in."
            )
        same_email.global_user_id = sub
        return same_email

    # Brand new account, created via central identity directly - no local
    # password exists for it; a random, never-typeable Argon2 hash keeps
    # `password_hash` a valid hash string without ever being guessable or
    # matchable by any real password.
    new_user = User(
        email=email,
        password_hash=security_service.hash_password(secrets.token_urlsafe(48)),
        email_verified=email_verified,
        status=UserStatus.ACTIVE.value,
        role=UserRole.USER.value,
        global_user_id=sub,
    )
    db.add(new_user)
    db.flush()
    return new_user


@router.get("/callback")
async def platform_callback(
    db: Session = Depends(get_db),
    code: str = Query(...),
    state: str = Query(...),
    pkce_verifier: str | None = Cookie(default=None, alias=_PKCE_VERIFIER_COOKIE),
    pkce_state: str | None = Cookie(default=None, alias=_PKCE_STATE_COOKIE),
    next_path: str | None = Cookie(default=None, alias=_NEXT_COOKIE),
):
    _require_configured()
    if not pkce_verifier or not pkce_state or state != pkce_state:
        raise InvalidTokenError("Central identity sign-in state mismatch - please try again.")

    oidc_tokens = platform_identity_service.exchange_code_for_tokens(code, pkce_verifier)
    claims = platform_identity_service.verify_id_token(oidc_tokens["id_token"])

    user = _find_or_link_local_user(db, claims["sub"], claims["email"], bool(claims.get("email_verified")))
    if user.status != UserStatus.ACTIVE.value:
        raise ForbiddenError("This account has been disabled.")

    # Kept so Loady's backend can later ask Platform Core for the
    # authoritative entitlement server-side without the user re-
    # authenticating - see platform_entitlement_service.py.
    platform_entitlement_service.store_tokens(
        db, user, oidc_tokens["access_token"], oidc_tokens["refresh_token"],
        oidc_tokens.get("expires_in", 900),
    )

    loady_access_token, loady_refresh_token = auth_service._issue_session(db, user, remember_me=True)
    result = AuthResult(user, loady_access_token, loady_refresh_token, remember_me=True)

    redirect = RedirectResponse(url=_safe_next(next_path), status_code=302)
    _set_session_cookies(redirect, result)
    redirect.delete_cookie(_PKCE_VERIFIER_COOKIE)
    redirect.delete_cookie(_PKCE_STATE_COOKIE)
    redirect.delete_cookie(_NEXT_COOKIE)
    return redirect
