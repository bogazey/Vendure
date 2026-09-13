"""Encryption at rest for `PlatformOidcToken.refresh_token`/`access_token`
(mission 4, phase 4).

Unlike every other token Loady stores (session refresh tokens, password
reset tokens, email verification tokens — all one-way SHA-256 hashes,
never needed back in plaintext), the Platform Core OIDC refresh/access
token pair MUST be presented back to Platform Core later
(`platform_entitlement_service._refresh_access_token`), so it cannot be a
one-way hash. It is therefore the one place in this schema that needs
genuine, reversible encryption at rest rather than hashing.

Uses AES-256-GCM (authenticated encryption) via the standard `cryptography`
library — no hand-rolled cryptography. The stored envelope is a single
string: `"<version>:<nonce_b64>:<ciphertext_and_tag_b64>"`, so a future key
rotation can introduce `v2` alongside `v1` without a schema change.

Fail-closed policy: `APP_ENV` other than `development` requires a real
`PLATFORM_TOKEN_ENCRYPTION_KEY` (32 raw bytes, base64-encoded) - if it is
missing, every encrypt/decrypt call raises `TokenEncryptionUnavailableError`
rather than silently persisting plaintext. Development without a
configured key falls back to an ephemeral per-process key (mirrors
`SECRET_KEY`'s existing dev-only generation pattern) - this is
deliberately isolated so it can never satisfy a staging/production
environment by accident.
"""
from __future__ import annotations

import base64
import functools
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config.commercial_settings import get_commercial_settings
from app.config.logging_config import get_logger

logger = get_logger("token_encryption")

_ENVELOPE_VERSION = "v1"
_KEY_BYTES = 32  # AES-256
_NONCE_BYTES = 12  # standard GCM nonce size


class TokenEncryptionError(RuntimeError):
    """Base class for token-encryption failures. Never includes plaintext
    or key material in its message."""


class TokenEncryptionUnavailableError(TokenEncryptionError):
    """No usable encryption key for this environment (fail-closed)."""


class TokenDecryptionError(TokenEncryptionError):
    """Ciphertext could not be decrypted: wrong key, tampering, or
    corruption. Deliberately does not distinguish which, to avoid leaking
    an oracle."""


@functools.lru_cache(maxsize=1)
def _load_key() -> bytes:
    settings = get_commercial_settings()
    configured = settings.platform_token_encryption_key.get_secret_value()

    if configured:
        try:
            raw = base64.b64decode(configured, validate=True)
        except Exception as exc:  # noqa: BLE001 - never echo the invalid value itself
            raise TokenEncryptionUnavailableError(
                "PLATFORM_TOKEN_ENCRYPTION_KEY is not valid base64."
            ) from exc
        if len(raw) != _KEY_BYTES:
            raise TokenEncryptionUnavailableError(
                f"PLATFORM_TOKEN_ENCRYPTION_KEY must decode to {_KEY_BYTES} bytes "
                f"(got {len(raw)})."
            )
        return raw

    if settings.app_env != "development":
        raise TokenEncryptionUnavailableError(
            f"PLATFORM_TOKEN_ENCRYPTION_KEY is not set and APP_ENV={settings.app_env!r} "
            "does not allow an ephemeral key. Provision a real key before storing "
            "any Platform Core OIDC tokens in staging/production."
        )

    logger.warning(
        "PLATFORM_TOKEN_ENCRYPTION_KEY unset - generating an ephemeral development-only "
        "key. Tokens encrypted this run will NOT decrypt after a restart."
    )
    return os.urandom(_KEY_BYTES)


def reset_key_cache_for_tests() -> None:
    """Test-only: forces the next `encrypt`/`decrypt` call to re-derive the
    key from current settings, exactly like a fresh process would."""
    _load_key.cache_clear()


def encrypt(plaintext: str) -> str:
    """Encrypts `plaintext`, returning a versioned envelope string safe to
    store directly in a text column. Never logs `plaintext`."""
    key = _load_key()
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), associated_data=None)
    return ":".join([
        _ENVELOPE_VERSION,
        base64.b64encode(nonce).decode("ascii"),
        base64.b64encode(ciphertext).decode("ascii"),
    ])


def decrypt(envelope: str) -> str:
    """Decrypts a value produced by `encrypt`. Raises `TokenDecryptionError`
    on a wrong key, tampered ciphertext, or malformed envelope - never
    returns partial/garbage plaintext."""
    parts = envelope.split(":", 2)
    if len(parts) != 3 or parts[0] != _ENVELOPE_VERSION:
        raise TokenDecryptionError("Unrecognized token envelope format or version.")
    _, nonce_b64, ciphertext_b64 = parts

    key = _load_key()
    try:
        nonce = base64.b64decode(nonce_b64, validate=True)
        ciphertext = base64.b64decode(ciphertext_b64, validate=True)
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, associated_data=None)
    except Exception as exc:  # noqa: BLE001 - never echo ciphertext/key material
        raise TokenDecryptionError("Token could not be decrypted.") from exc
    return plaintext.decode("utf-8")


def is_encrypted(value: str) -> bool:
    """Best-effort check used by the one-time migration script to decide
    whether a stored value is already in envelope form (idempotent
    re-runs) rather than legacy plaintext."""
    parts = value.split(":", 2)
    return len(parts) == 3 and parts[0] == _ENVELOPE_VERSION
