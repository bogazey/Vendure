"""Opaque, hashed tokens for everything that is NOT a signed JWT: central
session refresh tokens, email verification / password reset tokens,
authorization codes, and OAuth refresh tokens. Same pattern as Loady's
`security_service.py`: only a SHA-256 hash of the raw token is ever
persisted, so a stolen DB row alone cannot be replayed.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone


def new_raw_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_hashed_token(ttl: timedelta, nbytes: int = 32) -> tuple[str, str, datetime]:
    """Returns (raw_token, sha256_hash, expires_at)."""
    raw = new_raw_token(nbytes)
    return raw, hash_token(raw), datetime.now(timezone.utc) + ttl
