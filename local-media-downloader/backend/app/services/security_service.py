"""Password hashing and JWT token issuance/verification.

Password hashing uses Argon2id (via argon2-cffi's high-level PasswordHasher,
which defaults to argon2id with reasonable modern parameters). JWTs are
short-lived access tokens plus longer-lived, individually-revocable refresh
tokens (see database/commercial_models.RefreshToken) - both are delivered as
httpOnly cookies, never handed to frontend JavaScript.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError

from app.config.commercial_settings import get_commercial_settings

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True if the hash was made with outdated parameters and should be
    re-hashed next time the user successfully authenticates."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


# --- JWT access tokens -------------------------------------------------

def create_access_token(user_id: str, role: str) -> str:
    settings = get_commercial_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any] | None:
    settings = get_commercial_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != "access":
        return None
    return payload


# --- Refresh tokens (opaque, server-verified by hash) -------------------

def generate_refresh_token() -> tuple[str, str, datetime]:
    """Returns (raw_token_for_cookie, sha256_hash_for_db, expires_at)."""
    settings = get_commercial_settings()
    raw = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_ttl_days)
    return raw, token_hash, expires_at


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


# --- Generic single-use tokens (password reset / email verification) ----

def generate_single_use_token(ttl_hours: int) -> tuple[str, str, datetime]:
    raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
    return raw, token_hash, expires_at


def hash_single_use_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
