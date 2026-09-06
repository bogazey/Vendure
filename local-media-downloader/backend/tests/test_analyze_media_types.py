"""analyze() coverage for image/carousel/mixed media and normalized errors.

yt_dlp.YoutubeDL is replaced with a deterministic fake returning canned
extractor-shaped dicts - no network access, no live Instagram dependency.
"""
from __future__ import annotations

import pytest
from yt_dlp.utils import DownloadError

from app.models.enums import MediaType, Platform
from app.models.schemas import AppSettings
from app.services import ytdlp_service
from app.utils.exceptions import NoDownloadableMediaError, PrivateOrLoginRequiredError, UnavailableMediaError

INSTAGRAM_URL = "https://www.instagram.com/p/ABC123/"


class FakeYoutubeDL:
    info_to_return: dict | None = None
    raise_exc: Exception | None = None
    last_opts: dict | None = None

    def __init__(self, opts):
        self.opts = opts
        FakeYoutubeDL.last_opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def extract_info(self, url, download=False):
        if FakeYoutubeDL.raise_exc is not None:
            raise FakeYoutubeDL.raise_exc
        return FakeYoutubeDL.info_to_return


@pytest.fixture(autouse=True)
def _patch_yt_dlp(monkeypatch, tmp_path):
    monkeypatch.setattr(ytdlp_service, "yt_dlp", type("M", (), {"YoutubeDL": FakeYoutubeDL}))
    monkeypatch.setattr(ytdlp_service, "check_ffmpeg", lambda: (False, None))
    FakeYoutubeDL.info_to_return = None
    FakeYoutubeDL.raise_exc = None
    yield


def _settings(tmp_path) -> AppSettings:
    return AppSettings(download_dir=str(tmp_path))


def _image_entry(image_id: str, url: str, width: int = 1080, height: int = 1080, title: str | None = None) -> dict:
    return {
        "id": image_id,
        "title": title,
        "thumbnail": url,
        "thumbnails": [
            {"url": url.replace(".jpg", "_small.jpg"), "width": 150, "height": 150},
            {"url": url, "width": width, "height": height},
        ],
        "formats": [],
    }


def _video_entry(video_id: str, title: str | None = None, duration: float = 12.0) -> dict:
    return {
        "id": video_id,
        "title": title,
        "duration": duration,
        "thumbnail": f"https://example.com/{video_id}_thumb.jpg",
        "formats": [
            {"format_id": "137", "vcodec": "avc1.64001f", "acodec": "none", "height": 720, "ext": "mp4", "format_note": "720p"},
            {"format_id": "140", "vcodec": "none", "acodec": "mp4a.40.2", "ext": "m4a"},
        ],
    }


class TestSingleImagePost:
    def test_analyze_succeeds_for_a_single_image_post(self, tmp_path):
        FakeYoutubeDL.info_to_return = {
            **_image_entry("img1", "https://cdn.example.com/photo.jpg"),
            "title": "A nice photo",
            "uploader": "someone",
            "description": "a caption",
        }
        result = ytdlp_service.analyze(INSTAGRAM_URL, _settings(tmp_path))

        assert result.media_type == MediaType.IMAGE
        assert result.platform == Platform.INSTAGRAM
        assert result.image_url == "https://cdn.example.com/photo.jpg"
        assert result.image_width == 1080
        assert result.image_height == 1080
        assert result.image_ext == "jpg"
        assert result.title == "A nice photo"
        assert result.video_presets == []
        assert result.audio_presets == []
        assert not result.is_playlist

    def test_picks_the_largest_thumbnail_regardless_of_list_order(self, tmp_path):
        FakeYoutubeDL.info_to_return = {
            "id": "img2",
            "title": "photo",
            "thumbnail": None,
            "thumbnails": [
                {"url": "https://example.com/big.jpg", "width": 1080, "height": 1080},
                {"url": "https://example.com/small.jpg", "width": 150, "height": 150},
            ],
            "formats": [],
        }
        result = ytdlp_service.analyze(INSTAGRAM_URL, _settings(tmp_path))
        assert result.image_url == "https://example.com/big.jpg"


class TestExistingVideoBehaviorUnaffected:
    def test_video_post_still_analyzes_as_video(self, tmp_path):
        FakeYoutubeDL.info_to_return = _video_entry("vid1", title="A Reel")
        result = ytdlp_service.analyze("https://www.instagram.com/reel/XYZ/", _settings(tmp_path))

        assert result.media_type == MediaType.VIDEO
        assert result.image_url is None
        assert len(result.advanced_formats) == 2
        assert any(p.key == "best" and p.available for p in result.video_presets)


