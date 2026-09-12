"""DownloadGateService: the single choke point every download request must
pass through - entitlement checks, then an atomic credit reservation.

Gating reads container_mode/cookie_source from this user's OWN row in
user_download_preferences (never a global setting) - see
test_commercial_user_preferences.py for the dedicated isolation proofs."""
import uuid

import pytest

from app.models.commercial_enums import Plan
from app.models.enums import ContainerMode, CookieSource
from app.models.schemas import CreateDownloadRequest
from app.services.auth_service import auth_service
from app.services.download_gate_service import download_gate_service
from app.services.usage_service import usage_service
from app.services.user_preferences_service import user_preferences_service
from app.utils.exceptions import DailyLimitReachedError, FeatureNotIncludedError, PlanLimitReachedError


def _user(db_session):
    result = auth_service.signup(db_session, f"gate-{uuid.uuid4().hex[:12]}@example.com", "correcthorse9!")
    db_session.flush()
    return result.user


def _set_prefs(db_session, user, **overrides) -> None:
    patch = {}
    if "container_mode" in overrides:
        patch["container_mode"] = overrides["container_mode"]
    if "cookie_source" in overrides:
        patch["cookie_source"] = overrides["cookie_source"]
    user_preferences_service.update(db_session, user.id, patch)
    db_session.flush()


class TestFreeVideoGating:
    def test_720p_allowed(self, db_session):
        user = _user(db_session)
        request = CreateDownloadRequest(url="https://youtube.com/watch?v=x", media_type="video", quality_key="720")
        reservation_id, max_resolution_height = download_gate_service.authorize_and_reserve(
            db_session, user, Plan.FREE, None, request, "job-1"
        )
        assert reservation_id
        assert max_resolution_height == 720

    def test_1080p_blocked_for_free(self, db_session):
        user = _user(db_session)
        request = CreateDownloadRequest(url="https://youtube.com/watch?v=x", media_type="video", quality_key="1080")
        with pytest.raises(PlanLimitReachedError):
            download_gate_service.authorize_and_reserve(db_session, user, Plan.FREE, None, request, "job-1")

    def test_best_quality_allowed_for_capped_plan_and_resolves_to_plan_cap(self, db_session):
        # "Best Available" used to be rejected outright for a capped plan,
        # forcing the user to manually pick a specific resolution - it now
        # resolves automatically to the plan's own ceiling instead (see
        # test_best_available_plan_aware.py for the full scenario matrix).
        user = _user(db_session)
        request = CreateDownloadRequest(url="https://youtube.com/watch?v=x", media_type="video", quality_key="best")
        reservation_id, max_resolution_height = download_gate_service.authorize_and_reserve(
            db_session, user, Plan.FREE, None, request, "job-1"
        )
        assert reservation_id
        assert max_resolution_height == 720

    def test_clip_range_blocked_for_free(self, db_session):
        user = _user(db_session)
        request = CreateDownloadRequest(
            url="https://youtube.com/watch?v=x",
            media_type="video",
            quality_key="480",
            clip={"start": "00:00:01", "end": "00:00:05"},
        )
        with pytest.raises(FeatureNotIncludedError):
            download_gate_service.authorize_and_reserve(db_session, user, Plan.FREE, None, request, "job-1")

    def test_playlist_full_blocked_for_free(self, db_session):
        user = _user(db_session)
        request = CreateDownloadRequest(
            url="https://youtube.com/playlist?list=x", media_type="video", quality_key="480", playlist_mode="full"
        )
        with pytest.raises(FeatureNotIncludedError):
            download_gate_service.authorize_and_reserve(db_session, user, Plan.FREE, None, request, "job-1")

    def test_original_container_blocked_for_free(self, db_session):
        user = _user(db_session)
        _set_prefs(db_session, user, container_mode=ContainerMode.ORIGINAL)
        request = CreateDownloadRequest(url="https://youtube.com/watch?v=x", media_type="video", quality_key="480")
        with pytest.raises(FeatureNotIncludedError):
            download_gate_service.authorize_and_reserve(db_session, user, Plan.FREE, None, request, "job-1")

    def test_browser_cookies_blocked_for_free(self, db_session):
        user = _user(db_session)
        _set_prefs(db_session, user, cookie_source=CookieSource.CHROME)
        request = CreateDownloadRequest(url="https://youtube.com/watch?v=x", media_type="video", quality_key="480")
        with pytest.raises(FeatureNotIncludedError):
            download_gate_service.authorize_and_reserve(db_session, user, Plan.FREE, None, request, "job-1")

    def test_daily_limit_exhausted_after_five_downloads(self, db_session):
        user = _user(db_session)
        for i in range(5):
            request = CreateDownloadRequest(url="https://youtube.com/watch?v=x", media_type="video", quality_key="480")
            download_gate_service.authorize_and_reserve(db_session, user, Plan.FREE, None, request, f"job-{i}")
        request = CreateDownloadRequest(url="https://youtube.com/watch?v=x", media_type="video", quality_key="480")
        with pytest.raises(DailyLimitReachedError):
            download_gate_service.authorize_and_reserve(db_session, user, Plan.FREE, None, request, "job-overflow")


