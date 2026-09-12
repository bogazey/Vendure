"""Portrait/vertical video (TikTok, Reels, Shorts) resolution-preset
regression coverage.

Background: a "720p" preset conventionally names a video's SHORT side, not
literally its `height` field. For landscape/square video those are the same
thing, but for portrait video the frame is taller than wide, so yt-dlp
reports `height` as the LONG side while the "720p"-style label refers to
width. Comparing raw `height` against a preset threshold - what this app did
before this fix - either rejects every real portrait format outright (its
height always exceeds the threshold) or silently matches a lower-quality
portrait stream whose height happens to fall under the threshold by
coincidence. See ytdlp_service._effective_quality_dimension.
"""
from __future__ import annotations

from typing import Optional

import yt_dlp

from app.models.enums import ContainerMode, FormatKind, MediaType
from app.models.schemas import FormatOption
from app.services import ytdlp_service
from app.services.ytdlp_service import build_format_selector

# The exact production formats from the investigation: a TikTok portrait
# video advertising "540p" and "720p" renditions.
PORTRAIT_540P = FormatOption(
    format_id="h264_540p", kind=FormatKind.VIDEO, ext="mp4", width=576, height=1024,
    vcodec="avc1.640028", has_video=True, has_audio=False,
)
PORTRAIT_720P = FormatOption(
    format_id="bytevc1_720p", kind=FormatKind.VIDEO, ext="mp4", width=720, height=1280,
    vcodec="hev1.1.6.L120.90", has_video=True, has_audio=False,
)
PORTRAIT_AUDIO = FormatOption(
    format_id="audio", kind=FormatKind.AUDIO, ext="m4a", acodec="mp4a.40.2", has_video=False, has_audio=True,
)
PORTRAIT_FORMATS = [PORTRAIT_540P, PORTRAIT_720P, PORTRAIT_AUDIO]

LANDSCAPE_720P = FormatOption(
    format_id="landscape_720p", kind=FormatKind.VIDEO, ext="mp4", width=1280, height=720,
    vcodec="avc1.640028", has_video=True, has_audio=False,
)
LANDSCAPE_AUDIO = FormatOption(
    format_id="audio", kind=FormatKind.AUDIO, ext="m4a", acodec="mp4a.40.2", has_video=False, has_audio=True,
)
LANDSCAPE_FORMATS = [LANDSCAPE_720P, LANDSCAPE_AUDIO]


def _availability(formats: list[FormatOption], key: str, container_mode=ContainerMode.ORIGINAL) -> Optional[bool]:
    video_presets, _audio_presets = ytdlp_service._build_presets(formats, container_mode)
    preset = next(p for p in video_presets if p.key == key)
    return preset.available


def _select_with_real_ytdlp(selector_spec: str, formats: list[dict]) -> list[dict]:
    """Runs the actual yt-dlp format-selection engine (not just a string
    match) against a mock `formats` list, to genuinely prove what a
    generated selector would pick - the same mechanism yt-dlp itself uses at
    download time."""
    ydl = yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True})
    selector_fn = ydl.build_format_selector(selector_spec)
    return ydl._select_formats(formats, selector_fn)


# Raw yt-dlp format dicts mirroring PORTRAIT_FORMATS/LANDSCAPE_FORMATS above,
# for driving the real selection engine (which only understands plain dicts,
# not our FormatOption schema). `aspect_ratio` is set explicitly here because
# in real yt-dlp runs it's computed automatically (width/height, rounded) in
# YoutubeDL.process_video_result before format selection ever happens
# (confirmed in yt_dlp/YoutubeDL.py) - these tests call the selector engine
# directly, bypassing that step, so it has to be supplied by hand to match
# what production would actually see.
PORTRAIT_RAW_FORMATS = [
    {"format_id": "h264_540p", "ext": "mp4", "width": 576, "height": 1024, "aspect_ratio": 0.56,
     "vcodec": "avc1.640028", "acodec": "none", "url": "https://example.test/h264_540p"},
    {"format_id": "bytevc1_720p", "ext": "mp4", "width": 720, "height": 1280, "aspect_ratio": 0.56,
     "vcodec": "hev1.1.6.L120.90", "acodec": "none", "url": "https://example.test/bytevc1_720p"},
    {"format_id": "audio", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 128,
     "url": "https://example.test/audio"},
]
LANDSCAPE_RAW_FORMATS = [
    {"format_id": "landscape_720p", "ext": "mp4", "width": 1280, "height": 720, "aspect_ratio": 1.78,
     "vcodec": "avc1.640028", "acodec": "none", "url": "https://example.test/landscape_720p"},
    {"format_id": "audio", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 128,
     "url": "https://example.test/audio"},
]


