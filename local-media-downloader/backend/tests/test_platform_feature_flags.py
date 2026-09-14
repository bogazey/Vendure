"""Mission 7 (Phase 17): named, independently-testable Platform Core
integration flags (PLATFORM_AUTH_ENABLED / PLATFORM_ENTITLEMENTS_ENABLED /
PLATFORM_BILLING_ENABLED). These WRAP, not replace, the existing
PLATFORM_CLIENT_ID-emptiness dormancy check - hence defaulting to True,
so every pre-existing test/deployment that only ever configured
credentials (never touched these flags) keeps behaving exactly as
before. What's new is a credential-independent kill switch, and a
fail-fast rejection of the nonsensical
PLATFORM_ENTITLEMENTS_ENABLED=true + PLATFORM_AUTH_ENABLED=false
combination.
"""
from __future__ import annotations

import os

import pytest
from pydantic import ValidationError

from app.config.commercial_settings import CommercialSettings, get_commercial_settings
from app.database.commercial_models import User
from app.models.commercial_enums import Plan, UserRole, UserStatus
from app.services import platform_entitlement_service, platform_identity_service, security_service


def test_entitlements_enabled_without_auth_enabled_is_rejected_at_construction():
    # Fields declare an alias (env var name) and the model doesn't set
    # populate_by_name=True, so construction must use the alias, exactly
    # like a real PLATFORM_*_ENABLED env var would be read.
    with pytest.raises(ValidationError, match="PLATFORM_ENTITLEMENTS_ENABLED"):
        CommercialSettings(PLATFORM_AUTH_ENABLED=False, PLATFORM_ENTITLEMENTS_ENABLED=True)


def test_defaults_allow_the_construction_that_would_otherwise_be_rejected():
    # Both default True - the validator only fires on an EXPLICIT unsafe
    # combination, never on the defaults themselves.
    settings = CommercialSettings()
    assert settings.platform_auth_enabled is True
    assert settings.platform_entitlements_enabled is True


def test_auth_enabled_false_forces_dormancy_even_with_valid_credentials(monkeypatch):
    settings = get_commercial_settings()
    monkeypatch.setattr(settings, "platform_client_id", "loady-staging-client")
    monkeypatch.setattr(settings, "platform_client_secret", type(settings.platform_client_secret)("a-real-secret"))
    assert platform_identity_service.is_configured() is True

    monkeypatch.setattr(settings, "platform_auth_enabled", False)
    assert platform_identity_service.is_configured() is False


def test_entitlements_enabled_false_forces_local_plan_even_for_a_linked_user(monkeypatch, db_session):
    settings = get_commercial_settings()
    monkeypatch.setattr(settings, "platform_client_id", "loady-staging-client")

    user = User(
        email=f"flagtest-{os.urandom(4).hex()}@example.com",
        password_hash=security_service.hash_password("correct-horse-battery"),
        email_verified=True,
        status=UserStatus.ACTIVE.value,
        role=UserRole.USER.value,
        global_user_id=f"usr_{os.urandom(8).hex()}",
    )
    db_session.add(user)
    db_session.flush()

    # A live "entitled" answer would normally win - but the kill switch
    # forces the local plan through unchanged before that call ever happens.
    monkeypatch.setattr(
        platform_entitlement_service, "get_authoritative_entitlement",
        lambda s, u: {"entitled": True, "entitlement": {"product_id": "loady", "plan_slug": "creator", "source": "paddle", "status": "active", "expires_at": None}},
    )
    monkeypatch.setattr(settings, "platform_entitlements_enabled", False)

    plan, meta = platform_entitlement_service.resolve_effective_plan(db_session, user, Plan.FREE)
    assert plan == Plan.FREE
    assert meta["source"] == "local"


def test_get_authoritative_entitlement_returns_none_when_entitlements_disabled(monkeypatch, db_session):
    settings = get_commercial_settings()
    monkeypatch.setattr(settings, "platform_client_id", "loady-staging-client")
    monkeypatch.setattr(settings, "platform_entitlements_enabled", False)

    user = User(
        email=f"flagtest2-{os.urandom(4).hex()}@example.com",
        password_hash=security_service.hash_password("correct-horse-battery"),
        email_verified=True,
        status=UserStatus.ACTIVE.value,
        role=UserRole.USER.value,
        global_user_id=f"usr_{os.urandom(8).hex()}",
    )
    db_session.add(user)
    db_session.flush()

    assert platform_entitlement_service.get_authoritative_entitlement(db_session, user) is None
