"""HTTP-level regression tests: auth requirement enforcement, admin
authorization, rate limiting, and the full signup -> gated-download flow
through the real FastAPI routes (not just the service layer)."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database.commercial_db import get_session_factory
from app.database.commercial_models import User
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

    def test_admin_can_list_users(self):
        c, email = _signup()
        session = get_session_factory()()
        try:
            db_user = session.execute(select(User).where(User.email == email)).scalars().first()
            db_user.role = "admin"
            session.commit()
        finally:
            session.close()
        resp = c.get("/api/admin/users?search=" + email)
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1


class TestCheckoutValidation:
    def test_checkout_requires_auth(self):
        resp = TestClient(app).post("/api/billing/checkout", json={"plan": "pro", "billing_period": "monthly"})
        assert resp.status_code == 401

    def test_checkout_rejects_free_plan(self):
        c, _ = _signup()
        resp = c.post("/api/billing/checkout", json={"plan": "free", "billing_period": "monthly"})
        assert resp.status_code == 422  # Free doesn't go through checkout


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