class TestEffectiveQualityDimension:
    def test_both_dimensions_uses_short_side(self):
        assert ytdlp_service._effective_quality_dimension(576, 1024) == 576
        assert ytdlp_service._effective_quality_dimension(1280, 720) == 720

    def test_only_height_known_falls_back_to_height(self):
        assert ytdlp_service._effective_quality_dimension(None, 720) == 720

    def test_only_width_known_falls_back_to_width(self):
        assert ytdlp_service._effective_quality_dimension(720, None) == 720

    def test_neither_known_is_none(self):
        assert ytdlp_service._effective_quality_dimension(None, None) is None

    def test_zero_or_negative_values_treated_as_unknown(self):
        # Defensive: yt-dlp should never report 0/negative dimensions, but a
        # falsy-but-not-None value must not be treated as a real dimension.
        assert ytdlp_service._effective_quality_dimension(0, 720) == 720
        assert ytdlp_service._effective_quality_dimension(720, 0) == 720


class TestPortraitPresetAvailability:
    """(A) Portrait preset availability: 576x1024 + 720x1280 formats."""

    def test_720p_is_available(self):
        assert _availability(PORTRAIT_FORMATS, "720") is True

    def test_480p_is_available(self):
        assert _availability(PORTRAIT_FORMATS, "480") is True

    def test_360p_is_available(self):
        assert _availability(PORTRAIT_FORMATS, "360") is True

    def test_1080p_is_not_available(self):
        assert _availability(PORTRAIT_FORMATS, "1080") is False

    def test_1440p_is_not_available(self):
        assert _availability(PORTRAIT_FORMATS, "1440") is False

    def test_2160p_is_not_available(self):
        assert _availability(PORTRAIT_FORMATS, "2160") is False


class TestLandscapeRegression:
    """(B) Landscape regression: existing 720p behavior is unchanged."""

    def test_720p_still_available_for_landscape_720p_format(self):
        assert _availability(LANDSCAPE_FORMATS, "720") is True

    def test_1080p_still_unavailable_when_no_higher_format_exists(self):
        assert _availability(LANDSCAPE_FORMATS, "1080") is False

    def test_selector_never_falls_through_to_portrait_branch(self):
        # A landscape format can never satisfy the portrait guard
        # (height>width), so selecting for it must resolve entirely via the
        # first (landscape) alternative.
        selector = build_format_selector(MediaType.VIDEO, "720", None, container_mode=ContainerMode.ORIGINAL)
        picked = _select_with_real_ytdlp(selector, LANDSCAPE_RAW_FORMATS)
        assert len(picked) == 1
        video_parts = [p for p in picked[0]["requested_formats"]] if "requested_formats" in picked[0] else [picked[0]]
        assert any(p.get("format_id") == "landscape_720p" for p in video_parts)


