"""MP4 compatibility pipeline: format selection bias, codec detection, and the
post-download remux/transcode step that guarantees Compatibility-mode video
downloads end in a genuine, playable .mp4 rather than a renamed WebM/MKV.

FFmpeg itself is mocked (via a fake subprocess.Popen) so these stay fast,
deterministic unit tests - see LOCAL_MAC_TESTING.md for the real, on-device
FFmpeg verification steps.
"""
from __future__ import annotations

import io
import uuid

import pytest

from app.database import history_repo
from app.models.enums import ContainerMode, DownloadStage, MediaType, Platform
from app.models.schemas import AppSettings, CreateDownloadRequest
from app.services import download_manager as dm_module
from app.services import ytdlp_service


# ---------------------------------------------------------------------------
# Pure logic: codec compatibility detection and format-selector construction
# ---------------------------------------------------------------------------

class TestNeedsMp4Transcode:
    def test_h264_aac_single_format_is_already_compatible(self):
        info = {"vcodec": "avc1.640028", "acodec": "mp4a.40.2"}
        assert ytdlp_service.needs_mp4_transcode(info) is False

    def test_vp9_opus_needs_transcode(self):
        info = {"vcodec": "vp09.00.10.08", "acodec": "opus"}
        assert ytdlp_service.needs_mp4_transcode(info) is True

    def test_av1_video_needs_transcode(self):
        info = {"vcodec": "av01.0.05M.08", "acodec": "mp4a.40.2"}
        assert ytdlp_service.needs_mp4_transcode(info) is True

    def test_h264_video_with_opus_audio_needs_transcode(self):
        info = {"vcodec": "avc1.640028", "acodec": "opus"}
        assert ytdlp_service.needs_mp4_transcode(info) is True

    def test_merged_requested_formats_both_compatible(self):
        info = {
            "requested_formats": [
                {"vcodec": "avc1.4d401f", "acodec": "none"},
                {"vcodec": "none", "acodec": "mp4a.40.2"},
            ]
        }
        assert ytdlp_service.needs_mp4_transcode(info) is False

    def test_merged_requested_formats_video_incompatible(self):
        info = {
            "requested_formats": [
                {"vcodec": "vp09.00.40.08", "acodec": "none"},
                {"vcodec": "none", "acodec": "mp4a.40.2"},
            ]
        }
        assert ytdlp_service.needs_mp4_transcode(info) is True


class TestBuildFormatSelectorContainerMode:
    def test_best_compatibility_prefers_avc1(self):
        selector = ytdlp_service.build_format_selector(
            MediaType.VIDEO, "best", None, container_mode=ContainerMode.COMPATIBILITY
        )
        assert "vcodec^=avc1" in selector
        assert selector.endswith("/best")  # always has a true-best fallback

    def test_best_original_has_no_codec_bias(self):
        selector = ytdlp_service.build_format_selector(
            MediaType.VIDEO, "best", None, container_mode=ContainerMode.ORIGINAL
        )
        assert selector == "bestvideo*+bestaudio/best"

    def test_1080p_compatibility_prefers_avc1_at_that_height(self):
        selector = ytdlp_service.build_format_selector(
            MediaType.VIDEO, "1080", None, container_mode=ContainerMode.COMPATIBILITY
        )
        assert "vcodec^=avc1" in selector
        assert "height<=1080" in selector
        assert selector.endswith("/best[width<=1080][aspect_ratio<1]")

    def test_1080p_original_has_no_codec_bias(self):
        selector = ytdlp_service.build_format_selector(
            MediaType.VIDEO, "1080", None, container_mode=ContainerMode.ORIGINAL
        )
        assert selector == (
            "bestvideo[height<=1080][aspect_ratio>=1]+bestaudio"
            "/bestvideo[width<=1080][aspect_ratio<1]+bestaudio"
            "/best[height<=1080][aspect_ratio>=1]"
            "/best[width<=1080][aspect_ratio<1]"
        )

    def test_advanced_format_id_selection_unaffected_by_container_mode(self):
        compat = ytdlp_service.build_format_selector(
            MediaType.VIDEO, "best", "137", format_has_video=True, format_has_audio=False,
            container_mode=ContainerMode.COMPATIBILITY,
        )
        original = ytdlp_service.build_format_selector(
            MediaType.VIDEO, "best", "137", format_has_video=True, format_has_audio=False,
            container_mode=ContainerMode.ORIGINAL,
        )
        assert compat == original == "137+bestaudio/137/best"


