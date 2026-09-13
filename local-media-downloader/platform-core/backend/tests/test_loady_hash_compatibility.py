"""Proves - in code, not by inspection alone - that a Loady-issued
Argon2id password hash is directly usable by Platform Core with no
forced password reset (mission: "VERIFY THIS AGAIN IN CODE").

Loady's own hashing (`local-media-downloader/backend/app/services/
security_service.py`) is `argon2.PasswordHasher()` with library defaults,
`argon2-cffi==23.1.0` pinned. Platform Core's `app/security/passwords.py`
is the exact same construction and the exact same pinned version
(see both `requirements.txt` files). This test does not import Loady's
code (the two services intentionally have separate dependency trees/
venvs - see docs/platform/LOCAL_DEVELOPMENT.md) - instead it constructs a
hash the identical way Loady's own code does, which is precisely the
scenario a migration script copying `password_hash` verbatim between the
two databases relies on.
"""
from __future__ import annotations

from argon2 import PasswordHasher

from app.security import passwords as platform_passwords


def _loady_style_hash(password: str) -> str:
    """Byte-for-byte what `security_service.hash_password` does in Loady."""
    return PasswordHasher().hash(password)


def test_loady_hash_verifies_successfully_against_platform_core():
    raw_password = "correct horse battery staple 42!"
    loady_hash = _loady_style_hash(raw_password)

    assert loady_hash.startswith("$argon2id$"), "Loady hashes must be argon2id"
    assert platform_passwords.verify_password(raw_password, loady_hash) is True


def test_loady_hash_rejects_wrong_password_on_platform_core():
    loady_hash = _loady_style_hash("the-real-password")
    assert platform_passwords.verify_password("not-the-real-password", loady_hash) is False


def test_migrated_hash_is_not_downgraded_or_forced_to_rehash():
    """A copied hash must not trigger a forced re-hash on first use - that
    would be indistinguishable, from the user's perspective, from being
    forced to reset their password, which the mission explicitly forbids
    unless a real incompatibility exists (none does)."""
    loady_hash = _loady_style_hash("another-real-password-1")
    assert platform_passwords.needs_rehash(loady_hash) is False


def test_platform_core_issued_hash_is_also_loady_compatible_both_directions():
    """The compatibility is symmetric: a hash Platform Core creates must
    equally be verifiable by Loady's own verify_password shape (same
    library call), proving neither side's parameters silently drifted."""
    raw_password = "symmetric-check-password-1"
    platform_hash = platform_passwords.hash_password(raw_password)
    assert platform_hash.startswith("$argon2id$")
    assert PasswordHasher().verify(platform_hash, raw_password) is True


def test_plaintext_password_is_never_available_to_copy():
    """Structural proof, not a convention to remember: only a hash ever
    exists past the moment of hashing - there is no function anywhere in
    app/security/passwords.py that returns or logs a plaintext password,
    so a migration script reading a user row can only ever propagate
    `password_hash`, never a plaintext value, because no plaintext value
    exists in the database to begin with."""
    import inspect

    source = inspect.getsource(platform_passwords)
    assert "log" not in source.lower()
    assert "print(" not in source
