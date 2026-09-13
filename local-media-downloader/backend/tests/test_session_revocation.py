"""Bounded central-disable propagation (mission 4, phase 12): a centrally
linked Loady user's local session must be revoked within
SESSION_REVALIDATION_INTERVAL_MINUTES of Platform Core reporting the
account disabled - but never revoked merely because Platform Core was
briefly unreachable.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

import app.config.commercial_settings as commercial_settings_module
from app.config.commercial_settings import get_commercial_settings
from app.database.commercial_models import PlatformOidcToken, User
from app.models.commercial_enums import UserRole, UserStatus
from app.services import platform_entitlement_service, security_service, token_encryption_service


@pytest.fixture(autouse=True)
def _isolate_settings_singleton():
    """`get_commercial_settings()` is a process-wide singleton; leaving a
    PLATFORM_CLIENT_ID-configured instance cached after this file's tests
    would silently un-dormant the integration for every test that runs
    afterward (see the equivalent fixture in platform-core's
    `test_signing_key.py` for the same class of bug)."""
    yield
    commercial_settings_module._settings = None


def _make_linked_user(db_session) -> User:
    user = User(
        email=f"revoke-{os.urandom(4).hex()}@example.com",
        password_hash=security_service.hash_password("correct-horse-battery"),
        email_verified=True,
        status=UserStatus.ACTIVE.value,
        role=UserRole.USER.value,
        global_user_id=f"usr_{os.urandom(8).hex()}",
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(PlatformOidcToken(
        user_id=user.id, refresh_token="enc:irrelevant-for-this-test",
        access_token=None, access_token_expires_at=None, last_status_check_at=None,
    ))
    db_session.flush()
    return user


def _configure_platform_client(monkeypatch):
    monkeypatch.setenv("PLATFORM_CLIENT_ID", "loady-staging")
    commercial_settings_module._settings = None


def test_disabled_signal_locally_disables_the_user_immediately(monkeypatch, db_session):
    _configure_platform_client(monkeypatch)
    user = _make_linked_user(db_session)

    monkeypatch.setattr(platform_entitlement_service, "_refresh_access_token", lambda record: "fresh-token")

    class _Resp:
        status_code = 200

        def json(self):
            return {"status": "disabled"}

    monkeypatch.setattr(platform_entitlement_service.httpx, "get", lambda *a, **k: _Resp())

    platform_entitlement_service.revalidate_central_status_if_due(db_session, user)

    assert user.status == UserStatus.DISABLED.value


def test_active_signal_leaves_the_user_active(monkeypatch, db_session):
    _configure_platform_client(monkeypatch)
    user = _make_linked_user(db_session)
    monkeypatch.setattr(platform_entitlement_service, "_refresh_access_token", lambda record: "fresh-token")

    class _Resp:
        status_code = 200

        def json(self):
            return {"status": "active"}

    monkeypatch.setattr(platform_entitlement_service.httpx, "get", lambda *a, **k: _Resp())

    platform_entitlement_service.revalidate_central_status_if_due(db_session, user)

    assert user.status == UserStatus.ACTIVE.value


def test_unreachable_platform_core_never_disables_the_user(monkeypatch, db_session):
    _configure_platform_client(monkeypatch)
    user = _make_linked_user(db_session)
    # Refresh grant itself fails (e.g. network down) - ambiguous, must not act.
    monkeypatch.setattr(platform_entitlement_service, "_refresh_access_token", lambda record: None)

    platform_entitlement_service.revalidate_central_status_if_due(db_session, user)

    assert user.status == UserStatus.ACTIVE.value


def test_check_is_skipped_when_not_yet_due(monkeypatch, db_session):
    _configure_platform_client(monkeypatch)
    user = _make_linked_user(db_session)
    record = db_session.get(PlatformOidcToken, user.id)
    record.last_status_check_at = datetime.now(timezone.utc)  # just checked

    called = {"count": 0}

    def _fake_refresh(record):
        called["count"] += 1
        return "fresh-token"

    monkeypatch.setattr(platform_entitlement_service, "_refresh_access_token", _fake_refresh)

    platform_entitlement_service.revalidate_central_status_if_due(db_session, user)

    assert called["count"] == 0, "must not re-check before the interval elapses"


def test_check_runs_again_once_the_interval_has_elapsed(monkeypatch, db_session):
    _configure_platform_client(monkeypatch)
    user = _make_linked_user(db_session)
    settings = get_commercial_settings()
    record = db_session.get(PlatformOidcToken, user.id)
    record.last_status_check_at = datetime.now(timezone.utc) - timedelta(
        minutes=settings.session_revalidation_interval_minutes + 1
    )

    called = {"count": 0}

    def _fake_refresh(record):
        called["count"] += 1
        return "fresh-token"

    monkeypatch.setattr(platform_entitlement_service, "_refresh_access_token", _fake_refresh)

    class _Resp:
        status_code = 200

        def json(self):
            return {"status": "active"}

    monkeypatch.setattr(platform_entitlement_service.httpx, "get", lambda *a, **k: _Resp())

    platform_entitlement_service.revalidate_central_status_if_due(db_session, user)

    assert called["count"] == 1


def test_non_linked_user_is_never_checked(monkeypatch, db_session):
    _configure_platform_client(monkeypatch)
    user = User(
        email=f"unlinked-{os.urandom(4).hex()}@example.com",
        password_hash=security_service.hash_password("correct-horse-battery"),
        email_verified=True, status=UserStatus.ACTIVE.value, role=UserRole.USER.value,
        global_user_id=None,
    )
    db_session.add(user)
    db_session.flush()

    called = {"count": 0}
    monkeypatch.setattr(
        platform_entitlement_service, "_refresh_access_token",
        lambda record: called.__setitem__("count", called["count"] + 1) or "x",
    )

    platform_entitlement_service.revalidate_central_status_if_due(db_session, user)

    assert called["count"] == 0


def test_a_still_valid_cached_access_token_is_used_directly_never_forcing_a_refresh(monkeypatch, db_session):
    """Regression test for a real bug found during the staging rehearsal:
    forcing a refresh before checking status made a disabled account
    indistinguishable from an ordinary expired/revoked refresh token,
    since Platform Core's own refresh grant rejects both with the same
    generic invalid_grant error. Reusing a still-valid access token
    sidesteps that entirely."""
    _configure_platform_client(monkeypatch)
    user = _make_linked_user(db_session)
    record = db_session.get(PlatformOidcToken, user.id)
    record.access_token = token_encryption_service.encrypt("still-valid-access-token")
    record.access_token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    def _fail_if_called(record):
        raise AssertionError("must not force a refresh when a valid access token already exists")

    monkeypatch.setattr(platform_entitlement_service, "_refresh_access_token", _fail_if_called)

    class _Resp:
        status_code = 200

        def json(self):
            return {"status": "disabled"}

    monkeypatch.setattr(platform_entitlement_service.httpx, "get", lambda *a, **k: _Resp())

    platform_entitlement_service.revalidate_central_status_if_due(db_session, user)

    assert user.status == UserStatus.DISABLED.value


def test_disable_survives_a_rollback_later_in_the_same_request(monkeypatch, db_session):
    """Regression test for a real bug found during the staging rehearsal:
    `deps.get_optional_user` calls this function and then, in the SAME
    request, `get_current_user` raises AuthError once it sees the account
    is no longer active — which sends `deps.get_db`'s exception handler
    down the `session.rollback()` path. Without an explicit commit inside
    this function, that rollback silently undid the disable on every
    single request, so the account never actually stayed disabled."""
    _configure_platform_client(monkeypatch)
    user = _make_linked_user(db_session)
    monkeypatch.setattr(platform_entitlement_service, "_refresh_access_token", lambda record: "fresh-token")

    class _Resp:
        status_code = 200

        def json(self):
            return {"status": "disabled"}

    monkeypatch.setattr(platform_entitlement_service.httpx, "get", lambda *a, **k: _Resp())

    platform_entitlement_service.revalidate_central_status_if_due(db_session, user)
    assert user.status == UserStatus.DISABLED.value

    # Simulate exactly what deps.get_db does when the endpoint later raises.
    db_session.rollback()

    reloaded = db_session.get(User, user.id)
    assert reloaded.status == UserStatus.DISABLED.value, "the disable must survive a later rollback in this request"


def test_last_status_check_at_is_updated_even_on_failure_to_bound_retry_rate(monkeypatch, db_session):
    _configure_platform_client(monkeypatch)
    user = _make_linked_user(db_session)
    monkeypatch.setattr(platform_entitlement_service, "_refresh_access_token", lambda record: None)

    before = datetime.now(timezone.utc)
    platform_entitlement_service.revalidate_central_status_if_due(db_session, user)

    record = db_session.get(PlatformOidcToken, user.id)
    assert record.last_status_check_at is not None
    assert record.last_status_check_at >= before