class TestProVideoGating:
    def test_4k_allowed_for_pro(self, db_session):
        user = _user(db_session)
        request = CreateDownloadRequest(url="https://youtube.com/watch?v=x", media_type="video", quality_key="2160")
        reservation_id, _ = download_gate_service.authorize_and_reserve(
            db_session, user, Plan.PRO, None, request, "job-1"
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
        reservation_id, _ = download_gate_service.authorize_and_reserve(
            db_session, user, Plan.PRO, None, request, "job-1"
        )
        assert reservation_id

    def test_original_container_allowed_for_pro(self, db_session):
        user = _user(db_session)
        _set_prefs(db_session, user, container_mode=ContainerMode.ORIGINAL)
        request = CreateDownloadRequest(url="https://youtube.com/watch?v=x", media_type="video", quality_key="480")
        reservation_id, _ = download_gate_service.authorize_and_reserve(
            db_session, user, Plan.PRO, None, request, "job-1"
        )
        assert reservation_id

    def test_4k_charges_three_credits(self, db_session):
        user = _user(db_session)
        request = CreateDownloadRequest(url="https://youtube.com/watch?v=x", media_type="video", quality_key="2160")
        download_gate_service.authorize_and_reserve(db_session, user, Plan.PRO, None, request, "job-1")
        usage = usage_service.get_usage_out(db_session, user, Plan.PRO, None)
        assert usage.credits_used == 3

    def test_720p_charges_one_credit(self, db_session):
        user = _user(db_session)
        request = CreateDownloadRequest(url="https://youtube.com/watch?v=x", media_type="video", quality_key="720")
        download_gate_service.authorize_and_reserve(db_session, user, Plan.PRO, None, request, "job-1")
        usage = usage_service.get_usage_out(db_session, user, Plan.PRO, None)
        assert usage.credits_used == 1


class TestAudioGating:
    def test_audio_always_one_credit_regardless_of_plan(self, db_session):
        user = _user(db_session)
        request = CreateDownloadRequest(url="https://youtube.com/watch?v=x", media_type="audio", quality_key="best")
        download_gate_service.authorize_and_reserve(db_session, user, Plan.FREE, None, request, "job-1")
        usage = usage_service.get_usage_out(db_session, user, Plan.FREE, None)
        assert usage.daily_free_downloads_used == 1


class TestImageGating:
    """Images are a new media type (see MediaType.IMAGE) - this locks in
    the least-surprising rule: same one-credit rate as audio/<=1080p video,
    no video-only checks (resolution/4k/format/clip/original-container)."""

    def test_image_allowed_on_free_plan(self, db_session):
        user = _user(db_session)
        request = CreateDownloadRequest(url="https://www.instagram.com/p/ABC123/", media_type="image")
        reservation_id, _ = download_gate_service.authorize_and_reserve(db_session, user, Plan.FREE, None, request, "job-1")
        assert reservation_id
        usage = usage_service.get_usage_out(db_session, user, Plan.FREE, None)
        assert usage.daily_free_downloads_used == 1

    def test_image_charges_exactly_one_credit_on_a_paid_plan(self, db_session):
        user = _user(db_session)
        request = CreateDownloadRequest(url="https://www.instagram.com/p/ABC123/", media_type="image")
        download_gate_service.authorize_and_reserve(db_session, user, Plan.PRO, None, request, "job-1")
        usage = usage_service.get_usage_out(db_session, user, Plan.PRO, None)
        assert usage.credits_used == 1

    def test_image_download_is_never_gated_by_video_only_entitlements(self, db_session):
        # Free's max_resolution_height/can_use_4k restrictions must not
        # leak onto images - there is no "resolution" concept for a photo.
        user = _user(db_session)
        request = CreateDownloadRequest(url="https://www.instagram.com/p/ABC123/", media_type="image")
        reservation_id, _ = download_gate_service.authorize_and_reserve(db_session, user, Plan.FREE, None, request, "job-1")
        assert reservation_id
