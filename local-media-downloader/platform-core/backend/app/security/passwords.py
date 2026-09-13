"""Password hashing — Argon2id via argon2-cffi's high-level PasswordHasher,
the exact same library and default parameters Loady already uses in
production (`local-media-downloader/backend/app/services/security_service.py`).
Reused verbatim rather than replaced, per the mission brief's "reuse good
existing security patterns" and "do not roll your own crypto" rules.
"""
from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True
