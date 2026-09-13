"""Integration coverage: PlatformOidcToken persistence goes through
TokenEncryptionService end to end (mission 4, phase 4) - plaintext never
reaches the database, and a legitimate later read can decrypt it back.
"""
from __future__ import annotations

import base64
import os

import pytest
from sqlalchemy import select

from app.config import commercial_settings as commercial_settings_module
from app.database.commercial_models import PlatformOidcToken, User
from app.models.commercial_enums import UserRole, UserStatus
from app.services import platform_entitlement_service, security_service, token_encryption_service


@pytest.fixture(autouse=True)
def _isolated_key(monkeypatch):
    key = base64.b64encode(os.urandom(32)).decode("ascii")
    monkeypatch.setenv("PLATFORM_TOKEN_ENCRYPTION_KEY", key)
    commercial_settings_module._settings = None
    token_encryption_service.reset_key_cache_for_tests()
    yield
    commercial_settings_module._settings = None
    token_encryption_service.reset_key_cache_for_tests()


def _make_user(db_session) -> User:
    user = User(
        email=f"platform-oidc-{os.urandom(4).hex()}@example.com",
        password_hash=security_service.hash_password("correct-horse-battery"),
        email_verified=True,
        status=UserStatus.ACTIVE.value,
        role=UserRole.USER.value,
        global_user_id=f"usr_{os.urandom(8).hex()}",
    )
    db_session.add(user)
    db_session.flush()
    return user


def test_store_tokens_never_persists_plaintext(db_session):
    user = _make_user(db_session)
    raw_refresh = "REFRESH-super-secret-value-do-not-leak"
    raw_access = "ACCESS-also-sensitive-bearer-value"

    platform_entitlement_service.store_tokens(db_session, user, raw_access, raw_refresh, expires_in=900)
    db_session.commit()

    row = db_session.execute(
        select(PlatformOidcToken).where(PlatformOidcToken.user_id == user.id)
    ).scalars().one()

    assert raw_refresh not in row.refresh_token
    assert raw_access not in row.access_token
    assert token_encryption_service.is_encrypted(row.refresh_token)
    assert token_encryption_service.is_encrypted(row.access_token)


def test_stored_tokens_round_trip_decrypt_correctly(db_session):
    user = _make_user(db_session)
    raw_refresh = "REFRESH-round-trip-value"
    raw_access = "ACCESS-round-trip-value"

    platform_entitlement_service.store_tokens(db_session, user, raw_access, raw_refresh, expires_in=900)
    db_session.commit()

    row = db_session.execute(
        select(PlatformOidcToken).where(PlatformOidcToken.user_id == user.id)
    ).scalars().one()

    assert token_encryption_service.decrypt(row.refresh_token) == raw_refresh
    assert token_encryption_service.decrypt(row.access_token) == raw_access


def test_get_authoritative_entitlement_returns_none_when_stored_refresh_token_is_undecryptable(
    monkeypatch, db_session
):
    """A tampered/undecryptable stored refresh token must degrade to
    "unknown" (None), never crash the caller and never be silently treated
    as entitled."""
    monkeypatch.setenv("PLATFORM_CLIENT_ID", "demo-client")
    commercial_settings_module._settings = None

    user = _make_user(db_session)
    platform_entitlement_service.store_tokens(db_session, user, "access", "refresh", expires_in=900)
    db_session.commit()

    row = db_session.execute(
        select(PlatformOidcToken).where(PlatformOidcToken.user_id == user.id)
    ).scalars().one()
    row.refresh_token = "v1:not-valid-base64-nonce:also-not-valid"
    row.access_token = None
    row.access_token_expires_at = None
    db_session.commit()

    result = platform_entitlement_service.get_authoritative_entitlement(db_session, user)
    assert result is None