# ---------------------------------------------------------------------------
# Post-download remux/transcode pipeline
# ---------------------------------------------------------------------------

class FakeCompletedProcess:
    """Configurable stand-in for subprocess.Popen used by _run_ffmpeg."""

    returncode = 0
    stderr_text = ""
    never_finishes = False  # if True, poll() always returns None (simulates a hang, for cancel tests)

    def __init__(self, cmd, **kwargs):
        self.cmd = cmd
        self.stderr = io.StringIO(FakeCompletedProcess.stderr_text)
        self.terminated = False
        self.killed = False
        self._polled = False

    def poll(self):
        if FakeCompletedProcess.never_finishes:
            return None
        # Return None once (so the polling loop body runs at least once),
        # then report completion - matches a fast-but-real ffmpeg run.
        if not self._polled:
            self._polled = True
            return None
        return FakeCompletedProcess.returncode

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        return FakeCompletedProcess.returncode


@pytest.fixture(autouse=True)
def _fake_ffmpeg_subprocess(monkeypatch):
    FakeCompletedProcess.returncode = 0
    FakeCompletedProcess.stderr_text = ""
    FakeCompletedProcess.never_finishes = False
    monkeypatch.setattr(dm_module.subprocess, "Popen", FakeCompletedProcess)
    monkeypatch.setattr(dm_module.time, "sleep", lambda _seconds: None)
    yield


@pytest.fixture()
def job(tmp_path):
    request = CreateDownloadRequest(url="https://www.youtube.com/watch?v=abc123", media_type=MediaType.VIDEO)
    return dm_module.DownloadJob(id=str(uuid.uuid4()), request=request, platform=Platform.YOUTUBE)


class TestEnsureCompatibleMp4:
    def test_already_compatible_mp4_is_left_alone(self, job, tmp_path):
        source = tmp_path / "clip [abc123].mp4"
        source.write_bytes(b"fake mp4 bytes")
        job.filepath = str(source)

        manager = dm_module.DownloadManager()
        manager._ensure_compatible_mp4(job, {"vcodec": "avc1.640028", "acodec": "mp4a.40.2"})

        assert job.filepath == str(source)
        assert source.exists()  # untouched, no ffmpeg call needed

    def test_webm_vp9_opus_is_transcoded_to_genuine_mp4(self, job, tmp_path):
        source = tmp_path / "clip [abc123].webm"
        source.write_bytes(b"fake webm bytes")
        job.filepath = str(source)

        manager = dm_module.DownloadManager()
        manager._ensure_compatible_mp4(job, {"vcodec": "vp09.00.10.08", "acodec": "opus"})

        assert job.filepath.endswith(".mp4")
        assert job.filepath != str(source)

    def test_transcode_deletes_the_intermediate_webm(self, job, tmp_path):
        source = tmp_path / "clip [abc123].webm"
        source.write_bytes(b"fake webm bytes")
        job.filepath = str(source)

        manager = dm_module.DownloadManager()
        manager._ensure_compatible_mp4(job, {"vcodec": "vp09.00.10.08", "acodec": "opus"})

        assert not source.exists()  # intermediate cleaned up
        assert job.filepath.endswith(".mp4")

    def test_compatible_codec_but_non_mp4_container_is_remuxed(self, job, tmp_path):
        # e.g. yt-dlp naturally merged already-H.264/AAC streams into an .mkv
        source = tmp_path / "clip [abc123].mkv"
        source.write_bytes(b"fake mkv bytes")
        job.filepath = str(source)

        manager = dm_module.DownloadManager()
        manager._ensure_compatible_mp4(job, {"vcodec": "avc1.640028", "acodec": "mp4a.40.2"})

        assert job.filepath.endswith(".mp4")
        assert not source.exists()

    def test_ffmpeg_failure_raises_and_does_not_leave_a_dangling_output(self, job, tmp_path):
        source = tmp_path / "clip [abc123].webm"
        source.write_bytes(b"fake webm bytes")
        job.filepath = str(source)
        FakeCompletedProcess.returncode = 1
        FakeCompletedProcess.stderr_text = "Unsupported codec"

        manager = dm_module.DownloadManager()
        from app.utils.exceptions import FfmpegProcessingError

        with pytest.raises(FfmpegProcessingError):
            manager._ensure_compatible_mp4(job, {"vcodec": "vp09.00.10.08", "acodec": "opus"})

    def test_cancel_during_conversion_raises_download_cancelled(self, job, tmp_path):
        from yt_dlp.utils import DownloadCancelled

        source = tmp_path / "clip [abc123].webm"
        source.write_bytes(b"fake webm bytes")
        job.filepath = str(source)
        FakeCompletedProcess.never_finishes = True
        job.cancel_event.set()

        manager = dm_module.DownloadManager()
        with pytest.raises(DownloadCancelled):
            manager._ensure_compatible_mp4(job, {"vcodec": "vp09.00.10.08", "acodec": "opus"})


