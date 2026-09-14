"""Mission 7: `get_authoritative_entitlement` falls back to Platform
Core's `/api/v1/capabilities/me` when `/api/v1/entitlements/me` says
"not entitled" - closing the gap where a bundle/promotion/trial-only
user (V2-only sources) showed as unentitled to Loady even though
Platform Core's own capability engine knew better. Exercises the actual
HTTP-calling body of `get_authoritative_entitlement` directly (mocking
`httpx.get`), unlike the rest of the hybrid-model test suite, which
monkeypatches the whole function - so this is the one place this
specific logic is actually covered.
"""
from __future__ import annotations

import base64
import os

import httpx
import pytest

from app.config import commercial_settings as commercial_settings_module
from app.database.commercial_models import User
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


def _linked_user(db_session, monkeypatch) -> User:
    user = User(
        email=f"capfallback-{os.urandom(4).hex()}@example.com",
        password_hash=security_service.hash_password("correct-horse-battery"),
        email_verified=True,
        status=UserStatus.ACTIVE.value,
        role=UserRole.USER.value,
        global_user_id=f"usr_{os.urandom(8).hex()}",
    )
    db_session.add(user)
    db_session.flush()
    platform_entitlement_service.store_tokens(db_session, user, "valid-access-token", "valid-refresh-token", expires_in=900)
    db_session.commit()

    settings = platform_entitlement_service.get_commercial_settings()
    monkeypatch.setattr(settings, "platform_client_id", "loady-staging-client")
    return user


class _FakeResponse:
    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self._body = body

    def json(self) -> dict:
        return self._body


def test_bundle_only_access_falls_back_to_capabilities_me_and_picks_the_highest_ranked_source(db_session, monkeypatch):
    user = _linked_user(db_session, monkeypatch)

    def fake_get(url: str, **kwargs):
        if url.endswith("/api/v1/entitlements/me"):
            return _FakeResponse(200, {"entitled": False, "entitlement": None})
        if url.endswith("/api/v1/capabilities/me"):
            return _FakeResponse(200, {
                "entitled": True, "product_id": "loady", "capabilities": {},
                "sources": [
                    {"kind": "bundle", "plan_id": "plan_creator", "plan_slug": "creator", "status": "active",
                     "expires_at": None, "rank": 80},
                    {"kind": "gifted", "plan_id": "plan_pro", "plan_slug": "pro", "status": "active",
                     "expires_at": None, "rank": 60},
                ],
            })
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(httpx, "get", fake_get)

    result = platform_entitlement_service.get_authoritative_entitlement(db_session, user)
    assert result is not None
    assert result["entitled"] is True
    # The bundle source (rank 80) outranks the gift (rank 60).
    assert result["entitlement"]["plan_slug"] == "creator"
    assert result["entitlement"]["source"] == "bundle"


def test_entitlements_me_already_entitled_never_calls_capabilities_me(db_session, monkeypatch):
    user = _linked_user(db_session, monkeypatch)
    calls: list[str] = []

    def fake_get(url: str, **kwargs):
        calls.append(url)
        assert url.endswith("/api/v1/entitlements/me")
        return _FakeResponse(200, {
            "entitled": True,
            "entitlement": {"product_id": "loady", "plan_slug": "pro", "source": "paddle", "status": "active", "expires_at": None},
        })

    monkeypatch.setattr(httpx, "get", fake_get)

    result = platform_entitlement_service.get_authoritative_entitlement(db_session, user)
    assert result["entitled"] is True
    assert result["entitlement"]["plan_slug"] == "pro"
    assert len(calls) == 1  # no extra round trip when the legacy answer already says entitled


def test_neither_endpoint_has_access_stays_unentitled(db_session, monkeypatch):
    user = _linked_user(db_session, monkeypatch)

    def fake_get(url: str, **kwargs):
        if url.endswith("/api/v1/entitlements/me"):
            return _FakeResponse(200, {"entitled": False, "entitlement": None})
        if url.endswith("/api/v1/capabilities/me"):
            return _FakeResponse(200, {"entitled": False, "product_id": "loady", "capabilities": {}, "sources": []})
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(httpx, "get", fake_get)

    result = platform_entitlement_service.get_authoritative_entitlement(db_session, user)
    assert result["entitled"] is False
    assert result["entitlement"] is None


def test_capabilities_me_network_failure_never_raises_falls_back_to_legacy_answer(db_session, monkeypatch):
    user = _linked_user(db_session, monkeypatch)

    def fake_get(url: str, **kwargs):
        if url.endswith("/api/v1/entitlements/me"):
            return _FakeResponse(200, {"entitled": False, "entitlement": None})
        if url.endswith("/api/v1/capabilities/me"):
            raise httpx.ConnectError("connection refused")
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(httpx, "get", fake_get)

    result = platform_entitlement_service.get_authoritative_entitlement(db_session, user)
    assert result == {"entitled": False, "entitlement": None}
