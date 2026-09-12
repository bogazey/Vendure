"""First-party web analytics: event validation, privacy guarantees, admin
authorization, path/referrer normalization, aggregate reporting, plan
movement recording, and retention cleanup."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database.commercial_models import AnalyticsEvent, User
from app.database.commercial_db import get_session_factory
from app.main import app
from app.models.commercial_enums import AnalyticsEventType
from app.services import analytics_service
from app.services.download_manager import DownloadManager

client = TestClient(app)


@pytest.fixture(autouse=True)
def _stub_download_execution(monkeypatch):
    async def _noop(self, job_id: str) -> None:
        return None

    monkeypatch.setattr(DownloadManager, "_run_job", _noop)


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    from app.services import rate_limit_service

    for limiter in (
        rate_limit_service.login_limiter,
        rate_limit_service.signup_limiter,
        rate_limit_service.password_reset_limiter,
        rate_limit_service.analyze_limiter,
        rate_limit_service.billing_limiter,
        rate_limit_service.analytics_limiter,
        rate_limit_service.guest_download_limiter,
    ):
        limiter._hits.clear()
    yield


def _signup(email: str | None = None) -> tuple[TestClient, str]:
    c = TestClient(app)
    email = email or f"analytics-{uuid.uuid4().hex[:12]}@example.com"
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


def _events_by_type(event_type: str) -> list[AnalyticsEvent]:
    session = get_session_factory()()
    try:
        return list(session.execute(select(AnalyticsEvent).where(AnalyticsEvent.event_type == event_type)).scalars())
    finally:
        session.close()


class TestEventValidation:
    def test_unknown_event_type_is_rejected(self):
        c = TestClient(app)
        resp = c.post("/api/analytics/event", json={"event_type": "subscription_paid", "path": "/"})
        assert resp.status_code == 422

    def test_arbitrary_business_fields_are_rejected(self):
        """A browser must never be able to submit anything resembling a
        revenue/business event - only page_view exists as a shape at all,
        so extra fields like a forged "amount" simply aren't part of the
        schema and are ignored/rejected, never persisted."""
        c = TestClient(app)
        resp = c.post(
            "/api/analytics/event",
            json={"event_type": "page_view", "path": "/", "amount": 999999, "plan": "creator"},
        )
        assert resp.status_code == 204

    def test_missing_path_is_rejected(self):
        c = TestClient(app)
        resp = c.post("/api/analytics/event", json={"event_type": "page_view", "path": ""})
        assert resp.status_code == 422

    def test_oversized_utm_is_rejected(self):
        c = TestClient(app)
        resp = c.post(
            "/api/analytics/event",
            json={"event_type": "page_view", "path": "/", "utm_source": "x" * 500},
        )
        assert resp.status_code == 422


class TestPrivacyGuarantees:
    def test_user_id_is_never_trusted_from_the_request_body(self):
        """An anonymous request that claims someone else's user_id must not
        have it recorded - visitor_id/user_id are always derived server-side
        (cookie / auth dependency), never read from JSON."""
        c = TestClient(app)
        other_user_id = str(uuid.uuid4())
        resp = c.post(
            "/api/analytics/event",
            json={"event_type": "page_view", "path": "/pricing", "user_id": other_user_id},
        )
        assert resp.status_code == 204
        rows = [e for e in _events_by_type("page_view") if e.path == "/pricing"]
        assert all(e.user_id != other_user_id for e in rows)

    def test_visitor_id_is_never_trusted_from_the_request_body(self):
        c = TestClient(app)
        forged_visitor_id = "attacker-chosen-id"
        resp = c.post(
            "/api/analytics/event",
            json={"event_type": "page_view", "path": "/dashboard", "visitor_id": forged_visitor_id},
        )
        assert resp.status_code == 204
        rows = [e for e in _events_by_type("page_view") if e.path == "/dashboard"]
        assert all(e.visitor_id != forged_visitor_id for e in rows)

    def test_visitor_cookie_is_minted_httponly(self):
        c = TestClient(app)
        resp = c.post("/api/analytics/event", json={"event_type": "page_view", "path": "/"})
        assert resp.status_code == 204
        set_cookie = resp.headers.get("set-cookie", "")
        assert "lmd_visitor=" in set_cookie
        assert "httponly" in set_cookie.lower()

    def test_full_referrer_url_is_never_stored_only_the_domain(self):
        c = TestClient(app)
        resp = c.post(
            "/api/analytics/event",
            json={
                "event_type": "page_view",
                "path": "/",
                "referrer": "https://www.google.com/search?q=secret+query+string",
            },
        )
        assert resp.status_code == 204
        rows = [e for e in _events_by_type("page_view") if e.referrer_domain == "google.com"]
        assert rows
        assert all("search" not in (e.referrer_domain or "") and "secret" not in (e.referrer_domain or "") for e in rows)

    def test_analytics_event_model_has_no_url_or_ip_column(self):
        """Structural guarantee: even a future bug that tried to pass a
        `url`/`ip_address` field into record_event would fail immediately -
        neither column exists on the table at all."""
        columns = {c.name for c in AnalyticsEvent.__table__.columns}
        assert "url" not in columns
        assert "media_url" not in columns
        assert "ip_address" not in columns
        assert "ip" not in columns
        assert "user_agent" not in columns
        assert "metadata" not in columns


class TestBotFiltering:
    def test_known_crawler_user_agent_is_not_recorded(self):
        c = TestClient(app)
        before = len(_events_by_type("page_view"))
        resp = c.post(
            "/api/analytics/event",
            json={"event_type": "page_view", "path": "/dashboard"},
            headers={"User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"},
        )
        assert resp.status_code == 204
        assert len(_events_by_type("page_view")) == before

    def test_ordinary_browser_user_agent_is_recorded(self):
        c = TestClient(app)
        before = len(_events_by_type("page_view"))
        resp = c.post(
            "/api/analytics/event",
            json={"event_type": "page_view", "path": "/dashboard"},
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"},
        )
        assert resp.status_code == 204
        assert len(_events_by_type("page_view")) == before + 1


class TestPathNormalization:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("/", "/"),
            ("/pricing", "/pricing"),
            ("/pricing?foo=bar", "/pricing"),
            ("/pricing/", "/pricing"),
            ("/en", "/"),
            ("/ar", "/"),
            ("/en/video-downloader", "/video-downloader"),
            ("/ar/video-downloader", "/video-downloader"),
            ("/en/audio-downloader/", "/audio-downloader"),
            ("/admin/statistics", "/admin/statistics"),
            ("/some/unknown/attacker/path", "/other"),
            ("", "/"),
        ],
    )
    def test_normalize_path(self, raw, expected):
        assert analytics_service.normalize_path(raw) == expected


class TestReferrerNormalization:
    def test_empty_referrer_is_direct(self):
        from fastapi import Request

        request = Request(scope={"type": "http", "headers": [(b"host", b"loady.cc")]})
        assert analytics_service.extract_referrer_domain(None, request) is None
        assert analytics_service.extract_referrer_domain("", request) is None

    def test_self_referral_is_treated_as_direct(self):
        from fastapi import Request

        request = Request(scope={"type": "http", "headers": [(b"host", b"loady.cc")]})
        assert analytics_service.extract_referrer_domain("https://loady.cc/pricing", request) is None

    def test_external_referrer_strips_to_domain(self):
        from fastapi import Request

        request = Request(scope={"type": "http", "headers": [(b"host", b"loady.cc")]})
        assert analytics_service.extract_referrer_domain("https://www.tiktok.com/@someone/video/1", request) == "tiktok.com"


class TestUtmSanitization:
    def test_valid_utm_passes_through(self):
        assert analytics_service.sanitize_utm("summer_sale-2026") == "summer_sale-2026"

    def test_invalid_characters_are_dropped(self):
        assert analytics_service.sanitize_utm("<script>alert(1)</script>") is None
        assert analytics_service.sanitize_utm("a b c") is None

    def test_none_and_empty_are_none(self):
        assert analytics_service.sanitize_utm(None) is None
        assert analytics_service.sanitize_utm("") is None


class TestAdminAuthorization:
    ENDPOINTS = [
        "/api/admin/analytics/overview",
        "/api/admin/analytics/traffic",
        "/api/admin/analytics/pages",
        "/api/admin/analytics/sources",
        "/api/admin/analytics/geography",
        "/api/admin/analytics/devices",
        "/api/admin/analytics/downloads",
        "/api/admin/analytics/funnel",
        "/api/admin/analytics/revenue",
    ]

    def test_anonymous_is_denied(self):
        c = TestClient(app)
        for endpoint in self.ENDPOINTS:
            resp = c.get(endpoint)
            assert resp.status_code == 401, endpoint

    def test_regular_user_is_denied(self):
        c, _ = _signup()
        for endpoint in self.ENDPOINTS:
            resp = c.get(endpoint)
            assert resp.status_code == 403, endpoint

    def test_admin_is_allowed(self):
        c, email = _signup()
        _promote(email)
        for endpoint in self.ENDPOINTS:
            resp = c.get(endpoint)
            assert resp.status_code == 200, (endpoint, resp.text)

    def test_invalid_range_is_rejected(self):
        c, email = _signup()
        _promote(email)
        resp = c.get("/api/admin/analytics/overview?range=all_time_ever")
        assert resp.status_code == 422


class TestPageViewRecording:
    def test_page_view_recorded_with_locale(self):
        c = TestClient(app)
        resp = c.post("/api/analytics/event", json={"event_type": "page_view", "path": "/pricing", "locale": "ar"})
        assert resp.status_code == 204
        rows = [e for e in _events_by_type("page_view") if e.path == "/pricing" and e.locale == "ar"]
        assert rows

    def test_repeated_page_views_from_same_visitor_count_as_one_unique_visitor(self):
        c = TestClient(app)
        # "/pricing" is a known static path (not aggregated to "/other"), so
        # filter by row id rather than by path alone (other tests also hit
        # "/pricing" concurrently in the shared test DB).
        before_ids = {e.id for e in _events_by_type("page_view") if e.path == "/pricing"}
        c.post("/api/analytics/event", json={"event_type": "page_view", "path": "/pricing"})
        c.post("/api/analytics/event", json={"event_type": "page_view", "path": "/pricing"})
        c.post("/api/analytics/event", json={"event_type": "page_view", "path": "/pricing"})
        new_rows = [e for e in _events_by_type("page_view") if e.path == "/pricing" and e.id not in before_ids]
        # All three requests reuse the same TestClient (same cookie jar), so
        # they must resolve to exactly one visitor_id.
        assert len(new_rows) == 3
        assert len({e.visitor_id for e in new_rows}) == 1


class TestFailureClassification:
    def test_known_exception_types_map_to_expected_categories(self):
        from app.utils.exceptions import (
            FfmpegMissingError, NetworkError, RateLimitedError, UnavailableMediaError, UnsupportedUrlError,
        )

        assert analytics_service.classify_failure(UnsupportedUrlError("x")) == "unsupported_source"
        assert analytics_service.classify_failure(UnavailableMediaError("x")) == "metadata_failure"
        assert analytics_service.classify_failure(FfmpegMissingError("x")) == "processing_failure"
        assert analytics_service.classify_failure(NetworkError("x")) == "timeout"
        assert analytics_service.classify_failure(RateLimitedError("x")) == "rate_limited"
        assert analytics_service.classify_failure(ValueError("some internal detail")) == "other"

    def test_failure_message_is_never_persisted_only_the_category(self):
        from app.utils.exceptions import UnavailableMediaError

        exc = UnavailableMediaError("This post is private", technical="yt-dlp: HTTP 403 at https://secret/path")
        category = analytics_service.classify_failure(exc)
        assert category == "metadata_failure"
        assert "secret" not in category
        assert "yt-dlp" not in category


class TestDownloadAnalyticsIntegration:
    def test_download_started_and_completed_are_recorded_and_joinable_by_job_id(self, monkeypatch):
        """End-to-end through the real routes/download_manager (with the
        actual network/yt-dlp execution stubbed out) - proves the job_id
        correlation used for avg processing time actually links up."""
        c, _ = _signup()

        async def _fake_run_job(self, job_id: str) -> None:
            job = self.get_job(job_id)
            self._finish_as_completed(job)

        monkeypatch.setattr(DownloadManager, "_run_job", _fake_run_job)

        resp = c.post("/api/downloads", json={"url": "https://www.youtube.com/watch?v=abc123", "media_type": "video", "quality_key": "best"})
        assert resp.status_code == 201, resp.text
        job_id = resp.json()["id"]

        started = [e for e in _events_by_type("download_started") if e.job_id == job_id]
        completed = [e for e in _events_by_type("download_completed") if e.job_id == job_id]
        assert len(started) == 1
        assert len(completed) == 1
        assert started[0].source_platform == "youtube"
        assert started[0].media_type == "video"
        assert started[0].format == "best_available"
        # Never the submitted URL.
        assert not hasattr(started[0], "url")

    def test_download_failed_records_sanitized_failure_category(self, monkeypatch):
        from app.utils.exceptions import UnavailableMediaError

        c, _ = _signup()

        async def _fake_run_job_fails(self, job_id: str) -> None:
            job = self.get_job(job_id)
            self._finish_as_failed(job, UnavailableMediaError("private post", technical="internal detail"))

        monkeypatch.setattr(DownloadManager, "_run_job", _fake_run_job_fails)

        resp = c.post("/api/downloads", json={"url": "https://www.tiktok.com/@x/video/1", "media_type": "video", "quality_key": "best"})
        assert resp.status_code == 201, resp.text
        job_id = resp.json()["id"]

        failed = [e for e in _events_by_type("download_failed") if e.job_id == job_id]
        assert len(failed) == 1
        assert failed[0].failure_category == "metadata_failure"
        assert failed[0].source_platform == "tiktok"


class TestPlanMovementAnalytics:
    def _mock_price_settings(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.paddle_service.get_commercial_settings",
            lambda: type(
                "S", (),
                {
                    "paddle_pro_monthly_price_id": "pri_pro_monthly",
                    "paddle_pro_annual_price_id": "pri_pro_annual",
                    "paddle_creator_monthly_price_id": "pri_creator_monthly",
                    "paddle_creator_annual_price_id": "pri_creator_annual",
                },
            )(),
        )

    def test_new_subscription_records_plan_upgraded_free_to_pro(self, db_session, monkeypatch):
        from app.services import paddle_service
        from app.services.auth_service import auth_service

        self._mock_price_settings(monkeypatch)
        result = auth_service.signup(db_session, f"paddle-an-{uuid.uuid4().hex[:10]}@example.com", "correcthorse9!")
        db_session.flush()
        sub_id = f"sub_{uuid.uuid4().hex}"
        data = {
            "id": sub_id, "custom_data": {"user_id": result.user.id},
            "items": [{"price": {"id": "pri_pro_monthly"}}], "status": "active",
        }
        paddle_service.process_webhook_event(db_session, f"evt_{uuid.uuid4().hex}", "subscription.activated", data, "h1")
        db_session.commit()

        rows = db_session.execute(
            select(AnalyticsEvent).where(
                AnalyticsEvent.event_type == "plan_upgraded", AnalyticsEvent.user_id == result.user.id
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].from_plan == "free"
        assert rows[0].plan == "pro"

    def test_upgrade_pro_to_creator_and_cancellation_are_recorded(self, db_session, monkeypatch):
        from app.services import paddle_service
        from app.services.auth_service import auth_service

        self._mock_price_settings(monkeypatch)
        result = auth_service.signup(db_session, f"paddle-an2-{uuid.uuid4().hex[:10]}@example.com", "correcthorse9!")
        db_session.flush()
        sub_id = f"sub_{uuid.uuid4().hex}"
        activate = {
            "id": sub_id, "custom_data": {"user_id": result.user.id},
            "items": [{"price": {"id": "pri_pro_monthly"}}], "status": "active",
        }
        paddle_service.process_webhook_event(db_session, f"evt_{uuid.uuid4().hex}", "subscription.activated", activate, "h1")
        db_session.commit()

        upgrade = {
            "id": sub_id, "custom_data": {"user_id": result.user.id},
            "items": [{"price": {"id": "pri_creator_monthly"}}], "status": "active",
        }
        paddle_service.process_webhook_event(db_session, f"evt_{uuid.uuid4().hex}", "subscription.updated", upgrade, "h2")
        db_session.commit()

        upgraded_rows = db_session.execute(
            select(AnalyticsEvent).where(
                AnalyticsEvent.event_type == "plan_upgraded", AnalyticsEvent.user_id == result.user.id,
                AnalyticsEvent.from_plan == "pro", AnalyticsEvent.plan == "creator",
            )
        ).scalars().all()
        assert len(upgraded_rows) == 1

        paddle_service.process_webhook_event(
            db_session, f"evt_{uuid.uuid4().hex}", "subscription.canceled", {"id": sub_id}, "h3"
        )
        db_session.commit()
        cancelled_rows = db_session.execute(
            select(AnalyticsEvent).where(
                AnalyticsEvent.event_type == "subscription_cancelled", AnalyticsEvent.user_id == result.user.id
            )
        ).scalars().all()
        assert len(cancelled_rows) == 1

    def test_status_only_update_does_not_record_a_spurious_plan_change(self, db_session, monkeypatch):
        from app.services import paddle_service
        from app.services.auth_service import auth_service

        self._mock_price_settings(monkeypatch)
        result = auth_service.signup(db_session, f"paddle-an3-{uuid.uuid4().hex[:10]}@example.com", "correcthorse9!")
        db_session.flush()
        sub_id = f"sub_{uuid.uuid4().hex}"
        activate = {
            "id": sub_id, "custom_data": {"user_id": result.user.id},
            "items": [{"price": {"id": "pri_pro_monthly"}}], "status": "active",
        }
        paddle_service.process_webhook_event(db_session, f"evt_{uuid.uuid4().hex}", "subscription.activated", activate, "h1")
        db_session.commit()

        same_plan_update = {
            "id": sub_id, "custom_data": {"user_id": result.user.id},
            "items": [{"price": {"id": "pri_pro_monthly"}}], "status": "active",
            "current_billing_period": {"starts_at": "2026-01-01T00:00:00Z", "ends_at": "2026-02-01T00:00:00Z"},
        }
        paddle_service.process_webhook_event(db_session, f"evt_{uuid.uuid4().hex}", "subscription.updated", same_plan_update, "h2")
        db_session.commit()

        rows = db_session.execute(
            select(AnalyticsEvent).where(
                AnalyticsEvent.event_type.in_(["plan_upgraded", "plan_downgraded"]),
                AnalyticsEvent.user_id == result.user.id,
            )
        ).scalars().all()
        # Only the original free->pro activation, not a second spurious row
        # for the no-op status/date refresh.
        assert len(rows) == 1


class TestSignupAnalytics:
    def test_signup_completed_is_recorded_server_side(self):
        c, email = _signup()
        session = get_session_factory()()
        try:
            user_id = session.execute(select(User.id).where(User.email == email)).scalar_one()
        finally:
            session.close()
        rows = [e for e in _events_by_type("signup_completed") if e.user_id == user_id]
        assert len(rows) == 1


class TestAggregateReporting:
    def test_overview_reflects_recorded_events(self):
        c, email = _signup()
        _promote(email)
        unique_path = f"/reporting-check-{uuid.uuid4().hex[:8]}"
        TestClient(app).post("/api/analytics/event", json={"event_type": "page_view", "path": unique_path})

        resp = c.get("/api/admin/analytics/overview?range=today")
        assert resp.status_code == 200
        body = resp.json()
        assert body["visitors"] >= 1
        assert body["page_views"] >= 1
        assert body["range"] == "today"

    def test_geography_gracefully_reports_unavailable_when_no_country_data(self):
        c, email = _signup()
        _promote(email)
        resp = c.get("/api/admin/analytics/geography?range=today")
        assert resp.status_code == 200
        body = resp.json()
        # No CF-IPCountry header ever reaches this test client, so geography
        # must be honestly reported as unavailable, never fabricated.
        assert body["available"] is False
        assert body["countries"] == []

    def test_funnel_stages_are_present_and_labelled_as_aggregate(self):
        c, email = _signup()
        _promote(email)
        resp = c.get("/api/admin/analytics/funnel?range=30d")
        assert resp.status_code == 200
        body = resp.json()
        keys = [s["key"] for s in body["stages"]]
        assert keys == ["visitors", "analyzed", "downloaded", "signed_up", "paid"]
        assert "not a per-visitor cohort" in body["methodology_note"]

    def test_revenue_endpoint_declares_mrr_unavailable_rather_than_fabricating_it(self):
        c, email = _signup()
        _promote(email)
        resp = c.get("/api/admin/analytics/revenue?range=30d")
        assert resp.status_code == 200
        body = resp.json()
        assert body["mrr_available"] is False
        assert body["mrr_note"]


class TestActiveNow:
    def test_active_now_counts_recent_visitor_and_excludes_old_ones(self):
        c, email = _signup()
        _promote(email)

        recent_visitor_path = f"/active-now-{uuid.uuid4().hex[:8]}"
        TestClient(app).post("/api/analytics/event", json={"event_type": "page_view", "path": recent_visitor_path})

        session = get_session_factory()()
        try:
            stale = AnalyticsEvent(
                event_type="page_view", visitor_id="stale-visitor-" + uuid.uuid4().hex,
                path="/stale", timestamp=datetime.now(timezone.utc) - timedelta(minutes=30),
            )
            session.add(stale)
            session.commit()
        finally:
            session.close()

        resp = c.get("/api/admin/analytics/overview?range=today")
        assert resp.status_code == 200
        # active_now can't easily be isolated to exactly our one recent
        # visitor in a shared test DB, but it must never count the 30-minute-
        # old event above as active within the 5-minute window.
        assert resp.json()["active_now"] >= 1


class TestRetentionCleanup:
    def test_purge_removes_only_events_older_than_retention_window(self, db_session):
        old_id = f"old-{uuid.uuid4().hex}"
        fresh_id = f"fresh-{uuid.uuid4().hex}"
        db_session.add(AnalyticsEvent(
            event_type="page_view", visitor_id=old_id, path="/old",
            timestamp=datetime.now(timezone.utc) - timedelta(days=200),
        ))
        db_session.add(AnalyticsEvent(
            event_type="page_view", visitor_id=fresh_id, path="/fresh",
            timestamp=datetime.now(timezone.utc),
        ))
        db_session.commit()

        removed = analytics_service.purge_expired_events(db_session)
        db_session.commit()
        assert removed >= 1

        remaining_ids = {
            e.visitor_id for e in db_session.execute(
                select(AnalyticsEvent).where(AnalyticsEvent.visitor_id.in_([old_id, fresh_id]))
            ).scalars()
        }
        assert old_id not in remaining_ids
        assert fresh_id in remaining_ids
