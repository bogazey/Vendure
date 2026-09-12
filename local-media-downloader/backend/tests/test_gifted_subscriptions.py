"""Admin-managed Gifted Subscriptions: grant/change/revoke, entitlements,
paid-Paddle-subscription precedence, revenue exclusion, and audit trail.

CRITICAL invariant under test throughout: a gifted subscription must never
touch Paddle (no API call, no subscription id) and must never be counted as
paid/revenue - see gift_subscription_service.py and docs/ANALYTICS.md.
"""
from __future__ import annotations

import uuid
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database.commercial_db import get_session_factory
from app.database.commercial_models import AdminActionLog, AnalyticsEvent, Subscription, User
from app.main import app
from app.models.commercial_enums import Plan
from app.services import gift_subscription_service
from app.services.auth_service import auth_service
from app.utils.exceptions import PaidSubscriptionActiveError

client = TestClient(app)


def _signup(email: str | None = None) -> tuple[TestClient, str]:
    c = TestClient(app)
    email = email or f"gift-{uuid.uuid4().hex[:12]}@example.com"
    resp = c.post("/api/auth/signup", json={"email": email, "password": "correcthorse9!"})
    assert resp.status_code == 201, resp.text
    return c, email


def _promote(email: str) -> None:
    session = get_session_factory()()
    try:
        db_user = session.execute(select(User).where(User.email == email)).scalars().first()
        db_user.role = "admin"
        session.commit()
    finally:
        session.close()


def _user_id(email: str) -> str:
    session = get_session_factory()()
    try:
        return session.execute(select(User.id).where(User.email == email)).scalar_one()
    finally:
        session.close()


def _get_subscription(user_id: str) -> Subscription | None:
    session = get_session_factory()()
    try:
        return session.execute(
            select(Subscription).where(Subscription.user_id == user_id).order_by(Subscription.updated_at.desc())
        ).scalars().first()
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    from app.services import rate_limit_service

    for limiter in (
        rate_limit_service.login_limiter, rate_limit_service.signup_limiter,
        rate_limit_service.password_reset_limiter, rate_limit_service.analyze_limiter,
        rate_limit_service.billing_limiter, rate_limit_service.analytics_limiter,
    ):
        limiter._hits.clear()
    yield


@pytest.fixture(autouse=True)
def _no_paddle_client(monkeypatch):
    """A canary that fails the test if anything in this module's code path
    ever reaches out to Paddle - see the "no Paddle API call" requirement."""
    poison = Mock(side_effect=AssertionError("Gifted subscription flow must never call Paddle"))
    monkeypatch.setattr("app.services.paddle_client.paddle_client.get_subscription", poison)
    monkeypatch.setattr("app.services.paddle_client.paddle_client.cancel_subscription", poison)
    monkeypatch.setattr("app.services.paddle_client.paddle_client.update_subscription", poison)
    monkeypatch.setattr("app.services.paddle_client.paddle_client.create_customer_portal_session", poison)
    yield


