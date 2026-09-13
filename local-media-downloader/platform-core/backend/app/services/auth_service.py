"""Signup, login, central-session lifecycle, password reset, email
verification — the same shape as Loady's proven `auth_service.py`, moved
here as the one, central, cross-product identity authority (mission-brief
section 20: "products must NEVER receive plaintext passwords or central
password hashes").
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.logging_config import get_logger
from app.config.settings import get_settings
from app.database.models import EmailVerificationToken, PasswordResetToken, RefreshToken, User
from app.models.enums import UserStatus
from app.security import passwords
from app.security.tokens import generate_hashed_token, hash_token
from app.services import email_service
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
    def __init__(self, user: User, refresh_raw: str, remember_me: bool) -> None:
        self.user = user
        self.refresh_raw = refresh_raw
        self.remember_me = remember_me


class AuthService:
    def signup(self, session: Session, email: str, password: str) -> AuthResult:
        email = _normalize_email(email)
        existing = session.execute(select(User).where(User.email == email)).scalars().first()
        if existing is not None:
            raise EmailAlreadyRegisteredError("An account with that email already exists.")

        user = User(
            email=email,
            password_hash=passwords.hash_password(password),
            email_verified=False,
            status=UserStatus.ACTIVE.value,
        )
        session.add(user)
        session.flush()

        self._issue_verification_email(session, user)
        refresh_raw = self._issue_session(session, user, remember_me=True)
        logger.info("Signup: new global user %s", user.id)
        return AuthResult(user, refresh_raw, remember_me=True)

    def login(self, session: Session, email: str, password: str, remember_me: bool = False) -> AuthResult:
        email = _normalize_email(email)
        user = session.execute(select(User).where(User.email == email)).scalars().first()
        # Constant-time-ish: always run the hasher, even for a missing
        # user, so "no such account" and "wrong password" take the same
        # time (mitigates email enumeration via a timing side channel).
        password_hash = user.password_hash if user else passwords.hash_password("placeholder-timing-guard")
        password_ok = passwords.verify_password(password, password_hash)

        if user is None or not password_ok:
            raise InvalidCredentialsError("Incorrect email or password.")
        if user.status != UserStatus.ACTIVE.value:
            raise AccountDisabledError("This account has been disabled.")

        if passwords.needs_rehash(user.password_hash):
            user.password_hash = passwords.hash_password(password)

        refresh_raw = self._issue_session(session, user, remember_me=remember_me)
        logger.info("Login: global user %s", user.id)
        return AuthResult(user, refresh_raw, remember_me=remember_me)

    def refresh(self, session: Session, raw_refresh_token: str) -> AuthResult:
        token_hash = hash_token(raw_refresh_token)
        record = session.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash)).scalars().first()
        now = datetime.now(timezone.utc)
        if record is None or record.revoked_at is not None or record.expires_at < now:
            raise InvalidTokenError("Your session has expired. Please sign in again.")

        user = session.get(User, record.user_id)
        if user is None or user.status != UserStatus.ACTIVE.value:
            raise AccountDisabledError("This account is no longer active.")

        # Rotate: revoke the presented token, issue a fresh one under the
        # SAME session row identity concept (a new row, old one revoked) so
        # a leaked-and-reused refresh token is detectable/limited.
        remember_me = record.remember_me
        record.revoked_at = now
        refresh_raw = self._issue_session(session, user, remember_me=remember_me)
        return AuthResult(user, refresh_raw, remember_me=remember_me)

    def logout(self, session: Session, raw_refresh_token: str | None) -> None:
        if not raw_refresh_token:
            return
        token_hash = hash_token(raw_refresh_token)
        record = session.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash)).scalars().first()
        if record is not None and record.revoked_at is None:
            record.revoked_at = datetime.now(timezone.utc)

    def logout_all_sessions(self, session: Session, user_id: str) -> int:
        now = datetime.now(timezone.utc)
        records = session.execute(
            select(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        ).scalars().all()
        for record in records:
            record.revoked_at = now
        return len(records)

    def list_active_sessions(self, session: Session, user_id: str) -> list[RefreshToken]:
        now = datetime.now(timezone.utc)
        return list(
            session.execute(
                select(RefreshToken)
                .where(
                    RefreshToken.user_id == user_id,
                    RefreshToken.revoked_at.is_(None),
                    RefreshToken.expires_at > now,
                )
                .order_by(RefreshToken.last_used_at.desc())
            ).scalars().all()
        )

    def request_password_reset(self, session: Session, email: str) -> None:
        email = _normalize_email(email)
        user = session.execute(select(User).where(User.email == email)).scalars().first()
        if user is None:
            return  # Never reveal whether the account exists.
        raw, token_hash, expires_at = generate_hashed_token(timedelta(hours=1))
        session.add(PasswordResetToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
        settings = get_settings()
        reset_url = f"{settings.platform_auth_base_url}/reset-password?token={raw}"
        email_service.send_password_reset_email(user.email, reset_url)

    def reset_password(self, session: Session, raw_token: str, new_password: str) -> None:
        token_hash = hash_token(raw_token)
        record = session.execute(
            select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
        ).scalars().first()
        now = datetime.now(timezone.utc)
        if record is None or record.used_at is not None or record.expires_at < now:
            raise InvalidTokenError("This password reset link is invalid or has expired.")

        user = session.get(User, record.user_id)
        if user is None:
            raise InvalidTokenError("This password reset link is invalid or has expired.")

        user.password_hash = passwords.hash_password(new_password)
        record.used_at = now
        self.logout_all_sessions(session, user.id)
        logger.info("Password reset completed for global user %s", user.id)

    def change_password(self, session: Session, user: User, current_password: str, new_password: str) -> None:
        if not passwords.verify_password(current_password, user.password_hash):
            raise InvalidCredentialsError("Current password is incorrect.")
        user.password_hash = passwords.hash_password(new_password)

    def request_email_verification(self, session: Session, user: User) -> None:
        self._issue_verification_email(session, user)

    def verify_email(self, session: Session, raw_token: str) -> None:
        token_hash = hash_token(raw_token)
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
        raw, token_hash, expires_at = generate_hashed_token(timedelta(hours=48))
        session.add(EmailVerificationToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
        settings = get_settings()
        verify_url = f"{settings.platform_auth_base_url}/verify-email?token={raw}"
        email_service.send_verification_email(user.email, verify_url)

    def _issue_session(self, session: Session, user: User, remember_me: bool = True) -> str:
        settings = get_settings()
        raw, token_hash, expires_at = generate_hashed_token(timedelta(days=settings.refresh_token_ttl_days))
        session.add(
            RefreshToken(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=expires_at,
                remember_me=remember_me,
            )
        )
        return raw


auth_service = AuthService()