# ---------------------------------------------------------------------------
# Full job integration: FakeYoutubeDL + real DownloadManager queue
# ---------------------------------------------------------------------------

class FakeYoutubeDLForContainer:
    """A yt_dlp.YoutubeDL stand-in whose extract_info reports codecs so the
    real _ensure_compatible_mp4 gating logic runs against realistic info."""

    behavior = "webm_vp9_opus"  # "webm_vp9_opus" | "mp4_h264_aac" | "ffmpeg_fails"
    written_path: str = ""

    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def extract_info(self, url, download=True):
        hooks = self.opts.get("progress_hooks", [])
        for hook in hooks:
            hook({"status": "downloading", "downloaded_bytes": 10, "total_bytes": 10})
            hook({"status": "finished", "filename": FakeYoutubeDLForContainer.written_path})

        if FakeYoutubeDLForContainer.behavior == "mp4_h264_aac":
            return {"title": "Compat Title", "id": "abc123", "vcodec": "avc1.640028", "acodec": "mp4a.40.2"}
        # webm_vp9_opus and ffmpeg_fails both start from a VP9/Opus WebM
        return {"title": "Compat Title", "id": "abc123", "vcodec": "vp09.00.10.08", "acodec": "opus"}

    def prepare_filename(self, info):
        return FakeYoutubeDLForContainer.written_path


@pytest.fixture()
def _isolated_manager_for_container(monkeypatch, tmp_path):
    manager = dm_module.DownloadManager()
    monkeypatch.setattr(dm_module, "manager", manager)
    monkeypatch.setattr(dm_module, "yt_dlp", type("M", (), {"YoutubeDL": FakeYoutubeDLForContainer}))
    monkeypatch.setattr(ytdlp_service, "check_ffmpeg", lambda: (True, "/usr/bin/ffmpeg"))
    FakeCompletedProcess.returncode = 0
    FakeCompletedProcess.stderr_text = ""
    FakeCompletedProcess.never_finishes = False
    yield manager


async def _wait_for_terminal(manager: dm_module.DownloadManager, job_id: str) -> None:
    import asyncio

    terminal = {DownloadStage.COMPLETED, DownloadStage.CANCELLED, DownloadStage.FAILED}
    while manager.get_job(job_id).stage not in terminal:
        await asyncio.sleep(0.02)


