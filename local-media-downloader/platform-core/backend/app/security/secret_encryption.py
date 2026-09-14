"""Encryption at rest for `OAuthClient.webhook_signing_secret_encrypted`
(Mission 6 continuation - the previous session's security review flagged
this as stored in plaintext).

Ported directly from Loady's own, already-reviewed
`backend/app/services/token_encryption_service.py` (mission 4, phase 4) -
same reasoning applies: unlike every credential this codebase otherwise
one-way-hashes (passwords, refresh tokens, reset tokens), a webhook
signing secret must be presented back in its original form to sign
outgoing deliveries, so it cannot be a hash. AES-256-GCM (authenticated
encryption) via the standard `cryptography` library - no hand-rolled
cryptography.

Envelope format: `"<version>:<nonce_b64>:<ciphertext_and_tag_b64>"` - a
single string, safe to store directly in a text column. The version
prefix is the key-rotation mechanism: introducing `v2` (a new key)
alongside `v1` needs no schema change, only a new branch in `_load_key`/
`decrypt` keyed off the version already embedded in every stored value.

Fail-closed policy: `APP_ENV` other than `development` requires a real
`WEBHOOK_SECRET_ENCRYPTION_KEY` (32 raw bytes, base64-encoded) - missing
it raises `SecretEncryptionUnavailableError` rather than silently
persisting plaintext. Development without a configured key falls back to
an ephemeral per-process key (secrets encrypted this run will not decrypt
after a restart - acceptable for local dev, never for staging/production).
"""
from __future__ import annotations

import base64
import functools
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config.logging_config import get_logger
from app.config.settings import get_settings

logger = get_logger("secret_encryption")

_ENVELOPE_VERSION = "v1"
_KEY_BYTES = 32  # AES-256
_NONCE_BYTES = 12  # standard GCM nonce size


class SecretEncryptionError(RuntimeError):
    """Base class for secret-encryption failures. Never includes
    plaintext or key material in its message."""


class SecretEncryptionUnavailableError(SecretEncryptionError):
    """No usable encryption key for this environment (fail-closed)."""


class SecretDecryptionError(SecretEncryptionError):
    """Ciphertext could not be decrypted: wrong key, tampering, or
    corruption. Deliberately does not distinguish which, to avoid
    leaking an oracle."""


@functools.lru_cache(maxsize=1)
def _load_key() -> bytes:
    settings = get_settings()
    configured = settings.webhook_secret_encryption_key

    if configured:
        try:
            raw = base64.b64decode(configured, validate=True)
        except Exception as exc:  # noqa: BLE001 - never echo the invalid value itself
            raise SecretEncryptionUnavailableError(
                "WEBHOOK_SECRET_ENCRYPTION_KEY is not valid base64."
            ) from exc
        if len(raw) != _KEY_BYTES:
            raise SecretEncryptionUnavailableError(
                f"WEBHOOK_SECRET_ENCRYPTION_KEY must decode to {_KEY_BYTES} bytes (got {len(raw)})."
            )
        return raw

    if settings.app_env != "development":
        raise SecretEncryptionUnavailableError(
            f"WEBHOOK_SECRET_ENCRYPTION_KEY is not set and APP_ENV={settings.app_env!r} "
            "does not allow an ephemeral key. Provision a real key before storing any "
            "webhook signing secret in staging/production."
        )

    logger.warning(
        "WEBHOOK_SECRET_ENCRYPTION_KEY unset - generating an ephemeral development-only "
        "key. Secrets encrypted this run will NOT decrypt after a restart."
    )
    return os.urandom(_KEY_BYTES)


def reset_key_cache_for_tests() -> None:
    _load_key.cache_clear()


def encrypt(plaintext: str) -> str:
    """Never logs `plaintext`."""
    key = _load_key()
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), associated_data=None)
    return ":".join([
        _ENVELOPE_VERSION,
        base64.b64encode(nonce).decode("ascii"),
        base64.b64encode(ciphertext).decode("ascii"),
    ])


def decrypt(envelope: str) -> str:
    """Raises `SecretDecryptionError` on a wrong key, tampered ciphertext,
    or malformed envelope - never returns partial/garbage plaintext, and
    never logs the envelope or the recovered plaintext."""
    parts = envelope.split(":", 2)
    if len(parts) != 3 or parts[0] != _ENVELOPE_VERSION:
        raise SecretDecryptionError("Unrecognized secret envelope format or version.")
    _, nonce_b64, ciphertext_b64 = parts

    key = _load_key()
    try:
        nonce = base64.b64decode(nonce_b64, validate=True)
        ciphertext = base64.b64decode(ciphertext_b64, validate=True)
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, associated_data=None)
    except Exception as exc:  # noqa: BLE001 - never echo ciphertext/key material
        raise SecretDecryptionError("Secret could not be decrypted.") from exc
    return plaintext.decode("utf-8")
