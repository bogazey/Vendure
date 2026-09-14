"""Central identity: signup, login, logout, session refresh, password
reset, email verification, change password, active-session listing.
Cookies are httpOnly/SameSite=Lax and, in production, Secure — never
readable by JavaScript, exactly like Loady's own session cookies, and
scoped under a distinct name (`plat_*`) so a product's own cookies can
never collide with or be confused for Platform Core's.
"""
from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import SESSION_ACCESS_COOKIE, SESSION_REFRESH_COOKIE, get_current_user, get_db
from app.config.settings import get_settings
from app.database.models import User
from app.models.schemas import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    ResetPasswordRequest,
    SessionOut,
    SignupRequest,
    UserOut,
    VerifyEmailRequest,
)
from app.security.jwt_tokens import create_session_access_token
from app.security.tokens import hash_token
from app.services.auth_service import AuthResult, auth_service
from app.services.rate_limit_service import login_limiter, password_reset_limiter, signup_limiter
from app.utils.exceptions import InvalidTokenError, RateLimitedError

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _set_session_cookies(response: Response, result: AuthResult) -> None:
    settings = get_settings()
    access_token = create_session_access_token(result.user.id, result.user.security_epoch)
    access_max_age = settings.access_token_ttl_minutes * 60 if result.remember_me else None
    refresh_max_age = settings.refresh_token_ttl_days * 24 * 3600 if result.remember_me else None
    response.set_cookie(
        SESSION_ACCESS_COOKIE, access_token, max_age=access_max_age, httponly=True,
        secure=settings.cookie_secure, samesite="lax", domain=settings.cookie_domain, path="/",
    )
    response.set_cookie(
        SESSION_REFRESH_COOKIE, result.refresh_raw, max_age=refresh_max_age, httponly=True,
        secure=settings.cookie_secure, samesite="lax", domain=settings.cookie_domain,
        path="/api/v1/auth",
    )


def _clear_session_cookies(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(SESSION_ACCESS_COOKIE, path="/", domain=settings.cookie_domain)
    response.delete_cookie(SESSION_REFRESH_COOKIE, path="/api/v1/auth", domain=settings.cookie_domain)


@router.post("/signup", response_model=UserOut, status_code=201)
async def signup(payload: SignupRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> UserOut:
    if not signup_limiter.allow(_client_key(request), max_events=10, window_seconds=3600):
        raise RateLimitedError("Too many signup attempts. Please try again later.")
    result = auth_service.signup(db, payload.email, payload.password)
    _set_session_cookies(response, result)
    return UserOut.model_validate(result.user, from_attributes=True)


@router.post("/login", response_model=UserOut)
async def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> UserOut:
    key = f"{_client_key(request)}:{payload.email.lower()}"
    if not login_limiter.allow(key, max_events=10, window_seconds=300):
        raise RateLimitedError("Too many login attempts. Please wait a few minutes and try again.")
    result = auth_service.login(db, payload.email, payload.password, remember_me=payload.remember_me)
    _set_session_cookies(response, result)
    return UserOut.model_validate(result.user, from_attributes=True)


@router.post("/logout", status_code=204, response_model=None)
async def logout(
    response: Response, db: Session = Depends(get_db),
    session_refresh: str | None = Cookie(default=None, alias=SESSION_REFRESH_COOKIE),
) -> None:
    auth_service.logout(db, session_refresh)
    _clear_session_cookies(response)


@router.post("/logout-all", status_code=204, response_model=None)
async def logout_all(
    response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> None:
    auth_service.logout_all_sessions(db, user.id)
    _clear_session_cookies(response)


@router.post("/refresh", response_model=UserOut)
async def refresh(
    response: Response, db: Session = Depends(get_db),
    session_refresh: str | None = Cookie(default=None, alias=SESSION_REFRESH_COOKIE),
) -> UserOut:
    if not session_refresh:
        raise InvalidTokenError("Your session has expired. Please sign in again.")
    result = auth_service.refresh(db, session_refresh)
    _set_session_cookies(response, result)
    return UserOut.model_validate(result.user, from_attributes=True)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user, from_attributes=True)


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
    session_refresh: str | None = Cookie(default=None, alias=SESSION_REFRESH_COOKIE),
) -> list[SessionOut]:
    current_hash = hash_token(session_refresh) if session_refresh else None
    records = auth_service.list_active_sessions(db, user.id)
    return [
        SessionOut(
            id=r.id, device_label=r.device_label, created_at=r.created_at,
            last_used_at=r.last_used_at, expires_at=r.expires_at,
            is_current=(r.token_hash == current_hash),
        )
        for r in records
    ]


@router.post("/change-password", status_code=204, response_model=None)
async def change_password(
    payload: ChangePasswordRequest, response: Response, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> None:
    auth_service.change_password(db, user, payload.current_password, payload.new_password)
    if payload.revoke_other_sessions:
        auth_service.logout_all_sessions(db, user.id)
        # The caller's OWN current session must survive a password change
        # they just made themselves - re-issue fresh cookies bound to the
        # bumped epoch instead of leaving them logged out by their own action.
        db.flush()
        db.refresh(user)
        result = AuthResult(user, refresh_raw=auth_service.reissue_session(db, user, remember_me=True), remember_me=True)
        _set_session_cookies(response, result)


@router.delete("/sessions/{session_id}", status_code=204, response_model=None)
async def revoke_session(session_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> None:
    auth_service.revoke_session(db, user, session_id)


@router.post("/forgot-password", status_code=204, response_model=None)
async def forgot_password(payload: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)) -> None:
    if not password_reset_limiter.allow(_client_key(request), max_events=5, window_seconds=3600):
        raise RateLimitedError("Too many requests. Please try again later.")
    auth_service.request_password_reset(db, payload.email)


@router.post("/reset-password", status_code=204, response_model=None)
async def reset_password(payload: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)) -> None:
    if not password_reset_limiter.allow(_client_key(request), max_events=10, window_seconds=3600):
        raise RateLimitedError("Too many attempts. Please try again later.")
    auth_service.reset_password(db, payload.token, payload.new_password)


@router.post("/verify-email", status_code=204, response_model=None)
async def verify_email(payload: VerifyEmailRequest, request: Request, db: Session = Depends(get_db)) -> None:
    if not password_reset_limiter.allow(_client_key(request), max_events=10, window_seconds=3600):
        raise RateLimitedError("Too many attempts. Please try again later.")
    auth_service.verify_email(db, payload.token)


@router.post("/resend-verification", status_code=204, response_model=None)
async def resend_verification(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    if not password_reset_limiter.allow(_client_key(request), max_events=5, window_seconds=3600):
        raise RateLimitedError("Too many requests. Please try again later.")
    if not user.email_verified:
        auth_service.request_email_verification(db, user)
