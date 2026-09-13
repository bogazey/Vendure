"""TokenEncryptionService (mission 4, phase 4): AES-256-GCM encryption at
rest for Platform Core OIDC tokens Loady must be able to present back
later (so, unlike every other token in this schema, cannot be a one-way
hash).
"""
from __future__ import annotations

import base64
import logging
import os

import pytest

from app.config import commercial_settings as commercial_settings_module
from app.services import token_encryption_service as tes


@pytest.fixture(autouse=True)
def _isolated_key(monkeypatch):
    """Every test gets its own real key and a clean settings/key cache, and
    leaves both reset afterward so no test can leak a key into another
    test file (mirrors platform-core's `test_signing_key.py` fixture)."""
    key = base64.b64encode(os.urandom(32)).decode("ascii")
    monkeypatch.setenv("PLATFORM_TOKEN_ENCRYPTION_KEY", key)
    monkeypatch.setenv("APP_ENV", "development")
    commercial_settings_module._settings = None
    tes.reset_key_cache_for_tests()
    yield
    commercial_settings_module._settings = None
    tes.reset_key_cache_for_tests()


def test_round_trip_decrypt_works():
    envelope = tes.encrypt("super-secret-refresh-token-value")
    assert tes.decrypt(envelope) == "super-secret-refresh-token-value"


def test_envelope_stores_a_version_prefix():
    envelope = tes.encrypt("anything")
    assert envelope.startswith("v1:")
    assert tes.is_encrypted(envelope) is True
    assert tes.is_encrypted("plain-legacy-value") is False


def test_ciphertext_never_contains_the_plaintext():
    plaintext = "extremely-sensitive-refresh-token"
    envelope = tes.encrypt(plaintext)
    assert plaintext not in envelope


def test_wrong_key_fails(monkeypatch):
    envelope = tes.encrypt("a-refresh-token")

    wrong_key = base64.b64encode(os.urandom(32)).decode("ascii")
    monkeypatch.setenv("PLATFORM_TOKEN_ENCRYPTION_KEY", wrong_key)
    commercial_settings_module._settings = None
    tes.reset_key_cache_for_tests()

    with pytest.raises(tes.TokenDecryptionError):
        tes.decrypt(envelope)


def test_tampered_ciphertext_fails():
    envelope = tes.encrypt("a-refresh-token")
    version, nonce_b64, ciphertext_b64 = envelope.split(":")
    tampered = bytearray(base64.b64decode(ciphertext_b64))
    tampered[0] ^= 0xFF
    tampered_envelope = f"{version}:{nonce_b64}:{base64.b64encode(bytes(tampered)).decode()}"

    with pytest.raises(tes.TokenDecryptionError):
        tes.decrypt(tampered_envelope)


def test_tampered_nonce_fails():
    envelope = tes.encrypt("a-refresh-token")
    version, nonce_b64, ciphertext_b64 = envelope.split(":")
    tampered_nonce = bytearray(base64.b64decode(nonce_b64))
    tampered_nonce[0] ^= 0xFF
    tampered_envelope = f"{version}:{base64.b64encode(bytes(tampered_nonce)).decode()}:{ciphertext_b64}"

    with pytest.raises(tes.TokenDecryptionError):
        tes.decrypt(tampered_envelope)


def test_malformed_envelope_fails_closed():
    with pytest.raises(tes.TokenDecryptionError):
        tes.decrypt("not-a-valid-envelope-at-all")


def test_unknown_version_fails_closed():
    envelope = tes.encrypt("value")
    _, nonce_b64, ciphertext_b64 = envelope.split(":")
    with pytest.raises(tes.TokenDecryptionError):
        tes.decrypt(f"v99:{nonce_b64}:{ciphertext_b64}")


def test_missing_key_fails_closed_in_staging(monkeypatch):
    monkeypatch.setenv("PLATFORM_TOKEN_ENCRYPTION_KEY", "")
    monkeypatch.setenv("APP_ENV", "staging")
    commercial_settings_module._settings = None
    tes.reset_key_cache_for_tests()

    with pytest.raises(tes.TokenEncryptionUnavailableError):
        tes.encrypt("anything")


def test_missing_key_fails_closed_in_production(monkeypatch):
    monkeypatch.setenv("PLATFORM_TOKEN_ENCRYPTION_KEY", "")
    monkeypatch.setenv("APP_ENV", "production")
    commercial_settings_module._settings = None
    tes.reset_key_cache_for_tests()

    with pytest.raises(tes.TokenEncryptionUnavailableError):
        tes.encrypt("anything")


def test_missing_key_in_development_generates_an_ephemeral_key(monkeypatch):
    monkeypatch.setenv("PLATFORM_TOKEN_ENCRYPTION_KEY", "")
    monkeypatch.setenv("APP_ENV", "development")
    commercial_settings_module._settings = None
    tes.reset_key_cache_for_tests()

    envelope = tes.encrypt("anything")
    assert tes.decrypt(envelope) == "anything"


def test_wrong_length_key_fails_closed(monkeypatch):
    short_key = base64.b64encode(os.urandom(16)).decode("ascii")
    monkeypatch.setenv("PLATFORM_TOKEN_ENCRYPTION_KEY", short_key)
    commercial_settings_module._settings = None
    tes.reset_key_cache_for_tests()

    with pytest.raises(tes.TokenEncryptionUnavailableError):
        tes.encrypt("anything")


def test_no_plaintext_token_is_logged_on_decrypt_failure(caplog):
    plaintext = "unique-marker-should-never-be-logged-abc123"
    envelope = tes.encrypt(plaintext)
    tampered = envelope[:-1] + ("A" if envelope[-1] != "A" else "B")

    with caplog.at_level(logging.WARNING):
        with pytest.raises(tes.TokenDecryptionError):
            tes.decrypt(tampered)

    for record in caplog.records:
        assert plaintext not in record.getMessage()
