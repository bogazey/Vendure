""""Best Available" plan-aware resolution: it now resolves automatically to
min(source's real best, the account's plan ceiling) instead of either being
rejected outright for a capped plan (the old behavior - see
test_commercial_download_gate.py's now-renamed
test_best_quality_allowed_for_capped_plan_and_resolves_to_plan_cap) or
silently ignoring the plan ceiling altogether.

Covers the full scenario matrix from the task, plus the anti-bypass proof
(the backend enforces the cap from the account's own plan, never from
anything the client sends) and the portrait/orientation-safety regression
guard from the earlier portrait-video fix, which this change must not
disturb - see test_portrait_format_selection.py for that fix's own coverage.
"""
from __future__ import annotations

import uuid

import pytest
import yt_dlp

from app.models.commercial_enums import Plan
from app.models.enums import ContainerMode, MediaType
from app.models.schemas import AppSettings, CreateDownloadRequest
from app.services import plan_policy
from app.services.auth_service import auth_service
from app.services.download_gate_service import download_gate_service
from app.services.ytdlp_service import build_download_opts, build_format_selector


def _user(db_session):
    result = auth_service.signup(db_session, f"best-available-{uuid.uuid4().hex[:12]}@example.com", "correcthorse9!")
    db_session.flush()
    return result.user


def _select_with_real_ytdlp(selector_spec: str, formats: list[dict]) -> list[dict]:
    """Runs the actual yt-dlp format-selection engine (not just a string
    match) against a mock `formats` list - same technique used in
    test_portrait_format_selection.py, so these tests prove real selection
    behavior rather than just asserting on the selector's string shape."""
    ydl = yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True})
    selector_fn = ydl.build_format_selector(selector_spec)
    return ydl._select_formats(formats, selector_fn)


def _picked_video_format_ids(picked: list[dict]) -> set[str]:
    assert len(picked) == 1
    parts = picked[0].get("requested_formats", [picked[0]])
    return {p.get("format_id") for p in parts if p.get("vcodec") not in (None, "none")}


# A source offering everything from 360p up through true 4K, landscape.
LANDSCAPE_LADDER_WITH_4K = [
    {"format_id": "360p", "ext": "mp4", "width": 640, "height": 360, "aspect_ratio": 1.78,
     "vcodec": "avc1.640028", "acodec": "none", "url": "https://example.test/360p"},
    {"format_id": "720p", "ext": "mp4", "width": 1280, "height": 720, "aspect_ratio": 1.78,
     "vcodec": "avc1.640028", "acodec": "none", "url": "https://example.test/720p"},
    {"format_id": "1080p", "ext": "mp4", "width": 1920, "height": 1080, "aspect_ratio": 1.78,
     "vcodec": "avc1.640028", "acodec": "none", "url": "https://example.test/1080p"},
    {"format_id": "2160p", "ext": "mp4", "width": 3840, "height": 2160, "aspect_ratio": 1.78,
     "vcodec": "avc1.640028", "acodec": "none", "url": "https://example.test/2160p"},
    {"format_id": "audio", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 128,
     "url": "https://example.test/audio"},
]

# A source that never has anything above 576p (e.g. an old/low-quality upload).
LANDSCAPE_SOURCE_MAX_576P = [
    {"format_id": "360p", "ext": "mp4", "width": 640, "height": 360, "aspect_ratio": 1.78,
     "vcodec": "avc1.640028", "acodec": "none", "url": "https://example.test/360p"},
    {"format_id": "576p", "ext": "mp4", "width": 1024, "height": 576, "aspect_ratio": 1.78,
     "vcodec": "avc1.640028", "acodec": "none", "url": "https://example.test/576p"},
    {"format_id": "audio", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 128,
     "url": "https://example.test/audio"},
]

# A source that never has anything above 720p.
LANDSCAPE_SOURCE_MAX_720P = [
    {"format_id": "360p", "ext": "mp4", "width": 640, "height": 360, "aspect_ratio": 1.78,
     "vcodec": "avc1.640028", "acodec": "none", "url": "https://example.test/360p"},
    {"format_id": "720p", "ext": "mp4", "width": 1280, "height": 720, "aspect_ratio": 1.78,
     "vcodec": "avc1.640028", "acodec": "none", "url": "https://example.test/720p"},
    {"format_id": "audio", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 128,
     "url": "https://example.test/audio"},
]