class TestAdminAuthorization:
    def test_anonymous_cannot_gift_a_plan(self):
        c = TestClient(app)
        resp = c.patch(f"/api/admin/users/{uuid.uuid4()}/subscription", json={"plan": "pro"})
        assert resp.status_code == 401

    def test_normal_user_cannot_gift_a_plan(self):
        c, _ = _signup()
        resp = c.patch(f"/api/admin/users/{uuid.uuid4()}/subscription", json={"plan": "pro"})
        assert resp.status_code == 403

    def test_admin_can_gift_a_plan(self):
        c, admin_email = _signup()
        _promote(admin_email)
        _, target_email = _signup()
        target_id = _user_id(target_email)

        resp = c.patch(f"/api/admin/users/{target_id}/subscription", json={"plan": "pro", "reason": "beta tester"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["plan"] == "pro"
        assert body["subscription_provider"] == "gifted"

    def test_invalid_plan_value_is_rejected(self):
        c, admin_email = _signup()
        _promote(admin_email)
        resp = c.patch(f"/api/admin/users/{uuid.uuid4()}/subscription", json={"plan": "enterprise"})
        assert resp.status_code == 422

    def test_unknown_user_id_is_404(self):
        c, admin_email = _signup()
        _promote(admin_email)
        resp = c.patch(f"/api/admin/users/{uuid.uuid4()}/subscription", json={"plan": "pro"})
        assert resp.status_code == 404


class TestGiftLifecycle:
    def test_free_user_can_be_gifted_pro(self):
        c, admin_email = _signup()
        _promote(admin_email)
        _, target_email = _signup()
        target_id = _user_id(target_email)

        resp = c.patch(f"/api/admin/users/{target_id}/subscription", json={"plan": "pro"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["plan"] == "pro"
        assert body["subscription_status"] == "active"
        assert body["subscription_provider"] == "gifted"
        assert body["gifted_granted_at"] is not None
        assert body["gifted_granted_by_email"] == admin_email

        sub = _get_subscription(target_id)
        assert sub.provider == "gifted"
        assert sub.provider_subscription_id is None
        assert sub.provider_customer_id is None

    def test_free_user_can_be_gifted_creator(self):
        c, admin_email = _signup()
        _promote(admin_email)
        _, target_email = _signup()
        target_id = _user_id(target_email)

        resp = c.patch(f"/api/admin/users/{target_id}/subscription", json={"plan": "creator"})
        assert resp.status_code == 200
        assert resp.json()["plan"] == "creator"
        assert resp.json()["subscription_provider"] == "gifted"

    def test_gifted_pro_can_be_changed_to_gifted_creator(self):
        c, admin_email = _signup()
        _promote(admin_email)
        _, target_email = _signup()
        target_id = _user_id(target_email)

        c.patch(f"/api/admin/users/{target_id}/subscription", json={"plan": "pro"})
        resp = c.patch(f"/api/admin/users/{target_id}/subscription", json={"plan": "creator", "reason": "upgraded partnership"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["plan"] == "creator"
        assert body["subscription_provider"] == "gifted"

        # Same underlying row updated in place, not a second row.
        session = get_session_factory()()
        try:
            rows = session.execute(select(Subscription).where(Subscription.user_id == target_id)).scalars().all()
            assert len(rows) == 1
            assert rows[0].plan == "creator"
        finally:
            session.close()

    def test_gifted_creator_can_be_changed_to_gifted_pro(self):
        c, admin_email = _signup()
        _promote(admin_email)
        _, target_email = _signup()
        target_id = _user_id(target_email)

        c.patch(f"/api/admin/users/{target_id}/subscription", json={"plan": "creator"})
        resp = c.patch(f"/api/admin/users/{target_id}/subscription", json={"plan": "pro"})
        assert resp.status_code == 200
        assert resp.json()["plan"] == "pro"
        assert resp.json()["subscription_provider"] == "gifted"

    def test_gifted_subscription_can_be_revoked_to_free(self):
        c, admin_email = _signup()
        _promote(admin_email)
        _, target_email = _signup()
        target_id = _user_id(target_email)

        c.patch(f"/api/admin/users/{target_id}/subscription", json={"plan": "creator"})
        resp = c.patch(f"/api/admin/users/{target_id}/subscription", json={"plan": "free", "reason": "trial ended"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["plan"] == "free"
        assert body["subscription_provider"] == "none"

        # The row is canceled, not deleted - history preserved.
        session = get_session_factory()()
        try:
            rows = session.execute(select(Subscription).where(Subscription.user_id == target_id)).scalars().all()
            assert len(rows) == 1
            assert rows[0].status == "canceled"
            assert rows[0].provider == "gifted"
        finally:
            session.close()

    def test_revoking_an_already_free_user_is_a_harmless_no_op(self):
        c, admin_email = _signup()
        _promote(admin_email)
        _, target_email = _signup()
        target_id = _user_id(target_email)

        resp = c.patch(f"/api/admin/users/{target_id}/subscription", json={"plan": "free"})
        assert resp.status_code == 200
        assert resp.json()["subscription_provider"] == "none"

        # No spurious audit entry for a no-op.
        session = get_session_factory()()
        try:
            count = session.execute(
                select(AdminActionLog).where(AdminActionLog.target_user_id == target_id)
            ).scalars().all()
            assert count == []
        finally:
            session.close()


class TestGiftedEntitlements:
    def test_gifted_pro_user_gets_pro_feature_entitlements(self):
        c, admin_email = _signup()
        _promote(admin_email)
        target_client, target_email = _signup()
        target_id = _user_id(target_email)

        c.patch(f"/api/admin/users/{target_id}/subscription", json={"plan": "pro"})

        account = target_client.get("/api/account").json()
        assert account["subscription"]["plan"] == "pro"
        assert account["subscription"]["provider"] == "gifted"
        assert account["features"]["can_use_4k"] is True
        assert account["features"]["can_use_batch"] is True
        assert account["usage"]["credits_included"] == 150  # Pro's monthly_credits

    def test_gifted_creator_user_gets_creator_feature_entitlements(self):
        c, admin_email = _signup()
        _promote(admin_email)
        target_client, target_email = _signup()
        target_id = _user_id(target_email)

        c.patch(f"/api/admin/users/{target_id}/subscription", json={"plan": "creator"})

        account = target_client.get("/api/account").json()
        assert account["subscription"]["plan"] == "creator"
        assert account["features"]["can_use_creator_tools"] is True
        assert account["usage"]["credits_included"] == 500  # Creator's monthly_credits

    def test_revoked_gifted_user_falls_back_to_free_entitlements_immediately(self):
        c, admin_email = _signup()
        _promote(admin_email)
        target_client, target_email = _signup()
        target_id = _user_id(target_email)

        c.patch(f"/api/admin/users/{target_id}/subscription", json={"plan": "creator"})
        c.patch(f"/api/admin/users/{target_id}/subscription", json={"plan": "free"})

        account = target_client.get("/api/account").json()
        assert account["subscription"]["plan"] == "free"
        assert account["features"]["can_use_creator_tools"] is False
        assert account["features"]["max_resolution_height"] == 720


class TestNoPaddleInvolvement:
    def test_grant_never_creates_a_paddle_subscription_id(self):
        c, admin_email = _signup()
        _promote(admin_email)
        _, target_email = _signup()
        target_id = _user_id(target_email)

        c.patch(f"/api/admin/users/{target_id}/subscription", json={"plan": "pro"})

        sub = _get_subscription(target_id)
        assert sub.provider_subscription_id is None
        assert sub.provider_customer_id is None
        assert sub.provider == "gifted"

    def test_full_lifecycle_never_calls_paddle_api(self):
        """The autouse _no_paddle_client fixture would raise if any Paddle
        client method were invoked - reaching the end of this sequence
        without an exception IS the assertion."""
        c, admin_email = _signup()
        _promote(admin_email)
        _, target_email = _signup()
        target_id = _user_id(target_email)

        c.patch(f"/api/admin/users/{target_id}/subscription", json={"plan": "pro"})
        c.patch(f"/api/admin/users/{target_id}/subscription", json={"plan": "creator"})
        c.patch(f"/api/admin/users/{target_id}/subscription", json={"plan": "free"})


class TestPaidSubscriptionPrecedence:
    def _make_paddle_pro_user(self) -> tuple[str, str, Subscription]:
        session = get_session_factory()()
        try:
            email = f"paid-{uuid.uuid4().hex[:10]}@example.com"
            user = auth_service.signup(session, email, "correcthorse9!").user
            sub = Subscription(
                user_id=user.id, provider="paddle", provider_subscription_id=f"sub_{uuid.uuid4().hex}",
                provider_customer_id="ctm_real", plan="pro", status="active",
            )
            session.add(sub)
            session.commit()
            return user.id, email, sub
        finally:
            session.close()

    def test_active_paddle_pro_cannot_be_changed_through_gifting(self):
        c, admin_email = _signup()
        _promote(admin_email)
        target_id, _, _ = self._make_paddle_pro_user()

        resp = c.patch(f"/api/admin/users/{target_id}/subscription", json={"plan": "creator"})
        assert resp.status_code == 409
        assert resp.json()["code"] == "PAID_SUBSCRIPTION_ACTIVE"

    def test_active_paddle_creator_cannot_be_changed_through_gifting(self):
        session = get_session_factory()()
        try:
            email = f"paid-creator-{uuid.uuid4().hex[:10]}@example.com"
            user = auth_service.signup(session, email, "correcthorse9!").user
            sub = Subscription(
                user_id=user.id, provider="paddle", provider_subscription_id=f"sub_{uuid.uuid4().hex}",
                provider_customer_id="ctm_real2", plan="creator", status="active",
            )
            session.add(sub)
            session.commit()
            target_id = user.id
        finally:
            session.close()

        c, admin_email = _signup()
        _promote(admin_email)
        resp = c.patch(f"/api/admin/users/{target_id}/subscription", json={"plan": "pro"})
        assert resp.status_code == 409

    def test_paddle_billing_record_is_unchanged_after_a_blocked_gift_attempt(self):
        c, admin_email = _signup()
        _promote(admin_email)
        target_id, _, original_sub = self._make_paddle_pro_user()

        c.patch(f"/api/admin/users/{target_id}/subscription", json={"plan": "free"})

        sub = _get_subscription(target_id)
        assert sub.id == original_sub.id
        assert sub.provider == "paddle"
        assert sub.plan == "pro"
        assert sub.status == "active"
        assert sub.provider_subscription_id == original_sub.provider_subscription_id

    def test_revoke_is_also_blocked_for_an_active_paddle_subscription(self):
        c, admin_email = _signup()
        _promote(admin_email)
        target_id, _, _ = self._make_paddle_pro_user()

        resp = c.patch(f"/api/admin/users/{target_id}/subscription", json={"plan": "free"})
        assert resp.status_code == 409

    def test_service_layer_raises_directly_for_paid_precedence(self, db_session):
        """Unit-level proof independent of the HTTP layer/route wiring."""
        admin = auth_service.signup(db_session, f"admin-{uuid.uuid4().hex[:8]}@example.com", "correcthorse9!").user
        target = auth_service.signup(db_session, f"paid-unit-{uuid.uuid4().hex[:8]}@example.com", "correcthorse9!").user
        db_session.add(Subscription(
            user_id=target.id, provider="paddle", provider_subscription_id=f"sub_{uuid.uuid4().hex}",
            plan="pro", status="active",
        ))
        db_session.flush()

        with pytest.raises(PaidSubscriptionActiveError):
            gift_subscription_service.grant_or_change(db_session, admin, target, Plan.CREATOR, None)


class TestRevenueExclusion:
    def test_gifted_pro_not_counted_as_paid_subscriber_in_overview(self):
        c, admin_email = _signup()
        _promote(admin_email)
        _, target_email = _signup()
        target_id = _user_id(target_email)

        before = c.get("/api/admin/overview").json()
        c.patch(f"/api/admin/users/{target_id}/subscription", json={"plan": "pro"})
        after = c.get("/api/admin/overview").json()

        assert after["paid_subscribers"] == before["paid_subscribers"]
        assert after["pro_count"] == before["pro_count"]
        assert after["gifted_subscribers"] == before["gifted_subscribers"] + 1

    def test_gifted_creator_not_counted_as_paid_subscriber_in_overview(self):
        c, admin_email = _signup()
        _promote(admin_email)
        _, target_email = _signup()
        target_id = _user_id(target_email)

        before = c.get("/api/admin/overview").json()
        c.patch(f"/api/admin/users/{target_id}/subscription", json={"plan": "creator"})
        after = c.get("/api/admin/overview").json()

        assert after["creator_count"] == before["creator_count"]
        assert after["paid_subscribers"] == before["paid_subscribers"]
        assert after["gifted_subscribers"] == before["gifted_subscribers"] + 1

    def test_gifted_grant_does_not_increase_analytics_paid_conversions(self):
        c, admin_email = _signup()
        _promote(admin_email)
        _, target_email = _signup()
        target_id = _user_id(target_email)

        before = c.get("/api/admin/analytics/overview?range=today").json()
        c.patch(f"/api/admin/users/{target_id}/subscription", json={"plan": "pro"})
        after = c.get("/api/admin/analytics/overview?range=today").json()

        assert after["paid_conversions"] == before["paid_conversions"]

    def test_gifted_grant_does_not_increase_revenue_active_or_new_paid(self):
        c, admin_email = _signup()
        _promote(admin_email)
        _, target_email = _signup()
        target_id = _user_id(target_email)

        before = c.get("/api/admin/analytics/revenue?range=today").json()
        c.patch(f"/api/admin/users/{target_id}/subscription", json={"plan": "creator"})
        after = c.get("/api/admin/analytics/revenue?range=today").json()

        assert after["active_paid_subscribers"] == before["active_paid_subscribers"]
        assert after["new_paid_subscribers"] == before["new_paid_subscribers"]
        assert after["gifted_active_subscriptions"] == before["gifted_active_subscriptions"] + 1
        assert after["gifted_events_this_period"] == before["gifted_events_this_period"] + 1


class TestAuditLog:
    def test_grant_is_recorded_with_admin_identity_and_plan_transition(self):
        c, admin_email = _signup()
        _promote(admin_email)
        _, target_email = _signup()
        target_id = _user_id(target_email)

        c.patch(f"/api/admin/users/{target_id}/subscription", json={"plan": "pro", "reason": "beta"})

        entries = c.get(f"/api/admin/audit-log?target_user_id={target_id}").json()
        assert len(entries) == 1
        entry = entries[0]
        assert entry["action"] == "gift_subscription_granted"
        assert entry["admin_email"] == admin_email
        assert entry["target_email"] == target_email
        assert entry["details"]["previous_plan"] == "free"
        assert entry["details"]["new_plan"] == "pro"
        assert entry["details"]["previous_source"] == "none"
        assert entry["details"]["new_source"] == "gifted"
        assert entry["details"]["reason"] == "beta"

    def test_change_between_gifted_tiers_is_recorded(self):
        c, admin_email = _signup()
        _promote(admin_email)
        _, target_email = _signup()
        target_id = _user_id(target_email)

        c.patch(f"/api/admin/users/{target_id}/subscription", json={"plan": "pro"})
        c.patch(f"/api/admin/users/{target_id}/subscription", json={"plan": "creator"})

        entries = c.get(f"/api/admin/audit-log?target_user_id={target_id}").json()
        actions = [e["action"] for e in entries]
        assert "gift_subscription_changed" in actions
        changed = next(e for e in entries if e["action"] == "gift_subscription_changed")
        assert changed["details"]["previous_plan"] == "pro"
        assert changed["details"]["new_plan"] == "creator"

    def test_revoke_is_recorded(self):
        c, admin_email = _signup()
        _promote(admin_email)
        _, target_email = _signup()
        target_id = _user_id(target_email)

        c.patch(f"/api/admin/users/{target_id}/subscription", json={"plan": "creator"})
        c.patch(f"/api/admin/users/{target_id}/subscription", json={"plan": "free", "reason": "no longer needed"})

        entries = c.get(f"/api/admin/audit-log?target_user_id={target_id}").json()
        revoked = next(e for e in entries if e["action"] == "gift_subscription_revoked")
        assert revoked["details"]["previous_plan"] == "creator"
        assert revoked["details"]["new_plan"] == "free"
        assert revoked["details"]["reason"] == "no longer needed"

    def test_gifted_analytics_events_are_recorded_server_side_only(self, db_session):
        c, admin_email = _signup()
        _promote(admin_email)
        _, target_email = _signup()
        target_id = _user_id(target_email)

        c.patch(f"/api/admin/users/{target_id}/subscription", json={"plan": "pro"})

        session = get_session_factory()()
        try:
            rows = session.execute(
                select(AnalyticsEvent).where(
                    AnalyticsEvent.event_type == "gifted_subscription_granted",
                    AnalyticsEvent.user_id == target_id,
                )
            ).scalars().all()
            assert len(rows) == 1
            assert rows[0].plan == "pro"
            assert rows[0].from_plan == "free"
        finally:
            session.close()

    def test_browser_cannot_forge_a_gifted_analytics_event(self):
        """The public analytics ingestion endpoint only accepts page_view -
        there is structurally no way to submit a gifted_subscription_*
        event from the browser."""
        c = TestClient(app)
        resp = c.post("/api/analytics/event", json={"event_type": "gifted_subscription_granted", "path": "/admin"})
        assert resp.status_code == 422
