"""Mission 5, phase 3: the hybrid entitlement-availability model (mission 4,
phase 11 — see docs/platform/ENTITLEMENT_AVAILABILITY.md) is now the actual
authority behind Loady's download gate for any Platform-Core-linked user,
via platform_entitlement_service.resolve_effective_plan +
routes_downloads.py's call to it. This file proves the resolution function
itself picks the right plan (or fails closed) in every documented state;
test_commercial_download_gate.py continues to prove the gate's own
capability checks per plan unchanged.

Disabled-user handling isn't retested here: a centrally-disabled user never
reaches the download gate at all, because deps.get_optional_user's
revalidate_central_status_if_due (mission 4, phase 12) already flips
user.status to DISABLED before this code runs — see
test_session_status.py / docs/platform/SESSION_REVOCATION.md.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from app.database.commercial_models import PlatformEntitlementCache, User
from app.models.commercial_enums import Plan, UserRole, UserStatus
from app.models.schemas import CreateDownloadRequest
from app.services import platform_entitlement_service, security_service
from app.services.download_gate_service import download_gate_service
from app.utils.exceptions import PlanLimitReachedError


def _migrated_user(db_session) -> User:
    user = User(
        email=f"migrated-{os.urandom(4).hex()}@example.com",
        password_hash=security_service.hash_password("correct-horse-battery"),
        email_verified=True,
        status=UserStatus.ACTIVE.value,
        role=UserRole.USER.value,
        global_user_id=f"usr_{os.urandom(8).hex()}",
    )
    db_session.add(user)
    db_session.flush()
    return user


def _configure_platform_client(monkeypatch) -> None:
    """resolve_effective_plan is a no-op unless the integration is
    configured at all, matching production/staging behavior."""
    settings = platform_entitlement_service.get_commercial_settings()
    monkeypatch.setattr(settings, "platform_client_id", "loady-staging-client")


def _live(monkeypatch, response: dict) -> None:
    monkeypatch.setattr(platform_entitlement_service, "get_authoritative_entitlement", lambda s, u: response)


class TestNonMigratedAccountsAreUnaffected:
    def test_no_global_user_id_passes_local_plan_through_unchanged(self, db_session, monkeypatch):
        _configure_platform_client(monkeypatch)
        user = User(
            email=f"local-{os.urandom(4).hex()}@example.com",
            password_hash=security_service.hash_password("correct-horse-battery"),
            email_verified=True, status=UserStatus.ACTIVE.value, role=UserRole.USER.value,
        )
        db_session.add(user)
        db_session.flush()
        # Even if Platform Core would say something else, it's never asked.
        monkeypatch.setattr(
            platform_entitlement_service, "get_authoritative_entitlement",
            lambda s, u: pytest.fail("must not call Platform Core for a non-migrated user"),
        )
        plan, result = platform_entitlement_service.resolve_effective_plan(db_session, user, Plan.PRO)
        assert plan == Plan.PRO
        assert result["source"] == "local"

    def test_integration_not_configured_passes_local_plan_through_unchanged(self, db_session):
        user = _migrated_user(db_session)  # linked, but no PLATFORM_CLIENT_ID set
        plan, result = platform_entitlement_service.resolve_effective_plan(db_session, user, Plan.CREATOR)
        assert plan == Plan.CREATOR
        assert result["source"] == "local"


class TestPersonasResolveToTheAuthoritativePlan:
    @pytest.mark.parametrize(
        "plan_slug,source,expected",
        [
            ("free", "free", Plan.FREE),
            ("pro", "paddle", Plan.PRO),
            ("creator", "paddle", Plan.CREATOR),
            ("pro", "gifted", Plan.PRO),
            ("creator", "gifted", Plan.CREATOR),
        ],
        ids=["free", "pro-paddle", "creator-paddle", "gifted-pro", "gifted-creator"],
    )
    def test_live_entitlement_selects_the_matching_plan(self, db_session, monkeypatch, plan_slug, source, expected):
        _configure_platform_client(monkeypatch)
        user = _migrated_user(db_session)
        entitled = plan_slug != "free"
        entitlement = (
            {"product_id": "loady", "plan_slug": plan_slug, "source": source, "status": "active", "expires_at": None}
            if entitled else None
        )
        _live(monkeypatch, {"entitled": entitled, "entitlement": entitlement})

        plan, result = platform_entitlement_service.resolve_effective_plan(db_session, user, Plan.FREE)
        assert plan == expected
        assert result["source"] == "live"


class TestExpiredAndRevokedGiftsFailClosedToFree:
    def test_expired_gift_is_reported_unentitled_by_platform_core_and_falls_to_free(self, db_session, monkeypatch):
        # Platform Core's own entitlement_service.get_active_entitlement
        # excludes expired/revoked rows - Loady only ever sees entitled=False.
        _configure_platform_client(monkeypatch)
        user = _migrated_user(db_session)
        _live(monkeypatch, {"entitled": False, "entitlement": None})

        plan, result = platform_entitlement_service.resolve_effective_plan(db_session, user, Plan.PRO)
        assert plan == Plan.FREE
        assert result["entitled"] is False

        request = CreateDownloadRequest(url="https://youtube.com/watch?v=x", media_type="video", quality_key="1080")
        with pytest.raises(PlanLimitReachedError):
            download_gate_service.authorize_and_reserve(db_session, user, plan, None, request, "job-expired")

    def test_revoked_gift_falls_to_free(self, db_session, monkeypatch):
        _configure_platform_client(monkeypatch)
        user = _migrated_user(db_session)
        _live(monkeypatch, {"entitled": False, "entitlement": None})
        plan, _ = platform_entitlement_service.resolve_effective_plan(db_session, user, Plan.CREATOR)
        assert plan == Plan.FREE


class TestPlatformCoreAvailability:
    def test_offline_with_valid_cache_keeps_the_paid_plan(self, db_session, monkeypatch):
        _configure_platform_client(monkeypatch)
        user = _migrated_user(db_session)
        row = PlatformEntitlementCache(
            user_id=user.id, product_id="loady", entitled=True, plan_slug="creator", source="paddle",
            status="active", checked_at=datetime.now(timezone.utc) - timedelta(minutes=2),
        )
        db_session.add(row)
        db_session.commit()
        monkeypatch.setattr(platform_entitlement_service, "get_authoritative_entitlement", lambda s, u: None)

        plan, result = platform_entitlement_service.resolve_effective_plan(db_session, user, Plan.FREE)
        assert plan == Plan.CREATOR
        assert result["source"] == "cached"
        assert result["stale"] is True

        # And the gate actually honors it: a 4K request succeeds.
        request = CreateDownloadRequest(url="https://youtube.com/watch?v=x", media_type="video", quality_key="2160")
        reservation_id, height = download_gate_service.authorize_and_reserve(db_session, user, plan, None, request, "job-cached")
        assert reservation_id
        assert height is None  # Creator is uncapped

    def test_offline_with_expired_cache_fails_closed_to_free(self, db_session, monkeypatch):
        _configure_platform_client(monkeypatch)
        user = _migrated_user(db_session)
        row = PlatformEntitlementCache(
            user_id=user.id, product_id="loady", entitled=True, plan_slug="pro", source="paddle",
            status="active", checked_at=datetime.now(timezone.utc) - timedelta(minutes=999),
        )
        db_session.add(row)
        db_session.commit()
        monkeypatch.setattr(platform_entitlement_service, "get_authoritative_entitlement", lambda s, u: None)

        plan, result = platform_entitlement_service.resolve_effective_plan(db_session, user, Plan.PRO)
        assert plan == Plan.FREE
        assert result["source"] == "unknown"

        # Free capability (720p) still works - never a full lockout.
        request = CreateDownloadRequest(url="https://youtube.com/watch?v=x", media_type="video", quality_key="720")
        reservation_id, height = download_gate_service.authorize_and_reserve(db_session, user, plan, None, request, "job-expired-cache")
        assert reservation_id
        assert height == 720


class TestMalformedOrUnrecognizedPlanSlugFailsClosed:
    def test_unrecognized_plan_slug_never_grants_access(self, db_session, monkeypatch):
        """Platform Core's /api/v1/entitlements/me is scoped strictly to the
        calling OAuth client's own product_id server-side (see
        platform-core/backend/tests/test_entitlements.py::test_wrong_product_denied)
        - Loady's access token can never receive another product's
        entitlement. This defends the other direction: even a malformed or
        unrecognized plan_slug (a future plan this deployment doesn't know
        about yet, a corrupted cache row) must fail closed, never raise or
        silently grant a plan."""
        _configure_platform_client(monkeypatch)
        user = _migrated_user(db_session)
        _live(monkeypatch, {
            "entitled": True,
            "entitlement": {"product_id": "loady", "plan_slug": "enterprise-unicorn", "source": "paddle", "status": "active", "expires_at": None},
        })
        plan, _ = platform_entitlement_service.resolve_effective_plan(db_session, user, Plan.FREE)
        assert plan == Plan.FREE