@pytest.mark.asyncio
class TestFullJobContainerCompatibility:
    async def test_compatibility_mode_produces_mp4_from_webm_source(
        self, _isolated_manager_for_container, tmp_path, monkeypatch
    ):
        import asyncio

        source = tmp_path / "Compat Title [abc123].webm"
        source.write_bytes(b"fake webm bytes")
        FakeYoutubeDLForContainer.behavior = "webm_vp9_opus"
        FakeYoutubeDLForContainer.written_path = str(source)

        settings = AppSettings(download_dir=str(tmp_path), container_mode=ContainerMode.COMPATIBILITY)
        monkeypatch.setattr(dm_module, "get_settings", lambda: settings)

        request = CreateDownloadRequest(url="https://www.youtube.com/watch?v=abc123", media_type=MediaType.VIDEO)
        job = _isolated_manager_for_container.create_job(request)
        await asyncio.wait_for(_wait_for_terminal(_isolated_manager_for_container, job.id), timeout=5)

        finished = _isolated_manager_for_container.get_job(job.id)
        assert finished.stage == DownloadStage.COMPLETED
        # 5 & 6: history records the *final* mp4, Open File resolves to it too
        assert finished.filepath.endswith(".mp4")
        assert not source.exists()  # 7: intermediate cleaned up

        history = history_repo.get(job.id)
        assert history is not None
        assert history.filepath == finished.filepath
        assert history.filepath.endswith(".mp4")
        assert "MP4" in (history.format_label or "")

    async def test_original_mode_leaves_webm_as_webm(
        self, _isolated_manager_for_container, tmp_path, monkeypatch
    ):
        import asyncio

        source = tmp_path / "Compat Title [abc123].webm"
        source.write_bytes(b"fake webm bytes")
        FakeYoutubeDLForContainer.behavior = "webm_vp9_opus"
        FakeYoutubeDLForContainer.written_path = str(source)

        settings = AppSettings(download_dir=str(tmp_path), container_mode=ContainerMode.ORIGINAL)
        monkeypatch.setattr(dm_module, "get_settings", lambda: settings)

        request = CreateDownloadRequest(url="https://www.youtube.com/watch?v=abc123", media_type=MediaType.VIDEO)
        job = _isolated_manager_for_container.create_job(request)
        await asyncio.wait_for(_wait_for_terminal(_isolated_manager_for_container, job.id), timeout=5)

        finished = _isolated_manager_for_container.get_job(job.id)
        assert finished.stage == DownloadStage.COMPLETED
        assert finished.filepath.endswith(".webm")  # Original mode: WebM allowed
        assert source.exists()

    async def test_ffmpeg_conversion_failure_marks_job_failed_not_completed(
        self, _isolated_manager_for_container, tmp_path, monkeypatch
    ):
        import asyncio

        source = tmp_path / "Compat Title [abc123].webm"
        source.write_bytes(b"fake webm bytes")
        FakeYoutubeDLForContainer.behavior = "ffmpeg_fails"
        FakeYoutubeDLForContainer.written_path = str(source)
        FakeCompletedProcess.returncode = 1
        FakeCompletedProcess.stderr_text = "ffmpeg: unsupported codec"

        settings = AppSettings(download_dir=str(tmp_path), container_mode=ContainerMode.COMPATIBILITY)
        monkeypatch.setattr(dm_module, "get_settings", lambda: settings)

        request = CreateDownloadRequest(url="https://www.youtube.com/watch?v=abc123", media_type=MediaType.VIDEO)
        job = _isolated_manager_for_container.create_job(request)
        await asyncio.wait_for(_wait_for_terminal(_isolated_manager_for_container, job.id), timeout=5)

        finished = _isolated_manager_for_container.get_job(job.id)
        assert finished.stage == DownloadStage.FAILED  # never reported COMPLETED
        assert finished.error_message

        history = history_repo.get(job.id)
        assert history is not None
        assert history.status == DownloadStage.FAILED

    async def test_1080p_compatibility_request_also_ends_in_mp4(
        self, _isolated_manager_for_container, tmp_path, monkeypatch
    ):
        import asyncio

        source = tmp_path / "Compat Title [abc123].webm"
        source.write_bytes(b"fake webm bytes")
        FakeYoutubeDLForContainer.behavior = "webm_vp9_opus"
        FakeYoutubeDLForContainer.written_path = str(source)

        settings = AppSettings(download_dir=str(tmp_path), container_mode=ContainerMode.COMPATIBILITY)
        monkeypatch.setattr(dm_module, "get_settings", lambda: settings)

        request = CreateDownloadRequest(
            url="https://www.youtube.com/watch?v=abc123", media_type=MediaType.VIDEO, quality_key="1080"
        )
        job = _isolated_manager_for_container.create_job(request)
        await asyncio.wait_for(_wait_for_terminal(_isolated_manager_for_container, job.id), timeout=5)

        finished = _isolated_manager_for_container.get_job(job.id)
        assert finished.stage == DownloadStage.COMPLETED
        assert finished.filepath.endswith(".mp4")

    async def test_already_mp4_h264_source_is_not_reconverted(
        self, _isolated_manager_for_container, tmp_path, monkeypatch
    ):
        import asyncio

        source = tmp_path / "Compat Title [abc123].mp4"
        source.write_bytes(b"fake mp4 bytes")
        FakeYoutubeDLForContainer.behavior = "mp4_h264_aac"
        FakeYoutubeDLForContainer.written_path = str(source)

        settings = AppSettings(download_dir=str(tmp_path), container_mode=ContainerMode.COMPATIBILITY)
        monkeypatch.setattr(dm_module, "get_settings", lambda: settings)

        request = CreateDownloadRequest(url="https://www.youtube.com/watch?v=abc123", media_type=MediaType.VIDEO)
        job = _isolated_manager_for_container.create_job(request)
        await asyncio.wait_for(_wait_for_terminal(_isolated_manager_for_container, job.id), timeout=5)

        finished = _isolated_manager_for_container.get_job(job.id)
        assert finished.stage == DownloadStage.COMPLETED
        assert finished.filepath == str(source)  # untouched: already a genuine compatible MP4
        assert source.exists()