# The exact production portrait formats from the earlier portrait-video fix.
PORTRAIT_540P_AND_720P = [
    {"format_id": "h264_540p", "ext": "mp4", "width": 576, "height": 1024, "aspect_ratio": 0.56,
     "vcodec": "avc1.640028", "acodec": "none", "url": "https://example.test/h264_540p"},
    {"format_id": "bytevc1_720p", "ext": "mp4", "width": 720, "height": 1280, "aspect_ratio": 0.56,
     "vcodec": "hev1.1.6.L120.90", "acodec": "none", "url": "https://example.test/bytevc1_720p"},
    {"format_id": "audio", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 128,
     "url": "https://example.test/audio"},
]


class TestPlanCapIsReadFromExistingPolicy:
    """The cap "Best Available" resolves to must come from the existing
    plan_policy configuration, never a number hardcoded in the
    resolution/selector logic itself."""

    def test_free_plan_cap_matches_plan_policy_config(self):
        assert plan_policy.resolve_best_available_cap(Plan.FREE) == plan_policy.get_policy(Plan.FREE).max_resolution_height
        assert plan_policy.resolve_best_available_cap(Plan.FREE) == 720

    def test_pro_and_creator_use_whatever_plan_policy_currently_says(self):
        # Real Pro/Creator are uncapped (max_resolution_height=None) in the
        # existing plan_policy config today - this proves the resolution
        # logic simply reads that field rather than special-casing any plan
        # name, so if Pro's cap were later changed to e.g. 1080 in
        # plan_policy.py, this mechanism would honor it with no code change
        # here.
        assert plan_policy.resolve_best_available_cap(Plan.PRO) == plan_policy.get_policy(Plan.PRO).max_resolution_height
        assert plan_policy.resolve_best_available_cap(Plan.CREATOR) == plan_policy.get_policy(Plan.CREATOR).max_resolution_height

    def test_changing_the_policy_config_changes_the_resolved_cap_with_no_other_code_change(self, monkeypatch):
        """Proves resolve_best_available_cap has no plan-specific branching
        of its own - it is a pure function of plan_policy.PLAN_POLICIES."""
        from app.services.plan_policy import PlanPolicy

        capped_pro = plan_policy.PLAN_POLICIES[Plan.PRO]
        monkeypatch.setitem(
            plan_policy.PLAN_POLICIES, Plan.PRO,
            PlanPolicy(**{**capped_pro.__dict__, "max_resolution_height": 1080}),
        )
        assert plan_policy.resolve_best_available_cap(Plan.PRO) == 1080


