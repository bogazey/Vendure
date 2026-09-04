"""Signup, login, logout, session refresh, password reset, email verification.

Access + refresh tokens are set as httpOnly cookies here and nowhere else -
the response bodies never include the tokens themselves, so frontend
JavaScript can't read them (mitigates token theft via XSS).
"""
from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME, get_current_user, get_db
from app.config.commercial_settings import get_commercial_settings
from app.database.commercial_models import User
from app.models.commercial_schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    ResetPasswordRequest,
    SignupRequest,
    UserOut,
    VerifyEmailRequest,
)
from app.services.auth_service import AuthResult, auth_service
from app.services.rate_limit_service import login_limiter, password_reset_limiter, signup_limiter
from app.utils.exceptions import InvalidTokenError, RateLimitedError

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _set_session_cookies(response: Response, result: AuthResult) -> None:
    settings = get_commercial_settings()
    response.set_cookie(
        ACCESS_COOKIE_NAME,
        result.access_token,
        max_age=settings.access_token_ttl_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        domain=settings.cookie_domain,
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        result.refresh_token,
        max_age=settings.refresh_token_ttl_days * 24 * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        domain=settings.cookie_domain,
        path="/api/auth",
    )


def _clear_session_cookies(response: Response) -> None:
    settings = get_commercial_settings()
    response.delete_cookie(ACCESS_COOKIE_NAME, path="/", domain=settings.cookie_domain)
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/api/auth", domain=settings.cookie_domain)


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
    result = auth_service.login(db, payload.email, payload.password)
    _set_session_cookies(response, result)
    return UserOut.model_validate(result.user, from_attributes=True)


@router.post("/logout", status_code=204, response_model=None)
async def logout(
    response: Response,
    db: Session = Depends(get_db),
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
) -> None:
    auth_service.logout(db, refresh_token)
    _clear_session_cookies(response)


@router.post("/refresh", response_model=UserOut)
async def refresh(
    response: Response,
    db: Session = Depends(get_db),
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
) -> UserOut:
    if not refresh_token:
        raise InvalidTokenError("Your session has expired. Please sign in again.")
    result = auth_service.refresh(db, refresh_token)
    _set_session_cookies(response, result)
    return UserOut.model_validate(result.user, from_attributes=True)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user, from_attributes=True)


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
async def resend_verification(
    request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> None:
    if not password_reset_limiter.allow(_client_key(request), max_events=5, window_seconds=3600):
        raise RateLimitedError("Too many requests. Please try again later.")
    if not user.email_verified:
        auth_service.request_email_verification(db, user)