class TestPortraitSelectorExecution:
    """(C) Portrait 720p selector: prove it actually selects the 720x1280
    format, using yt-dlp's real selection engine rather than a string match."""

    def test_selects_720x1280_format_for_720p(self):
        selector = build_format_selector(MediaType.VIDEO, "720", None, container_mode=ContainerMode.ORIGINAL)
        picked = _select_with_real_ytdlp(selector, PORTRAIT_RAW_FORMATS)
        assert len(picked) == 1
        parts = picked[0].get("requested_formats", [picked[0]])
        video_ids = {p.get("format_id") for p in parts if p.get("vcodec") not in (None, "none")}
        assert video_ids == {"bytevc1_720p"}

    def test_selector_string_contains_orientation_guards(self):
        selector = build_format_selector(MediaType.VIDEO, "720", None, container_mode=ContainerMode.ORIGINAL)
        assert "[width<=720][aspect_ratio<1]" in selector
        assert "[height<=720][aspect_ratio>=1]" in selector


class TestPortrait1080DoesNotSilentlyDowngrade:
    """(D) Portrait 1080p: given max format 720x1280, 1080p must not be
    advertised as available, and if requested anyway must not silently
    resolve to the lower-quality 576x1024 stream."""

    def test_1080p_not_advertised_as_available(self):
        assert _availability(PORTRAIT_FORMATS, "1080") is False

    def test_1080p_selector_does_not_resolve_to_540p_stream(self):
        selector = build_format_selector(MediaType.VIDEO, "1080", None, container_mode=ContainerMode.ORIGINAL)
        picked = _select_with_real_ytdlp(selector, PORTRAIT_RAW_FORMATS)
        assert len(picked) == 1
        parts = picked[0].get("requested_formats", [picked[0]])
        video_ids = {p.get("format_id") for p in parts if p.get("vcodec") not in (None, "none")}
        # It's fine (and correct - "at most 1080p") for this to resolve to
        # the best available portrait stream under the threshold; it must
        # never silently be the *wrong*, lower-quality 540p stream.
        assert "h264_540p" not in video_ids
        assert video_ids == {"bytevc1_720p"}


class TestMissingWidthCompatibility:
    """(E) Existing/mocked FormatOption objects that only ever set `height`
    (as elsewhere in this test suite, and any pre-fix caller) must keep
    working exactly as before - width defaults to None."""

    def test_format_option_without_width_still_constructs(self):
        f = FormatOption(format_id="v", kind=FormatKind.VIDEO, ext="mp4", height=720, has_video=True)
        assert f.width is None
        assert f.height == 720

    def test_quality_dimension_falls_back_to_height_alone(self):
        f = FormatOption(format_id="v", kind=FormatKind.VIDEO, ext="mp4", height=720, has_video=True)
        assert ytdlp_service._quality_dimension(f) == 720

    def test_presets_for_width_less_formats_behave_as_before(self):
        formats = [
            FormatOption(format_id="v", kind=FormatKind.VIDEO, ext="mp4", height=720, has_video=True,
                         vcodec="avc1.640028"),
            FormatOption(format_id="a", kind=FormatKind.AUDIO, ext="m4a", has_audio=True, acodec="mp4a.40.2"),
        ]
        assert _availability(formats, "720") is True
        assert _availability(formats, "1080") is False


class TestAdvancedFormatIdUnchanged:
    """(F) Advanced Formats (explicit format_id) selection must be completely
    unaffected by the orientation-safety changes - it never goes through
    the height/width preset-filtering logic at all."""

    def test_portrait_style_format_id_passed_through_as_is(self):
        selector = build_format_selector(
            MediaType.VIDEO, "best", "bytevc1_720p", format_has_video=True, format_has_audio=False,
        )
        assert selector == "bytevc1_720p+bestaudio/bytevc1_720p/best"

    def test_format_id_selection_ignores_quality_key_and_container_mode(self):
        for quality_key in ("best", "720", "1080"):
            for mode in (ContainerMode.COMPATIBILITY, ContainerMode.ORIGINAL):
                selector = build_format_selector(
                    MediaType.VIDEO, quality_key, "bytevc1_720p",
                    format_has_video=True, format_has_audio=False, container_mode=mode,
                )
                assert selector == "bytevc1_720p+bestaudio/bytevc1_720p/best"
