"""HTTP-level regression tests: auth requirement enforcement, admin
authorization, rate limiting, and the full signup -> gated-download flow
through the real FastAPI routes (not just the service layer)."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from datetime import datetime, timedelta, timezone

from app.database.commercial_db import get_session_factory
from app.database.commercial_models import Subscription, User
from app.main import app
from app.services.download_manager import DownloadManager

client = TestClient(app)


@pytest.fixture(autouse=True)
def _stub_download_execution(monkeypatch):
    """create_job() schedules a real background download via asyncio.create_task
    - these tests only care about gating/ownership/routing, so replace the
    actual yt-dlp/network execution with a no-op rather than let a unit test
    reach out to a real video platform."""

    async def _noop(self, job_id: str) -> None:
        return None

    monkeypatch.setattr(DownloadManager, "_run_job", _noop)


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """Rate limiters are process-lifetime singletons keyed by client host, and
    TestClient always reports the same fake host - without resetting between
    tests, the signup/login limiters would eventually block later tests based
    on how many earlier tests happened to run first."""
    from app.services import rate_limit_service

    for limiter in (rate_limit_service.login_limiter, rate_limit_service.signup_limiter, rate_limit_service.password_reset_limiter):
        limiter._hits.clear()
    yield


def _signup(email: str | None = None) -> tuple[TestClient, str]:
    c = TestClient(app)
    email = email or f"api-{uuid.uuid4().hex[:12]}@example.com"
    resp = c.post("/api/auth/signup", json={"email": email, "password": "correcthorse9!"})
    assert resp.status_code == 201, resp.text
    return c, email


class TestAuthRequirement:
    def test_downloads_requires_auth(self):
        resp = TestClient(app).get("/api/downloads")
        assert resp.status_code == 401
        assert resp.json()["code"] == "AUTH_REQUIRED"

    def test_history_requires_auth(self):
        resp = TestClient(app).get("/api/history")
        assert resp.status_code == 401

    def test_account_requires_auth(self):
        resp = TestClient(app).get("/api/account")
        assert resp.status_code == 401

    def test_progress_stream_requires_auth(self):
        resp = TestClient(app).get("/api/progress/stream")
        assert resp.status_code == 401

    def test_settings_requires_auth(self):
        """Previously wide open - anyone unauthenticated could rewrite the
        shared download_dir/concurrency/theme/etc. for the whole server."""
        c = TestClient(app)
        assert c.get("/api/settings").status_code == 401
        assert c.put("/api/settings", json={"theme": "dark"}).status_code == 401

    def test_filesystem_open_requires_auth(self):
        """Previously wide open - anyone unauthenticated could ask the
        server to run its OS file-open handler on a path."""
        c = TestClient(app)
        assert c.post("/api/fs/open", json={"path": "/tmp"}).status_code == 401
        assert c.post("/api/fs/open-folder", json={"path": "/tmp"}).status_code == 401
        assert c.post("/api/fs/validate-folder", json={"path": "/tmp"}).status_code == 401


def _promote(email: str) -> None:
    session = get_session_factory()()
    try:
        db_user = session.execute(select(User).where(User.email == email)).scalars().first()
        db_user.role = "admin"
        session.commit()
    finally:
        session.close()


class TestAdminAuthorization:
    def test_regular_user_cannot_list_admin_users(self):
        c, _ = _signup()
        resp = c.get("/api/admin/users")
        assert resp.status_code == 403
        assert resp.json()["code"] == "FORBIDDEN"

    def test_regular_user_cannot_grant_credits(self):
        c, _ = _signup()
        resp = c.post(f"/api/admin/users/{uuid.uuid4()}/grant-credits", json={"credits": 10, "reason": "test"})
        assert resp.status_code == 403

    def test_regular_user_cannot_get_user_detail(self):
        c, _ = _signup()
        resp = c.get(f"/api/admin/users/{uuid.uuid4()}")
        assert resp.status_code == 403

    def test_regular_user_cannot_set_account_status(self):
        c, _ = _signup()
        resp = c.post(f"/api/admin/users/{uuid.uuid4()}/status", json={"status": "disabled"})
        assert resp.status_code == 403

    def test_regular_user_cannot_list_billing_events(self):
        c, _ = _signup()
        resp = c.get("/api/admin/billing-events")
        assert resp.status_code == 403

    def test_regular_user_cannot_list_overview(self):
        c, _ = _signup()
        resp = c.get("/api/admin/overview")
        assert resp.status_code == 403

    def test_regular_user_cannot_list_audit_log(self):
        c, _ = _signup()
        resp = c.get("/api/admin/audit-log")
        assert resp.status_code == 403

    def test_admin_can_list_users(self):
        c, email = _signup()
        _promote(email)
        resp = c.get("/api/admin/users?search=" + email)
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_admin_can_get_user_detail(self):
        c, email = _signup()
        _promote(email)
        session = get_session_factory()()
        try:
            user_id = session.execute(select(User.id).where(User.email == email)).scalar_one()
        finally:
            session.close()
        resp = c.get(f"/api/admin/users/{user_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == email
        assert body["role"] == "admin"

    def test_admin_get_unknown_user_detail_is_404(self):
        c, email = _signup()
        _promote(email)
        resp = c.get(f"/api/admin/users/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestAdminCreditsAndStatus:
    def test_grant_credits_increases_included_credits_and_is_audited(self):
        c, admin_email = _signup()
        _promote(admin_email)
        target_c, target_email = _signup()
        session = get_session_factory()()
        try:
            target_id = session.execute(select(User.id).where(User.email == target_email)).scalar_one()
        finally:
            session.close()

        resp = c.post(
            f"/api/admin/users/{target_id}/grant-credits",
            json={"credits": 25, "reason": "support case #123"},
        )
        assert resp.status_code == 200

        audit = c.get("/api/admin/audit-log")
        assert audit.status_code == 200
        entries = audit.json()
        grant_entries = [e for e in entries if e["action"] == "grant_credits" and e["target_user_id"] == target_id]
        assert len(grant_entries) == 1
        assert grant_entries[0]["details"]["credits"] == 25
        assert grant_entries[0]["details"]["reason"] == "support case #123"
        assert grant_entries[0]["admin_email"] == admin_email
        assert grant_entries[0]["target_email"] == target_email

    def test_grant_credits_reports_bonus_separately_from_plan_base(self):
        """credits_bonus should reflect only the admin-granted top-up, not
        the plan's own base allocation - the two must never be conflated."""
        c, admin_email = _signup()
        _promote(admin_email)
        target_c, target_email = _signup()
        session = get_session_factory()()
        try:
            target = session.execute(select(User).where(User.email == target_email)).scalars().first()
            now = datetime.now(timezone.utc)
            session.add(
                Subscription(
                    user_id=target.id,
                    provider="paddle",
                    provider_subscription_id=f"sub_{uuid.uuid4().hex[:12]}",
                    plan="pro",
                    status="active",
                    current_period_start=now,
                    current_period_end=now + timedelta(days=30),
                )
            )
            session.commit()
            target_id = target.id
        finally:
            session.close()

        before = c.get(f"/api/admin/users/{target_id}").json()
        assert before["plan"] == "pro"
        assert before["credits_included"] == 150  # Pro's base monthly allocation
        assert before["credits_bonus"] == 0

        resp = c.post(f"/api/admin/users/{target_id}/grant-credits", json={"credits": 30, "reason": "bonus"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["credits_included"] == 180  # 150 base + 30 granted
        assert body["credits_bonus"] == 30

    def test_grant_credits_unknown_user_is_404(self):
        c, admin_email = _signup()
        _promote(admin_email)
        resp = c.post(f"/api/admin/users/{uuid.uuid4()}/grant-credits", json={"credits": 10, "reason": "x"})
        assert resp.status_code == 404

    def test_disable_and_reactivate_are_audited(self):
        c, admin_email = _signup()
        _promote(admin_email)
        target_c, target_email = _signup()
        session = get_session_factory()()
        try:
            target_id = session.execute(select(User.id).where(User.email == target_email)).scalar_one()
        finally:
            session.close()

        disable_resp = c.post(f"/api/admin/users/{target_id}/status", json={"status": "disabled"})
        assert disable_resp.status_code == 200
        assert disable_resp.json()["status"] == "disabled"

        reactivate_resp = c.post(f"/api/admin/users/{target_id}/status", json={"status": "active"})
        assert reactivate_resp.status_code == 200
        assert reactivate_resp.json()["status"] == "active"

        audit = c.get(f"/api/admin/audit-log?target_user_id={target_id}").json()
        actions = [e["action"] for e in audit]
        assert "disable_account" in actions
        assert "reactivate_account" in actions

    def test_self_disable_is_rejected_and_not_audited(self):
        c, admin_email = _signup()
        _promote(admin_email)
        session = get_session_factory()()
        try:
            admin_id = session.execute(select(User.id).where(User.email == admin_email)).scalar_one()
        finally:
            session.close()

        resp = c.post(f"/api/admin/users/{admin_id}/status", json={"status": "disabled"})
        assert resp.status_code == 403

        audit = c.get("/api/admin/audit-log").json()
        assert not any(e["target_user_id"] == admin_id and e["action"] == "disable_account" for e in audit)

    def test_disabled_status_unchanged_is_not_re_audited(self):
        """Re-submitting the same status shouldn't add a duplicate audit
        entry - only an actual transition is logged."""
        c, admin_email = _signup()
        _promote(admin_email)
        target_c, target_email = _signup()
        session = get_session_factory()()
        try:
            target_id = session.execute(select(User.id).where(User.email == target_email)).scalar_one()
        finally:
            session.close()

        c.post(f"/api/admin/users/{target_id}/status", json={"status": "active"})
        audit = c.get(f"/api/admin/audit-log?target_user_id={target_id}").json()
        assert len(audit) == 0


class TestAdminOverview:
    def test_overview_counts_reflect_real_users(self):
        c, admin_email = _signup()
        _promote(admin_email)
        resp = c.get("/api/admin/overview")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_users"] >= 1
        assert body["active_users"] >= 1
        assert body["free_count"] + body["paid_subscribers"] == body["total_users"]
        assert body["pro_count"] + body["creator_count"] == body["paid_subscribers"]
        assert isinstance(body["recent_billing_failures"], list)
        assert isinstance(body["recent_admin_actions"], list)

    def test_overview_reflects_recent_admin_action(self):
        c, admin_email = _signup()
        _promote(admin_email)
        target_c, target_email = _signup()
        session = get_session_factory()()
        try:
            target_id = session.execute(select(User.id).where(User.email == target_email)).scalar_one()
        finally:
            session.close()
        c.post(f"/api/admin/users/{target_id}/grant-credits", json={"credits": 5, "reason": "test"})

        resp = c.get("/api/admin/overview")
        recent = resp.json()["recent_admin_actions"]
        assert any(a["target_user_id"] == target_id and a["action"] == "grant_credits" for a in recent)


class TestAdminBillingEvents:
    def test_admin_can_list_billing_events(self):
        c, admin_email = _signup()
        _promote(admin_email)
        resp = c.get("/api/admin/billing-events")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestCheckoutValidation:
    def test_checkout_requires_auth(self):
        resp = TestClient(app).post("/api/billing/checkout", json={"plan": "pro", "billing_period": "monthly"})
        assert resp.status_code == 401

    def test_checkout_rejects_free_plan(self):
        c, _ = _signup()
        resp = c.post("/api/billing/checkout", json={"plan": "free", "billing_period": "monthly"})
        assert resp.status_code == 422  # Free doesn't go through checkout

    def test_checkout_reports_a_clean_error_when_unconfigured(self):
        """No PADDLE_*_PRICE_ID/PADDLE_CLIENT_TOKEN in this test environment
        (there's no real Paddle Sandbox account here) - this must surface as
        a clear 502 billing error, not an unhandled 500."""
        c, _ = _signup()
        resp = c.post("/api/billing/checkout", json={"plan": "pro", "billing_period": "monthly"})
        assert resp.status_code == 502
        assert resp.json()["code"] == "BILLING_ERROR"

    def test_checkout_returns_environment_when_configured(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.paddle_service.get_commercial_settings",
            lambda: type(
                "S",
                (),
                {
                    "paddle_pro_monthly_price_id": "pri_test_pro_monthly",
                    "paddle_pro_annual_price_id": "",
                    "paddle_creator_monthly_price_id": "",
                    "paddle_creator_annual_price_id": "",
                    "paddle_client_token": "test_client_token",
                    "paddle_env": "sandbox",
                },
            )(),
        )
        c, _ = _signup()
        resp = c.post("/api/billing/checkout", json={"plan": "pro", "billing_period": "monthly"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["environment"] == "sandbox"
        assert body["price_id"] == "pri_test_pro_monthly"
        assert body["client_token"] == "test_client_token"


class TestLoginRateLimiting:
    def test_login_is_rate_limited_after_repeated_failures(self):
        c, email = _signup()
        for _ in range(10):
            resp = c.post("/api/auth/login", json={"email": email, "password": "wrongpassword"})
            assert resp.status_code == 401
        resp = c.post("/api/auth/login", json={"email": email, "password": "wrongpassword"})
        assert resp.status_code == 429
        assert resp.json()["code"] == "RATE_LIMITED"


class TestWebhookRejectsBadSignature:
    def test_webhook_without_signature_rejected(self):
        resp = client.post("/api/billing/paddle/webhook", content=b"{}", headers={"Content-Type": "application/json"})
        assert resp.status_code == 400
        assert resp.json()["code"] == "INVALID_WEBHOOK_SIGNATURE"


class TestSignupToGatedDownloadFlow:
    def test_free_user_can_download_within_limits_and_is_blocked_over_them(self):
        c, _ = _signup()

        # Requesting above the Free resolution cap is rejected up front.
        resp = c.post(
            "/api/downloads",
            json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "media_type": "video", "quality_key": "1440"},
        )
        assert resp.status_code == 402
        assert resp.json()["code"] == "PLAN_LIMIT_REACHED"

        # A request within the cap is accepted and reserved.
        resp = c.post(
            "/api/downloads",
            json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "media_type": "video", "quality_key": "480"},
        )
        assert resp.status_code == 201
        job_id = resp.json()["id"]

        # The job belongs to this user and is visible in their own list.
        resp = c.get("/api/downloads")
        assert resp.status_code == 200
        assert any(j["id"] == job_id for j in resp.json())

    def test_job_is_not_visible_to_a_different_user(self):
        c1, _ = _signup()
        resp = c1.post(
            "/api/downloads",
            json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "media_type": "video", "quality_key": "480"},
        )
        assert resp.status_code == 201
        job_id = resp.json()["id"]

        c2, _ = _signup()
        resp = c2.get(f"/api/downloads/{job_id}")
        assert resp.status_code == 404  # not 403 - existence isn't leaked cross-user

        resp = c2.get("/api/downloads")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_unsupported_url_rejected_before_any_reservation(self):
        c, _ = _signup()
        resp = c.post("/api/downloads", json={"url": "not a url", "media_type": "video", "quality_key": "480"})
        assert resp.status_code == 400
