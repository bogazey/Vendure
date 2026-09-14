"""Mission 6 continuation: `app/security/secret_encryption.py` -
AES-256-GCM encryption at rest for `OAuthClient.webhook_signing_secret_
encrypted`. Ported test-for-test from Loady's already-reviewed
`backend/tests/test_token_encryption_service.py`, since the module itself
is a direct port of that pattern."""
from __future__ import annotations

import base64
import logging
import os

import pytest

from app.config import settings as settings_module
from app.security import secret_encryption as se


@pytest.fixture(autouse=True)
def _isolated_key(monkeypatch):
    key = base64.b64encode(os.urandom(32)).decode("ascii")
    monkeypatch.setenv("WEBHOOK_SECRET_ENCRYPTION_KEY", key)
    monkeypatch.setenv("APP_ENV", "development")
    settings_module._settings = None
    se.reset_key_cache_for_tests()
    yield
    settings_module._settings = None
    se.reset_key_cache_for_tests()


def test_round_trip_decrypt_works():
    envelope = se.encrypt("super-secret-webhook-value")
    assert se.decrypt(envelope) == "super-secret-webhook-value"


def test_envelope_stores_a_version_prefix():
    envelope = se.encrypt("anything")
    assert envelope.startswith("v1:")


def test_ciphertext_never_contains_the_plaintext():
    plaintext = "extremely-sensitive-webhook-secret"
    envelope = se.encrypt(plaintext)
    assert plaintext not in envelope


def test_wrong_key_fails(monkeypatch):
    envelope = se.encrypt("a-webhook-secret")

    wrong_key = base64.b64encode(os.urandom(32)).decode("ascii")
    monkeypatch.setenv("WEBHOOK_SECRET_ENCRYPTION_KEY", wrong_key)
    settings_module._settings = None
    se.reset_key_cache_for_tests()

    with pytest.raises(se.SecretDecryptionError):
        se.decrypt(envelope)


def test_tampered_ciphertext_fails():
    envelope = se.encrypt("a-webhook-secret")
    version, nonce_b64, ciphertext_b64 = envelope.split(":")
    tampered = bytearray(base64.b64decode(ciphertext_b64))
    tampered[0] ^= 0xFF
    tampered_envelope = f"{version}:{nonce_b64}:{base64.b64encode(bytes(tampered)).decode()}"

    with pytest.raises(se.SecretDecryptionError):
        se.decrypt(tampered_envelope)


def test_tampered_nonce_fails():
    envelope = se.encrypt("a-webhook-secret")
    version, nonce_b64, ciphertext_b64 = envelope.split(":")
    tampered_nonce = bytearray(base64.b64decode(nonce_b64))
    tampered_nonce[0] ^= 0xFF
    tampered_envelope = f"{version}:{base64.b64encode(bytes(tampered_nonce)).decode()}:{ciphertext_b64}"

    with pytest.raises(se.SecretDecryptionError):
        se.decrypt(tampered_envelope)


def test_malformed_envelope_fails_closed():
    with pytest.raises(se.SecretDecryptionError):
        se.decrypt("not-a-valid-envelope-at-all")


def test_unknown_version_fails_closed():
    envelope = se.encrypt("value")
    _, nonce_b64, ciphertext_b64 = envelope.split(":")
    with pytest.raises(se.SecretDecryptionError):
        se.decrypt(f"v99:{nonce_b64}:{ciphertext_b64}")


def test_missing_key_fails_closed_in_staging(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET_ENCRYPTION_KEY", "")
    monkeypatch.setenv("APP_ENV", "staging")
    settings_module._settings = None
    se.reset_key_cache_for_tests()

    with pytest.raises(se.SecretEncryptionUnavailableError):
        se.encrypt("anything")


def test_missing_key_fails_closed_in_production(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET_ENCRYPTION_KEY", "")
    monkeypatch.setenv("APP_ENV", "production")
    settings_module._settings = None
    se.reset_key_cache_for_tests()

    with pytest.raises(se.SecretEncryptionUnavailableError):
        se.encrypt("anything")


def test_missing_key_in_development_generates_an_ephemeral_key(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET_ENCRYPTION_KEY", "")
    monkeypatch.setenv("APP_ENV", "development")
    settings_module._settings = None
    se.reset_key_cache_for_tests()

    envelope = se.encrypt("anything")
    assert se.decrypt(envelope) == "anything"


def test_wrong_length_key_fails_closed(monkeypatch):
    short_key = base64.b64encode(os.urandom(16)).decode("ascii")
    monkeypatch.setenv("WEBHOOK_SECRET_ENCRYPTION_KEY", short_key)
    settings_module._settings = None
    se.reset_key_cache_for_tests()

    with pytest.raises(se.SecretEncryptionUnavailableError):
        se.encrypt("anything")


def test_no_plaintext_secret_is_logged_on_decrypt_failure(caplog):
    plaintext = "unique-marker-should-never-be-logged-abc123"
    envelope = se.encrypt(plaintext)
    tampered = envelope[:-1] + ("A" if envelope[-1] != "A" else "B")

    with caplog.at_level(logging.WARNING):
        with pytest.raises(se.SecretDecryptionError):
            se.decrypt(tampered)

    for record in caplog.records:
        assert plaintext not in record.getMessage()


def test_stored_column_never_contains_the_raw_secret(db_session):
    """DB-level check: the actual column a webhook secret ends up in
    never contains the plaintext, not just the encryption function in
    isolation."""
    from app.database.models import OAuthClient, Product, User
    from app.services import oidc_service, service_auth

    admin = User(email="admin-secretcheck@example.com", password_hash="x", email_verified=True)
    db_session.add(admin)
    product = Product(id="secretcheck-product", name="SC", domain="sc.example", status="live")
    db_session.add(product)
    db_session.flush()
    reg_client, _oauth_secret = oidc_service.register_client(db_session, admin, "secretcheck-client", "SC Client", product.id, [])
    db_session.commit()

    raw_secret = service_auth.configure_webhook(db_session, admin, reg_client, "https://sc.example/hook")
    db_session.commit()

    stored = db_session.get(OAuthClient, "secretcheck-client")
    assert raw_secret not in stored.webhook_signing_secret_encrypted
    assert se.decrypt(stored.webhook_signing_secret_encrypted) == raw_secret
