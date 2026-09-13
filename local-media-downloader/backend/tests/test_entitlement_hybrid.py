"""Hybrid entitlement-availability model (mission 4, phase 11): a bounded,
server-side, product-scoped last-known-entitlement cache used only for
read-only capability checks, never for a security-sensitive mutation - see
docs/platform/ENTITLEMENT_AVAILABILITY.md.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from app.database.commercial_models import PlatformEntitlementCache, User
from app.models.commercial_enums import UserRole, UserStatus
from app.services import platform_entitlement_service, security_service


def _make_user(db_session) -> User:
    user = User(
        email=f"hybrid-{os.urandom(4).hex()}@example.com",
        password_hash=security_service.hash_password("correct-horse-battery"),
        email_verified=True,
        status=UserStatus.ACTIVE.value,
        role=UserRole.USER.value,
        global_user_id=f"usr_{os.urandom(8).hex()}",
    )
    db_session.add(user)
    db_session.flush()
    return user


def test_live_success_writes_the_cache_and_reports_source_live(monkeypatch, db_session):
    user = _make_user(db_session)
    live_response = {
        "entitled": True,
        "entitlement": {"product_id": "loady", "plan_slug": "creator", "source": "paddle", "status": "active", "expires_at": None},
    }
    monkeypatch.setattr(platform_entitlement_service, "get_authoritative_entitlement", lambda s, u: live_response)

    result = platform_entitlement_service.get_entitlement_hybrid(db_session, user)
    db_session.commit()

    assert result["source"] == "live"
    assert result["stale"] is False
    assert result["entitled"] is True

    row = db_session.get(PlatformEntitlementCache, (user.id, "loady"))
    assert row is not None
    assert row.entitled is True
    assert row.plan_slug == "creator"
    assert row.source == "paddle"


def test_unreachable_platform_core_serves_fresh_cache_as_stale(monkeypatch, db_session):
    user = _make_user(db_session)
    monkeypatch.setattr(platform_entitlement_service, "get_authoritative_entitlement", lambda s, u: {
        "entitled": True,
        "entitlement": {"product_id": "loady", "plan_slug": "pro", "source": "gifted", "status": "active", "expires_at": None},
    })
    platform_entitlement_service.get_entitlement_hybrid(db_session, user)
    db_session.commit()

    # Platform Core goes unreachable.
    monkeypatch.setattr(platform_entitlement_service, "get_authoritative_entitlement", lambda s, u: None)
    result = platform_entitlement_service.get_entitlement_hybrid(db_session, user)

    assert result["source"] == "cached"
    assert result["stale"] is True
    assert result["entitled"] is True
    assert result["entitlement"]["source"] == "gifted"  # gifted/paid source preserved through the cache


def test_cache_older_than_ttl_is_never_served_falls_back_to_unentitled(monkeypatch, db_session):
    user = _make_user(db_session)
    row = PlatformEntitlementCache(
        user_id=user.id, product_id="loady", entitled=True, plan_slug="pro", source="paddle",
        status="active", checked_at=datetime.now(timezone.utc) - timedelta(minutes=999),
    )
    db_session.add(row)
    db_session.commit()

    monkeypatch.setattr(platform_entitlement_service, "get_authoritative_entitlement", lambda s, u: None)
    result = platform_entitlement_service.get_entitlement_hybrid(db_session, user)

    assert result["source"] == "unknown"
    assert result["entitled"] is False
    assert result["entitlement"] is None


def test_no_cache_and_unreachable_platform_core_is_unentitled_never_a_guess(monkeypatch, db_session):
    user = _make_user(db_session)
    monkeypatch.setattr(platform_entitlement_service, "get_authoritative_entitlement", lambda s, u: None)

    result = platform_entitlement_service.get_entitlement_hybrid(db_session, user)

    assert result["source"] == "unknown"
    assert result["entitled"] is False


def test_revocation_is_reflected_immediately_on_the_next_live_call(monkeypatch, db_session):
    user = _make_user(db_session)
    monkeypatch.setattr(platform_entitlement_service, "get_authoritative_entitlement", lambda s, u: {
        "entitled": True,
        "entitlement": {"product_id": "loady", "plan_slug": "pro", "source": "gifted", "status": "active", "expires_at": None},
    })
    platform_entitlement_service.get_entitlement_hybrid(db_session, user)
    db_session.commit()

    # Admin revokes the gift; Platform Core is reachable again and now says no.
    monkeypatch.setattr(platform_entitlement_service, "get_authoritative_entitlement", lambda s, u: {
        "entitled": False, "entitlement": None,
    })
    result = platform_entitlement_service.get_entitlement_hybrid(db_session, user)
    db_session.commit()

    assert result["source"] == "live"
    assert result["entitled"] is False
    row = db_session.get(PlatformEntitlementCache, (user.id, "loady"))
    assert row.entitled is False
