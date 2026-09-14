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
from app.database.models import EmailChangeToken, EmailVerificationToken, OAuthRefreshToken, PasswordResetToken, RefreshToken, User
from app.models.enums import AuditAction, UserStatus
from app.security import passwords
from app.security.tokens import generate_hashed_token, hash_token
from app.services import audit_service, email_service
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
        audit_service.record(session, user.id, AuditAction.USER_SIGNUP, "user", user.id)
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
        audit_service.record(session, user.id, AuditAction.USER_LOGIN, "user", user.id)
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
        """Ecosystem-wide sign-out foundation (mission-brief Phase 22).
        Three things happen together, all in the same transaction:

        1. Every central `RefreshToken` is revoked (as before) - no
           product/account-portal session can silently renew its central
           access token.
        2. `User.security_epoch` is bumped - any already-issued, still-
           unexpired central `session_access` JWT is rejected on its very
           next use (`api/deps.py::get_optional_user`), rather than
           living out its remaining `access_token_ttl_minutes`.
        3. Every product-scoped `OAuthRefreshToken` is revoked too - no
           product backend can silently mint a fresh OIDC access token
           for this user after this call, even though this function lives
           in Platform Core and never touches a product's own code.

        Documented, bounded SLA (never claimed as instant): an already-
        issued OIDC *access* token a product is holding (not a refresh
        token) remains valid for up to `OIDC_ACCESS_TOKEN_TTL_MINUTES`
        (default 15) after this call - the same bounded-propagation
        precedent `SESSION_REVOCATION.md` already established for account
        disable."""
        now = datetime.now(timezone.utc)
        records = session.execute(
            select(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        ).scalars().all()
        for record in records:
            record.revoked_at = now

        oauth_records = session.execute(
            select(OAuthRefreshToken).where(OAuthRefreshToken.user_id == user_id, OAuthRefreshToken.revoked_at.is_(None))
        ).scalars().all()
        for record in oauth_records:
            record.revoked_at = now

        user = session.get(User, user_id)
        if user is not None:
            user.security_epoch += 1

        audit_service.record(
            session, user_id, AuditAction.ALL_SESSIONS_REVOKED, "user", user_id,
            after_state={"central_sessions_revoked": len(records), "product_sessions_revoked": len(oauth_records)},
        )
        return len(records)

    def revoke_session(self, session: Session, user: User, session_id: str) -> bool:
        """Sign out ONE specific device/session (mission-brief Phase 21),
        as opposed to `logout_all_sessions`'s "everywhere." IDOR-safe by
        construction: the row must belong to the calling user, checked in
        the same query, not as a separate lookup-then-compare step a
        future refactor could accidentally drop."""
        record = session.execute(
            select(RefreshToken).where(RefreshToken.id == session_id, RefreshToken.user_id == user.id)
        ).scalars().first()
        if record is None or record.revoked_at is not None:
            return False
        record.revoked_at = datetime.now(timezone.utc)
        audit_service.record(session, user.id, AuditAction.SESSION_REVOKED, "refresh_token", record.id)
        return True

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

    def reissue_session(self, session: Session, user: User, remember_me: bool = True) -> str:
        """Public wrapper around `_issue_session` for a caller that has
        already independently authenticated the user by some other means
        this request (e.g. `routes_auth.change_password` re-authenticating
        the caller's own current session after `revoke_other_sessions`
        just revoked it out from under them) - never used to issue a
        session for anyone whose password/credentials weren't just
        verified in this same request."""
        return self._issue_session(session, user, remember_me=remember_me)

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
        audit_service.record(session, user.id, AuditAction.PASSWORD_CHANGED, "user", user.id)

    def request_email_change(self, session: Session, user: User, new_email: str) -> None:
        """Mission 6 continuation (Phase 19): `User.email` is NOT touched
        here - only `pending_new_email`, purely informational until the
        new address is actually verified. Never reveals whether
        `new_email` is already registered to someone else (mirrors
        `request_password_reset`'s "never reveal whether the account
        exists" discipline) - the collision is instead checked, and
        safely rejected, only at confirmation time."""
        new_email = _normalize_email(new_email)
        user.pending_new_email = new_email
        raw, token_hash, expires_at = generate_hashed_token(timedelta(hours=48))
        session.add(EmailChangeToken(user_id=user.id, new_email=new_email, token_hash=token_hash, expires_at=expires_at))
        settings = get_settings()
        verify_url = f"{settings.platform_auth_base_url}/verify-email-change?token={raw}"
        email_service.send_email_change_verification(new_email, verify_url)
        audit_service.record(session, user.id, AuditAction.EMAIL_CHANGE_REQUESTED, "user", user.id)

    def confirm_email_change(self, session: Session, raw_token: str) -> User:
        token_hash = hash_token(raw_token)
        record = session.execute(
            select(EmailChangeToken).where(EmailChangeToken.token_hash == token_hash)
        ).scalars().first()
        now = datetime.now(timezone.utc)
        if record is None or record.used_at is not None or record.expires_at < now:
            raise InvalidTokenError("This email-change link is invalid or has expired.")

        existing = session.execute(select(User).where(User.email == record.new_email)).scalars().first()
        if existing is not None and existing.id != record.user_id:
            raise EmailAlreadyRegisteredError("That email address is already in use by another account.")

        user = session.get(User, record.user_id)
        if user is None:
            raise InvalidTokenError("This email-change link is invalid or has expired.")

        old_email = user.email
        user.email = record.new_email
        user.pending_new_email = None
        record.used_at = now
        audit_service.record(
            session, user.id, AuditAction.EMAIL_CHANGED, "user", user.id,
            before_state={"email": old_email}, after_state={"email": user.email},
        )
        logger.info("Email change completed for global user %s", user.id)
        return user

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
