"""yt-dlp format selector construction and download-opts sanitization wiring.

Container-mode-specific selector bias (Compatibility vs Original) is covered
in tests/test_mp4_compatibility.py; these tests fix container_mode=ORIGINAL
to exercise the underlying selector-construction mechanics without that bias.
"""
from __future__ import annotations

from app.models.enums import ContainerMode, MediaType
from app.models.schemas import AppSettings, CreateDownloadRequest
from app.services import ytdlp_service
from app.services.ytdlp_service import build_download_opts, build_format_selector


class TestBuildFormatSelector:
    def test_best_video(self):
        selector = build_format_selector(MediaType.VIDEO, "best", None, container_mode=ContainerMode.ORIGINAL)
        assert selector == "bestvideo*+bestaudio/best"

    def test_specific_height(self):
        selector = build_format_selector(MediaType.VIDEO, "1080", None, container_mode=ContainerMode.ORIGINAL)
        assert selector == "bestvideo[height<=1080]+bestaudio/best[height<=1080]"

    def test_invalid_quality_key_falls_back_to_best(self):
        selector = build_format_selector(
            MediaType.VIDEO, "not-a-number", None, container_mode=ContainerMode.ORIGINAL
        )
        assert selector == "bestvideo*+bestaudio/best"

    def test_audio_best(self):
        assert build_format_selector(MediaType.AUDIO, "best", None) == "bestaudio/best"

    def test_advanced_video_only_format_merges_with_best_audio(self):
        selector = build_format_selector(
            MediaType.VIDEO, "best", "137", format_has_video=True, format_has_audio=False
        )
        assert selector == "137+bestaudio/137/best"

    def test_advanced_audio_only_format_does_not_merge_with_audio(self):
        # Merging two audio-only streams is invalid in yt-dlp's selector syntax;
        # picking an audio-only advanced format must download it directly.
        selector = build_format_selector(
            MediaType.VIDEO, "best", "140", format_has_video=False, format_has_audio=True
        )
        assert selector == "140/bestaudio/best"
        assert "+bestaudio" not in selector

    def test_advanced_combined_format_downloaded_as_is(self):
        selector = build_format_selector(
            MediaType.VIDEO, "best", "18", format_has_video=True, format_has_audio=True
        )
        assert selector == "18/best"

    def test_advanced_format_without_metadata_falls_back_safely(self):
        # Unknown has_video/has_audio (e.g. an older client) must not merge
        # blindly - falls back to downloading the id as-is.
        selector = build_format_selector(MediaType.VIDEO, "best", "22")
        assert selector == "22/best"


class TestBuildDownloadOpts:
    def _settings(self, **overrides) -> AppSettings:
        return AppSettings(download_dir="/tmp/lmd-test-downloads", **overrides)

    def _noop_hook(self, _d: dict) -> None:
        pass

    def test_enables_cross_platform_filename_sanitization(self):
        request = CreateDownloadRequest(url="https://www.youtube.com/watch?v=abc123")
        opts = build_download_opts(request, self._settings(), "%(title)s.%(ext)s", self._noop_hook, self._noop_hook)
        # This is the actual mechanism relied on for safe filenames on
        # Windows/macOS/Linux (see sanitize discussion) - no home-grown
        # filename sanitizer duplicates this, so we verify it's really wired in.
        assert opts["windowsfilenames"] is True
        assert opts["trim_file_name"] == 150

    def test_audio_mp3_sets_extract_audio_postprocessor(self):
        request = CreateDownloadRequest(
            url="https://www.youtube.com/watch?v=abc123",
            media_type=MediaType.AUDIO,
            audio_format="mp3",
            mp3_bitrate=256,
        )
        opts = build_download_opts(request, self._settings(), "%(title)s.%(ext)s", self._noop_hook, self._noop_hook)
        pp = next(p for p in opts["postprocessors"] if p["key"] == "FFmpegExtractAudio")
        assert pp["preferredcodec"] == "mp3"
        assert pp["preferredquality"] == "256"

    def test_embed_thumbnail_deletes_temp_file_when_not_saving(self):
        request = CreateDownloadRequest(url="https://www.youtube.com/watch?v=abc123", media_type=MediaType.AUDIO)
        settings = self._settings(embed_thumbnail_in_audio=True, save_thumbnail=False)
        opts = build_download_opts(request, settings, "%(title)s.%(ext)s", self._noop_hook, self._noop_hook)
        pp = next(p for p in opts["postprocessors"] if p["key"] == "EmbedThumbnail")
        assert pp["already_have_thumbnail"] is False

    def test_embed_thumbnail_keeps_file_when_save_thumbnail_enabled(self):
        request = CreateDownloadRequest(url="https://www.youtube.com/watch?v=abc123", media_type=MediaType.AUDIO)
        settings = self._settings(embed_thumbnail_in_audio=True, save_thumbnail=True)
        opts = build_download_opts(request, settings, "%(title)s.%(ext)s", self._noop_hook, self._noop_hook)
        pp = next(p for p in opts["postprocessors"] if p["key"] == "EmbedThumbnail")
        assert pp["already_have_thumbnail"] is True

    def test_clip_range_sets_download_ranges(self):
        request = CreateDownloadRequest(
            url="https://www.youtube.com/watch?v=abc123", clip={"start": "00:10", "end": "00:20"}
        )
        opts = build_download_opts(request, self._settings(), "%(title)s.%(ext)s", self._noop_hook, self._noop_hook)
        assert callable(opts["download_ranges"])
        assert opts["force_keyframes_at_cuts"] is True


class TestCheckFfmpeg:
    def test_uses_path_when_found(self, monkeypatch):
        monkeypatch.setattr(ytdlp_service.shutil, "which", lambda name: "/usr/bin/ffmpeg")
        available, path = ytdlp_service.check_ffmpeg()
        assert available is True
        assert path == "/usr/bin/ffmpeg"

    def test_falls_back_to_homebrew_path_on_mac(self, monkeypatch, tmp_path):
        fake_ffmpeg = tmp_path / "ffmpeg"
        fake_ffmpeg.write_text("#!/bin/sh\n")
        fake_ffmpeg.chmod(0o755)

        monkeypatch.setattr(ytdlp_service, "_FFMPEG_FALLBACK_PATHS", (str(fake_ffmpeg),))
        monkeypatch.setattr(ytdlp_service.shutil, "which", lambda name: None)
        available, path = ytdlp_service.check_ffmpeg()
        assert available is True
        assert path == str(fake_ffmpeg)

    def test_reports_missing_when_nothing_found(self, monkeypatch):
        monkeypatch.setattr(ytdlp_service, "_FFMPEG_FALLBACK_PATHS", ("/nonexistent/ffmpeg",))
        monkeypatch.setattr(ytdlp_service.shutil, "which", lambda name: None)
        available, path = ytdlp_service.check_ffmpeg()
        assert available is False
        assert path is None


class TestClassifyError:
    def test_passes_through_app_errors_unchanged(self):
        from app.utils.exceptions import UnavailableMediaError

        original = UnavailableMediaError("custom message")
        assert ytdlp_service.classify_error(original) is original

    def test_cookie_file_not_found_maps_to_friendly_error(self):
        exc = Exception("ERROR: cookie file /bad/path.txt could not open")
        result = ytdlp_service.classify_error(exc)
        assert "cookie file" in result.message.lower()

    def test_unknown_error_falls_back_to_extractor_failure(self):
        from app.utils.exceptions import ExtractorFailureError

        result = ytdlp_service.classify_error(Exception("some completely novel failure"))
        assert isinstance(result, ExtractorFailureError)