class TestBestAvailableResolvesAgainstSourceAndCap:
    """"Best Available" = min(source's real best, plan cap) - proven by
    actually running yt-dlp's selection engine, not just inspecting the
    generated selector string."""

    def test_free_best_available_with_4k_source_resolves_to_720p(self):
        selector = build_format_selector(MediaType.VIDEO, "best", None, container_mode=ContainerMode.ORIGINAL, max_height=720)
        picked = _select_with_real_ytdlp(selector, LANDSCAPE_LADDER_WITH_4K)
        assert _picked_video_format_ids(picked) == {"720p"}

    def test_free_best_available_with_source_max_576p_resolves_to_576p(self):
        # The plan cap (720) is above what the source offers - Best
        # Available must still fall back to the source's own real best
        # (576p), never fail and never "wait" for a higher tier.
        selector = build_format_selector(MediaType.VIDEO, "best", None, container_mode=ContainerMode.ORIGINAL, max_height=720)
        picked = _select_with_real_ytdlp(selector, LANDSCAPE_SOURCE_MAX_576P)
        assert _picked_video_format_ids(picked) == {"576p"}

    def test_1080_capped_plan_with_4k_source_resolves_to_1080p(self):
        # Stands in for the task's "Pro -> up to 1080p" example using an
        # explicit 1080 cap, since the real Pro policy in this codebase is
        # currently uncapped (max_resolution_height=None) - see
        # TestRealUncappedPlansAreNotArtificiallyLimited below for that.
        # The mechanism itself (build_format_selector's max_height) is
        # identical regardless of which plan the cap came from.
        selector = build_format_selector(MediaType.VIDEO, "best", None, container_mode=ContainerMode.ORIGINAL, max_height=1080)
        picked = _select_with_real_ytdlp(selector, LANDSCAPE_LADDER_WITH_4K)
        assert _picked_video_format_ids(picked) == {"1080p"}

    def test_1080_capped_plan_with_source_max_720p_resolves_to_720p(self):
        selector = build_format_selector(MediaType.VIDEO, "best", None, container_mode=ContainerMode.ORIGINAL, max_height=1080)
        picked = _select_with_real_ytdlp(selector, LANDSCAPE_SOURCE_MAX_720P)
        assert _picked_video_format_ids(picked) == {"720p"}

    def test_creator_style_cap_behaves_identically_to_any_other_cap(self):
        """"Creator uses its configured plan maximum correctly": there is no
        Creator-specific branch anywhere in build_format_selector - whatever
        numeric cap the plan resolves to (via plan_policy, see
        TestPlanCapIsReadFromExistingPolicy) is treated exactly the same as
        any other max_height value. This test stands in for "Creator's
        maximum" with an arbitrary distinguishing number (1440) precisely to
        prove that genericity - there is nothing to hardcode."""
        selector = build_format_selector(MediaType.VIDEO, "best", None, container_mode=ContainerMode.ORIGINAL, max_height=1440)
        picked = _select_with_real_ytdlp(selector, LANDSCAPE_LADDER_WITH_4K)
        assert _picked_video_format_ids(picked) == {"1080p"}  # highest available at or under 1440p


class TestRealUncappedPlansAreNotArtificiallyLimited:
    """The actual, current Pro/Creator policies (max_resolution_height=None)
    must remain fully uncapped - "Best Available" for them is still the true
    best the source offers, exactly as before this change."""

    def test_real_pro_plan_best_available_is_uncapped(self):
        cap = plan_policy.resolve_best_available_cap(Plan.PRO)
        assert cap is None
        selector = build_format_selector(MediaType.VIDEO, "best", None, container_mode=ContainerMode.ORIGINAL, max_height=cap)
        picked = _select_with_real_ytdlp(selector, LANDSCAPE_LADDER_WITH_4K)
        assert _picked_video_format_ids(picked) == {"2160p"}

    def test_real_creator_plan_best_available_is_uncapped(self):
        cap = plan_policy.resolve_best_available_cap(Plan.CREATOR)
        assert cap is None
        selector = build_format_selector(MediaType.VIDEO, "best", None, container_mode=ContainerMode.ORIGINAL, max_height=cap)
        picked = _select_with_real_ytdlp(selector, LANDSCAPE_LADDER_WITH_4K)
        assert _picked_video_format_ids(picked) == {"2160p"}


class TestPortraitBestAvailableRemainsOrientationSafe:
    """The portrait-video fix's orientation-safe selector construction must
    survive plan-aware "Best Available" completely intact - a capped "best"
    request simply becomes the same call as an equivalent explicit numeric
    pick (see build_format_selector), so it inherits the exact same
    height<=X/width<=X + aspect_ratio guards, not a raw height-only filter."""

    def test_free_best_available_on_portrait_source_selects_720x1280(self):
        selector = build_format_selector(MediaType.VIDEO, "best", None, container_mode=ContainerMode.ORIGINAL, max_height=720)
        picked = _select_with_real_ytdlp(selector, PORTRAIT_540P_AND_720P)
        assert _picked_video_format_ids(picked) == {"bytevc1_720p"}

    def test_selector_never_regresses_to_raw_height_only_filtering(self):
        selector = build_format_selector(MediaType.VIDEO, "best", None, container_mode=ContainerMode.ORIGINAL, max_height=720)
        assert "aspect_ratio" in selector
        assert "width<=720" in selector


