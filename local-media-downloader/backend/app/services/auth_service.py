"""Signup, login, session (access/refresh token) lifecycle, password reset,
and email verification.

Sessions are two JWT/opaque-token pairs delivered as httpOnly cookies (never
handed to frontend JS, never put in localStorage):
- access token: short-lived JWT (app.services.security_service), stateless.
- refresh token: opaque random string; only its SHA-256 hash is stored
  server-side (app.database.commercial_models.RefreshToken), so a single
  session can be revoked (logout, password reset) without a JWT blocklist.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.commercial_settings import get_commercial_settings
from app.config.logging_config import get_logger
from app.database.commercial_models import (
    EmailVerificationToken,
    PasswordResetToken,
    RefreshToken,
    User,
)
from app.models.commercial_enums import UserRole, UserStatus
from app.services import email_service, security_service
from app.utils.exceptions import (
    AccountDisabledError,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidTokenError,
)

logger = get_logger("auth")


def _normalize_email(email: str) -> str:
    return email.strip().lower()


class AuthResult:
    def __init__(self, user: User, access_token: str, refresh_token: str, remember_me: bool) -> None:
        self.user = user
        self.access_token = access_token
        self.refresh_token = refresh_token
        # "Keep me logged in" for this session - routes_auth._set_session_cookies
        # reads this to decide whether the cookies get a Max-Age (persistent,
        # survives browser restarts) or none at all (a true session cookie,
        # cleared once the browser closes).
        self.remember_me = remember_me


class AuthService:
    def signup(self, session: Session, email: str, password: str) -> AuthResult:
        email = _normalize_email(email)
        existing = session.execute(select(User).where(User.email == email)).scalars().first()
        if existing is not None:
            raise EmailAlreadyRegisteredError("An account with that email already exists.")

        user = User(
            email=email,
            password_hash=security_service.hash_password(password),
            email_verified=False,
            status=UserStatus.ACTIVE.value,
            role=UserRole.USER.value,
        )
        session.add(user)
        session.flush()

        self._issue_verification_email(session, user)
        # Signup has no "Keep me logged in" checkbox - preserves the
        # existing, always-persistent behavior a fresh signup had before
        # this option existed.
        access_token, refresh_token = self._issue_session(session, user, remember_me=True)
        logger.info("Signup: new user %s", user.id)
        return AuthResult(user, access_token, refresh_token, remember_me=True)

    def login(self, session: Session, email: str, password: str, remember_me: bool = False) -> AuthResult:
        email = _normalize_email(email)
        user = session.execute(select(User).where(User.email == email)).scalars().first()
        # Always run the hasher even on a missing user, so responses for
        # "no such account" and "wrong password" take the same time and
        # don't leak which case occurred via a timing side channel.
        password_hash = user.password_hash if user else security_service.hash_password("placeholder-timing-guard")
        password_ok = security_service.verify_password(password, password_hash)

        if user is None or not password_ok:
            raise InvalidCredentialsError("Incorrect email or password.")
        if user.status != UserStatus.ACTIVE.value:
            raise AccountDisabledError("This account has been disabled.")

        if security_service.needs_rehash(user.password_hash):
            user.password_hash = security_service.hash_password(password)

        access_token, refresh_token = self._issue_session(session, user, remember_me=remember_me)
        logger.info("Login: user %s", user.id)
        return AuthResult(user, access_token, refresh_token, remember_me=remember_me)

    def refresh(self, session: Session, raw_refresh_token: str) -> AuthResult:
        token_hash = security_service.hash_refresh_token(raw_refresh_token)
        record = session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        ).scalars().first()
        now = datetime.now(timezone.utc)
        if record is None or record.revoked_at is not None or record.expires_at < now:
            raise InvalidTokenError("Your session has expired. Please sign in again.")

        user = session.get(User, record.user_id)
        if user is None or user.status != UserStatus.ACTIVE.value:
            raise AccountDisabledError("This account is no longer active.")

        # Rotate: revoke the presented token and issue a fresh pair, so a
        # leaked-and-reused refresh token is detectable/limited. The new pair
        # carries forward the SAME remember_me the user originally chose at
        # login, so "Keep me logged in" keeps applying across every silent
        # rotation for the life of this session, not just the first token.
        remember_me = record.remember_me
        record.revoked_at = now
        access_token, refresh_token = self._issue_session(session, user, remember_me=remember_me)
        return AuthResult(user, access_token, refresh_token, remember_me=remember_me)

    def logout(self, session: Session, raw_refresh_token: str | None) -> None:
        if not raw_refresh_token:
            return
        token_hash = security_service.hash_refresh_token(raw_refresh_token)
        record = session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        ).scalars().first()
        if record is not None and record.revoked_at is None:
            record.revoked_at = datetime.now(timezone.utc)

    def request_password_reset(self, session: Session, email: str) -> None:
        email = _normalize_email(email)
        user = session.execute(select(User).where(User.email == email)).scalars().first()
        if user is None:
            # Do not reveal whether the account exists.
            return
        raw, token_hash, expires_at = security_service.generate_single_use_token(ttl_hours=1)
        session.add(PasswordResetToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
        settings = get_commercial_settings()
        reset_url = f"{settings.frontend_base_url}/reset-password?token={raw}"
        email_service.send_password_reset_email(user.email, reset_url)

    def reset_password(self, session: Session, raw_token: str, new_password: str) -> None:
        token_hash = security_service.hash_single_use_token(raw_token)
        record = session.execute(
            select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
        ).scalars().first()
        now = datetime.now(timezone.utc)
        if record is None or record.used_at is not None or record.expires_at < now:
            raise InvalidTokenError("This password reset link is invalid or has expired.")

        user = session.get(User, record.user_id)
        if user is None:
            raise InvalidTokenError("This password reset link is invalid or has expired.")

        user.password_hash = security_service.hash_password(new_password)
        record.used_at = now

        # Force re-login everywhere after a password reset.
        active_tokens = session.execute(
            select(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        ).scalars().all()
        for token in active_tokens:
            token.revoked_at = now
        logger.info("Password reset completed for user %s", user.id)

    def request_email_verification(self, session: Session, user: User) -> None:
        self._issue_verification_email(session, user)

    def verify_email(self, session: Session, raw_token: str) -> None:
        token_hash = security_service.hash_single_use_token(raw_token)
        record = session.execute(
            select(EmailVerificationToken).where(EmailVerificationToken.token_hash == token_hash)
        ).scalars().first()
        now = datetime.now(timezone.utc)
        if record is None or record.used_at is not None or record.expires_at < now:
            raise InvalidTokenError("This verification link is invalid or has expired.")

        user = session.get(User, record.user_id)
        if user is None:
            raise InvalidTokenError("This verification link is invalid or has expired.")

        user.email_verified = True
        record.used_at = now

    # --- internal helpers ---

    def _issue_verification_email(self, session: Session, user: User) -> None:
        raw, token_hash, expires_at = security_service.generate_single_use_token(ttl_hours=48)
        session.add(EmailVerificationToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
        settings = get_commercial_settings()
        verify_url = f"{settings.frontend_base_url}/verify-email?token={raw}"
        email_service.send_verification_email(user.email, verify_url)

    def _issue_session(self, session: Session, user: User, remember_me: bool = True) -> tuple[str, str]:
        access_token = security_service.create_access_token(user.id, user.role)
        raw_refresh, refresh_hash, expires_at = security_service.generate_refresh_token()
        session.add(
            RefreshToken(
                user_id=user.id, token_hash=refresh_hash, expires_at=expires_at, remember_me=remember_me,
            )
        )
        return access_token, raw_refresh


auth_service = AuthService()
