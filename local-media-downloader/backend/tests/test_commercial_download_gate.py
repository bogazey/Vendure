"""DownloadGateService: the single choke point every download request must
pass through - entitlement checks, then an atomic credit reservation."""
import uuid

import pytest

from app.models.commercial_enums import Plan
from app.models.enums import ContainerMode, CookieSource
from app.models.schemas import AppSettings, CreateDownloadRequest
from app.services.auth_service import auth_service
from app.services.download_gate_service import download_gate_service
from app.services.usage_service import usage_service
from app.utils.exceptions import DailyLimitReachedError, FeatureNotIncludedError, PlanLimitReachedError


def _user(db_session):
    result = auth_service.signup(db_session, f"gate-{uuid.uuid4().hex[:12]}@example.com", "correcthorse9!")
    db_session.flush()
    return result.user


def _settings(**overrides) -> AppSettings:
    base = dict(download_dir="/tmp/downloads", container_mode=ContainerMode.COMPATIBILITY, cookie_source=CookieSource.NONE)
    base.update(overrides)
    return AppSettings(**base)


class TestFreeVideoGating:
    def test_720p_allowed(self, db_session):
        user = _user(db_session)
        request = CreateDownloadRequest(url="https://youtube.com/watch?v=x", media_type="video", quality_key="720")
        reservation_id = download_gate_service.authorize_and_reserve(
            db_session, user, Plan.FREE, None, _settings(), request, "job-1"
        )
        assert reservation_id

    def test_1080p_blocked_for_free(self, db_session):
        user = _user(db_session)
        request = CreateDownloadRequest(url="https://youtube.com/watch?v=x", media_type="video", quality_key="1080")
        with pytest.raises(PlanLimitReachedError):
            download_gate_service.authorize_and_reserve(db_session, user, Plan.FREE, None, _settings(), request, "job-1")

    def test_best_quality_blocked_for_capped_plan(self, db_session):
        user = _user(db_session)
        request = CreateDownloadRequest(url="https://youtube.com/watch?v=x", media_type="video", quality_key="best")
        with pytest.raises(PlanLimitReachedError):
            download_gate_service.authorize_and_reserve(db_session, user, Plan.FREE, None, _settings(), request, "job-1")

    def test_clip_range_blocked_for_free(self, db_session):
        user = _user(db_session)
        request = CreateDownloadRequest(
            url="https://youtube.com/watch?v=x",
            media_type="video",
            quality_key="480",
            clip={"start": "00:00:01", "end": "00:00:05"},
        )
        with pytest.raises(FeatureNotIncludedError):
            download_gate_service.authorize_and_reserve(db_session, user, Plan.FREE, None, _settings(), request, "job-1")

    def test_playlist_full_blocked_for_free(self, db_session):
        user = _user(db_session)
        request = CreateDownloadRequest(
            url="https://youtube.com/playlist?list=x", media_type="video", quality_key="480", playlist_mode="full"
        )
        with pytest.raises(FeatureNotIncludedError):
            download_gate_service.authorize_and_reserve(db_session, user, Plan.FREE, None, _settings(), request, "job-1")

    def test_original_container_blocked_for_free(self, db_session):
        user = _user(db_session)
        request = CreateDownloadRequest(url="https://youtube.com/watch?v=x", media_type="video", quality_key="480")
        with pytest.raises(FeatureNotIncludedError):
            download_gate_service.authorize_and_reserve(
                db_session, user, Plan.FREE, None, _settings(container_mode=ContainerMode.ORIGINAL), request, "job-1"
            )

    def test_browser_cookies_blocked_for_free(self, db_session):
        user = _user(db_session)
        request = CreateDownloadRequest(url="https://youtube.com/watch?v=x", media_type="video", quality_key="480")
        with pytest.raises(FeatureNotIncludedError):
            download_gate_service.authorize_and_reserve(
                db_session, user, Plan.FREE, None, _settings(cookie_source=CookieSource.CHROME), request, "job-1"
            )

    def test_daily_limit_exhausted_after_five_downloads(self, db_session):
        user = _user(db_session)
        for i in range(5):
            request = CreateDownloadRequest(url="https://youtube.com/watch?v=x", media_type="video", quality_key="480")
            download_gate_service.authorize_and_reserve(db_session, user, Plan.FREE, None, _settings(), request, f"job-{i}")
        request = CreateDownloadRequest(url="https://youtube.com/watch?v=x", media_type="video", quality_key="480")
        with pytest.raises(DailyLimitReachedError):
            download_gate_service.authorize_and_reserve(db_session, user, Plan.FREE, None, _settings(), request, "job-overflow")


class TestProVideoGating:
    def test_4k_allowed_for_pro(self, db_session):
        user = _user(db_session)
        request = CreateDownloadRequest(url="https://youtube.com/watch?v=x", media_type="video", quality_key="2160")
        reservation_id = download_gate_service.authorize_and_reserve(
            db_session, user, Plan.PRO, None, _settings(), request, "job-1"
        )
        assert reservation_id

    def test_clip_range_allowed_for_pro(self, db_session):
        user = _user(db_session)
        request = CreateDownloadRequest(
            url="https://youtube.com/watch?v=x",
            media_type="video",
            quality_key="480",
            clip={"start": "00:00:01", "end": "00:00:05"},
        )
        reservation_id = download_gate_service.authorize_and_reserve(
            db_session, user, Plan.PRO, None, _settings(), request, "job-1"
        )
        assert reservation_id

    def test_4k_charges_three_credits(self, db_session):
        user = _user(db_session)
        request = CreateDownloadRequest(url="https://youtube.com/watch?v=x", media_type="video", quality_key="2160")
        download_gate_service.authorize_and_reserve(db_session, user, Plan.PRO, None, _settings(), request, "job-1")
        usage = usage_service.get_usage_out(db_session, user, Plan.PRO, None)
        assert usage.credits_used == 3

    def test_720p_charges_one_credit(self, db_session):
        user = _user(db_session)
        request = CreateDownloadRequest(url="https://youtube.com/watch?v=x", media_type="video", quality_key="720")
        download_gate_service.authorize_and_reserve(db_session, user, Plan.PRO, None, _settings(), request, "job-1")
        usage = usage_service.get_usage_out(db_session, user, Plan.PRO, None)
        assert usage.credits_used == 1


class TestAudioGating:
    def test_audio_always_one_credit_regardless_of_plan(self, db_session):
        user = _user(db_session)
        request = CreateDownloadRequest(url="https://youtube.com/watch?v=x", media_type="audio", quality_key="best")
        download_gate_service.authorize_and_reserve(db_session, user, Plan.FREE, None, _settings(), request, "job-1")
        usage = usage_service.get_usage_out(db_session, user, Plan.FREE, None)
        assert usage.daily_free_downloads_used == 1