class TestCarousels:
    def test_image_plus_image_carousel(self, tmp_path):
        FakeYoutubeDL.info_to_return = {
            "_type": "playlist",
            "id": "carousel1",
            "title": "Post by someone",
            "entries": [
                _image_entry("img1", "https://example.com/1.jpg"),
                _image_entry("img2", "https://example.com/2.jpg"),
            ],
        }
        result = ytdlp_service.analyze(INSTAGRAM_URL, _settings(tmp_path))

        assert result.is_playlist is True
        assert result.playlist_count == 2
        assert [item.media_type for item in result.media_items] == [MediaType.IMAGE, MediaType.IMAGE]
        assert [item.index for item in result.media_items] == [1, 2]
        assert result.media_items[0].image_url == "https://example.com/1.jpg"
        assert result.media_items[1].image_url == "https://example.com/2.jpg"

    def test_video_plus_video_carousel(self, tmp_path):
        FakeYoutubeDL.info_to_return = {
            "_type": "playlist",
            "id": "carousel2",
            "title": "Post by someone",
            "entries": [_video_entry("v1"), _video_entry("v2")],
        }
        result = ytdlp_service.analyze(INSTAGRAM_URL, _settings(tmp_path))

        assert result.playlist_count == 2
        assert all(item.media_type == MediaType.VIDEO for item in result.media_items)
        assert result.media_items[0].duration == 12.0

    def test_mixed_image_and_video_carousel(self, tmp_path):
        FakeYoutubeDL.info_to_return = {
            "_type": "playlist",
            "id": "carousel3",
            "title": "Post by someone",
            "entries": [
                _image_entry("img1", "https://example.com/1.jpg"),
                _video_entry("v1"),
                _image_entry("img2", "https://example.com/2.jpg"),
            ],
        }
        result = ytdlp_service.analyze(INSTAGRAM_URL, _settings(tmp_path))

        types = [item.media_type for item in result.media_items]
        assert types == [MediaType.IMAGE, MediaType.VIDEO, MediaType.IMAGE]
        # First entry decides the top-level media_type shown in the preview card.
        assert result.media_type == MediaType.IMAGE
        assert result.media_items[1].image_url is None
        assert result.media_items[1].duration == 12.0

    def test_carousel_entries_with_no_media_are_skipped_but_indices_preserved(self, tmp_path):
        FakeYoutubeDL.info_to_return = {
            "_type": "playlist",
            "id": "carousel4",
            "title": "Post by someone",
            "entries": [
                _image_entry("img1", "https://example.com/1.jpg"),
                {"id": "empty", "title": "nothing", "formats": [], "thumbnails": [], "thumbnail": None},
                _image_entry("img2", "https://example.com/2.jpg"),
            ],
        }
        result = ytdlp_service.analyze(INSTAGRAM_URL, _settings(tmp_path))
        assert [item.index for item in result.media_items] == [1, 3]


class TestNormalizedErrors:
    def test_post_with_no_downloadable_media_raises_friendly_error(self, tmp_path):
        FakeYoutubeDL.info_to_return = {"id": "empty1", "title": "Nothing here", "formats": [], "thumbnails": [], "thumbnail": None}
        with pytest.raises(NoDownloadableMediaError) as exc_info:
            ytdlp_service.analyze(INSTAGRAM_URL, _settings(tmp_path))
        assert exc_info.value.message == "This post does not contain downloadable media."

    def test_empty_carousel_raises_friendly_error(self, tmp_path):
        FakeYoutubeDL.info_to_return = {"_type": "playlist", "id": "carousel5", "title": "Post", "entries": []}
        with pytest.raises(NoDownloadableMediaError):
            ytdlp_service.analyze(INSTAGRAM_URL, _settings(tmp_path))

    def test_raw_yt_dlp_no_video_message_is_normalized(self, tmp_path):
        """Regression guard for the exact bug report: yt-dlp's own message
        ("There is no video in this post") must never reach the user as the
        primary error - see classify_error()."""
        FakeYoutubeDL.raise_exc = DownloadError("ERROR: [Instagram] ABC123: There is no video in this post")
        with pytest.raises(NoDownloadableMediaError) as exc_info:
            ytdlp_service.analyze(INSTAGRAM_URL, _settings(tmp_path))
        assert exc_info.value.message == "This post does not contain downloadable media."
        assert "There is no video in this post" in (exc_info.value.technical or "")

    def test_login_required_post_is_normalized_to_auth_required(self, tmp_path):
        FakeYoutubeDL.raise_exc = DownloadError(
            "This content is only available for registered users who follow this account."
        )
        with pytest.raises(PrivateOrLoginRequiredError) as exc_info:
            ytdlp_service.analyze(INSTAGRAM_URL, _settings(tmp_path))
        assert exc_info.value.message == "Instagram requires authentication to access this post."

    def test_rate_limited_anonymous_access_is_normalized_to_auth_required(self, tmp_path):
        FakeYoutubeDL.raise_exc = DownloadError(
            "The webpage request was redirected to the login page. "
            "You have exceeded the rate-limit for accessing posts anonymously"
        )
        with pytest.raises(PrivateOrLoginRequiredError):
            ytdlp_service.analyze(INSTAGRAM_URL, _settings(tmp_path))

    def test_empty_media_response_is_normalized_to_unavailable(self, tmp_path):
        FakeYoutubeDL.raise_exc = DownloadError("Instagram sent an empty media response.")
        with pytest.raises(UnavailableMediaError) as exc_info:
            ytdlp_service.analyze(INSTAGRAM_URL, _settings(tmp_path))
        assert exc_info.value.message == "This post is unavailable or you may not have access to it."
