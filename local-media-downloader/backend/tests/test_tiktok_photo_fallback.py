"""The TikTok fallback is narrow and preserves every existing extractor."""
from __future__ import annotations

import pytest
from yt_dlp.utils import DownloadError

from app.models.enums import MediaType, Platform
from app.models.schemas import AppSettings
from app.services import tiktok_photo_service, ytdlp_service
from app.utils.exceptions import NetworkError

PHOTO_URL = "https://www.tiktok.com/@creator/photo/7682896059135216916"


class FakeYoutubeDL:
    result: dict | None = None
    error: Exception | None = None
    calls: list[str] = []

    def __init__(self, _opts):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def extract_info(self, url, download=False):
        FakeYoutubeDL.calls.append(url)
        if FakeYoutubeDL.error:
            raise FakeYoutubeDL.error
        return FakeYoutubeDL.result


def _carousel() -> dict:
    return {
        "_type": "playlist", "id": "7682896059135216916", "title": "Photo post", "uploader": "creator",
        "entries": [
            {"id": "one", "formats": [], "thumbnail": "https://cdn.example/1.jpg", "thumbnails": [{"url": "https://cdn.example/1.jpg", "width": 900, "height": 1200}]},
            {"id": "two", "formats": [], "thumbnail": "https://cdn.example/2.webp", "thumbnails": [{"url": "https://cdn.example/2.webp", "width": 1080, "height": 1440}]},
        ],
    }


@pytest.fixture(autouse=True)
def _patch(monkeypatch, tmp_path):
    monkeypatch.setattr(ytdlp_service, "yt_dlp", type("Y", (), {"YoutubeDL": FakeYoutubeDL}))
    monkeypatch.setattr(ytdlp_service, "check_ffmpeg", lambda: (False, None))
    FakeYoutubeDL.result, FakeYoutubeDL.error, FakeYoutubeDL.calls = None, None, []


def _settings(tmp_path) -> AppSettings:
    return AppSettings(download_dir=str(tmp_path), network_timeout_seconds=19, retries=2)


def test_direct_photo_falls_back_after_ytdlp_unsupported(monkeypatch, tmp_path):
    FakeYoutubeDL.error = DownloadError("ERROR: Unsupported URL")
    calls = []
    monkeypatch.setattr(tiktok_photo_service, "extract_photo_info", lambda url, **kwargs: calls.append((url, kwargs)) or _carousel())
    result = ytdlp_service.analyze(PHOTO_URL, _settings(tmp_path))
    assert result.platform == Platform.TIKTOK
    assert result.media_type == MediaType.IMAGE
    assert result.playlist_count == 2
    assert result.media_items[1].image_ext == "webp"
    assert calls == [(PHOTO_URL, {"timeout": 19, "retries": 2})]


def test_selected_carousel_entry_reuses_existing_download_flow(monkeypatch, tmp_path):
    FakeYoutubeDL.error = DownloadError("ERROR: Unsupported URL")
    monkeypatch.setattr(tiktok_photo_service, "extract_photo_info", lambda *_args, **_kwargs: _carousel())
    info = ytdlp_service.extract_entry_for_download(PHOTO_URL, _settings(tmp_path), [2])
    assert info["id"] == "two"
    assert ytdlp_service.pick_best_image(info)[0] == "https://cdn.example/2.webp"


def test_direct_photo_network_error_does_not_invoke_scraping_fallback(monkeypatch, tmp_path):
    FakeYoutubeDL.error = DownloadError("network connection timed out")
    monkeypatch.setattr(tiktok_photo_service, "extract_photo_info", lambda *_a, **_k: pytest.fail("fallback called"))
    with pytest.raises(NetworkError):
        ytdlp_service.analyze(PHOTO_URL, _settings(tmp_path))


def test_normal_tiktok_video_still_uses_only_ytdlp(monkeypatch, tmp_path):
    FakeYoutubeDL.result = {
        "id": "video", "title": "Normal TikTok", "formats": [
            {"format_id": "v", "ext": "mp4", "vcodec": "h264", "acodec": "aac", "height": 720}
        ]
    }
    monkeypatch.setattr(tiktok_photo_service, "extract_photo_info", lambda *_a, **_k: pytest.fail("fallback called"))
    result = ytdlp_service.analyze("https://www.tiktok.com/@creator/video/123", _settings(tmp_path))
    assert result.media_type == MediaType.VIDEO
    assert FakeYoutubeDL.calls == ["https://www.tiktok.com/@creator/video/123"]


def test_instagram_carousel_behavior_is_unchanged(monkeypatch, tmp_path):
    FakeYoutubeDL.result = _carousel()
    monkeypatch.setattr(tiktok_photo_service, "extract_photo_info", lambda *_a, **_k: pytest.fail("fallback called"))
    result = ytdlp_service.analyze("https://www.instagram.com/p/ABC123/", _settings(tmp_path))
    assert result.platform == Platform.INSTAGRAM
    assert result.playlist_count == 2