class TestManualQualitySelectionUnaffectedByCapResolution:
    """Manual numeric picks keep their existing, separate enforcement path -
    "Best Available" resolution never changes what an explicit pick does."""

    def test_manual_free_1080p_still_blocked(self, db_session):
        from app.utils.exceptions import PlanLimitReachedError

        user = _user(db_session)
        request = CreateDownloadRequest(url="https://youtube.com/watch?v=x", media_type="video", quality_key="1080")
        with pytest.raises(PlanLimitReachedError):
            download_gate_service.authorize_and_reserve(db_session, user, Plan.FREE, None, request, "job-1")

    def test_manual_free_720p_still_allowed(self, db_session):
        user = _user(db_session)
        request = CreateDownloadRequest(url="https://youtube.com/watch?v=x", media_type="video", quality_key="720")
        reservation_id, max_resolution_height = download_gate_service.authorize_and_reserve(
            db_session, user, Plan.FREE, None, request, "job-1"
        )
        assert reservation_id
        assert max_resolution_height == 720


class TestDirectApiRequestCannotBypassTheCap:
    """The backend must resolve the cap itself from the account's plan -
    never trust anything the client sends about its own entitlement. This
    drives the *actual* format selector (what yt-dlp will really download),
    not just the entitlement check, so a client cannot submit a bare "best"
    quality_key and expect an uncapped download just because the request
    itself carries no cap information."""

    def _settings(self) -> AppSettings:
        return AppSettings(download_dir="/tmp/lmd-test-downloads")

    def _noop_hook(self, _d: dict) -> None:
        pass

    def test_free_best_available_request_produces_a_capped_selector_end_to_end(self, db_session):
        user = _user(db_session)
        request = CreateDownloadRequest(url="https://youtube.com/watch?v=x", media_type="video", quality_key="best")

        # Exactly what routes_downloads._gate_and_create does: gate first,
        # then build the real download opts from whatever the gate resolved
        # - never from the client-supplied request alone.
        _reservation_id, max_resolution_height = download_gate_service.authorize_and_reserve(
            db_session, user, Plan.FREE, None, request, "job-1"
        )
        opts = build_download_opts(
            request, self._settings(), "%(title)s.%(ext)s", self._noop_hook, self._noop_hook,
            max_resolution_height=max_resolution_height,
        )

        assert max_resolution_height == 720
        selector = opts["format"]
        assert "height<=720" in selector
        assert "width<=720" in selector
        # The uncapped "true best" selector must never appear for a Free
        # request, even though the client only ever said quality_key="best".
        assert "bestvideo*" not in selector

    def test_pro_best_available_request_remains_the_true_best_selector(self, db_session):
        from app.services.auth_service import auth_service as _auth

        result = _auth.signup(db_session, f"pro-best-{uuid.uuid4().hex[:10]}@example.com", "correcthorse9!")
        db_session.flush()
        user = result.user
        request = CreateDownloadRequest(url="https://youtube.com/watch?v=x", media_type="video", quality_key="best")

        _reservation_id, max_resolution_height = download_gate_service.authorize_and_reserve(
            db_session, user, Plan.PRO, None, request, "job-1"
        )
        opts = build_download_opts(
            request, self._settings(), "%(title)s.%(ext)s", self._noop_hook, self._noop_hook,
            max_resolution_height=max_resolution_height,
        )

        assert max_resolution_height is None
        assert "bestvideo*" in opts["format"]


class TestAdvancedFormatSelectionUnaffectedByCap:
    """Explicit Advanced Format (format_id) selections must be completely
    unaffected by max_height - they never pass through the "best"/height
    resolution branch at all."""

    def test_format_id_selection_ignores_max_height(self):
        capped = build_format_selector(
            MediaType.VIDEO, "best", "137", format_has_video=True, format_has_audio=False, max_height=720,
        )
        uncapped = build_format_selector(
            MediaType.VIDEO, "best", "137", format_has_video=True, format_has_audio=False, max_height=None,
        )
        assert capped == uncapped == "137+bestaudio/137/best"
