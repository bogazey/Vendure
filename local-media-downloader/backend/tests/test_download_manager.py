"""Download job lifecycle tests. yt-dlp itself is mocked; no network access occurs."""
from __future__ import annotations

import asyncio

import pytest

from app.database import history_repo
from app.models.enums import DownloadStage, MediaType
from app.models.schemas import AppSettings, CreateDownloadRequest
from app.services import download_manager as dm_module
from app.services import ytdlp_service


class FakeYoutubeDL:
    """Stand-in for yt_dlp.YoutubeDL that never touches the network."""

    behavior = "success"  # "success" | "cancel" | "unavailable" | "error"

    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def extract_info(self, url, download=True):
        hooks = self.opts.get("progress_hooks", [])
        for hook in hooks:
            hook({"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100, "speed": 1000, "eta": 1})

        if FakeYoutubeDL.behavior == "cancel":
            for hook in hooks:
                hook({"status": "downloading", "downloaded_bytes": 60, "total_bytes": 100})
            return None

        if FakeYoutubeDL.behavior == "error":
            raise RuntimeError("simulated extractor failure")

        for hook in hooks:
            hook({"status": "finished", "filename": "/tmp/fake_video [abc123].mp4"})

        if FakeYoutubeDL.behavior == "unavailable":
            return None

        return {"title": "Fake Title", "uploader": "Fake Uploader", "thumbnail": "https://example.com/t.jpg", "id": "abc123"}

    def prepare_filename(self, info):
        return "/tmp/fake_video [abc123].mp4"


@pytest.fixture(autouse=True)
def _isolated_manager(monkeypatch, tmp_path):
    manager = dm_module.DownloadManager()
    monkeypatch.setattr(dm_module, "manager", manager)

    fake_settings = AppSettings(download_dir=str(tmp_path), max_concurrent_downloads=2)
    monkeypatch.setattr(dm_module, "get_settings", lambda: fake_settings)
    monkeypatch.setattr(ytdlp_service, "check_ffmpeg", lambda: (True, "/usr/bin/ffmpeg"))
    monkeypatch.setattr(dm_module, "yt_dlp", type("M", (), {"YoutubeDL": FakeYoutubeDL}))
    FakeYoutubeDL.behavior = "success"
    yield manager


@pytest.mark.asyncio
class TestDownloadJobLifecycle:
    async def test_successful_download_completes(self, _isolated_manager):
        request = CreateDownloadRequest(url="https://www.youtube.com/watch?v=abc123", media_type=MediaType.VIDEO)
        job = _isolated_manager.create_job(request)
        await asyncio.wait_for(_wait_for_terminal(_isolated_manager, job.id), timeout=5)

        finished = _isolated_manager.get_job(job.id)
        assert finished.stage == DownloadStage.COMPLETED
        assert finished.title == "Fake Title"

        history = history_repo.get(job.id)
        assert history is not None
        assert history.status == DownloadStage.COMPLETED

    async def test_extractor_error_marks_job_failed(self, _isolated_manager):
        FakeYoutubeDL.behavior = "error"
        request = CreateDownloadRequest(url="https://www.youtube.com/watch?v=abc123", media_type=MediaType.VIDEO)
        job = _isolated_manager.create_job(request)
        await asyncio.wait_for(_wait_for_terminal(_isolated_manager, job.id), timeout=5)

        finished = _isolated_manager.get_job(job.id)
        assert finished.stage == DownloadStage.FAILED
        assert finished.error_message

    async def test_unavailable_media_marks_job_failed(self, _isolated_manager):
        FakeYoutubeDL.behavior = "unavailable"
        request = CreateDownloadRequest(url="https://www.youtube.com/watch?v=abc123", media_type=MediaType.VIDEO)
        job = _isolated_manager.create_job(request)
        await asyncio.wait_for(_wait_for_terminal(_isolated_manager, job.id), timeout=5)

        finished = _isolated_manager.get_job(job.id)
        assert finished.stage == DownloadStage.FAILED
        assert "unavailable" in finished.error_message.lower() or "no media" in finished.error_message.lower()

    async def test_cancel_before_start_marks_cancelled(self, _isolated_manager):
        request = CreateDownloadRequest(url="https://www.youtube.com/watch?v=abc123", media_type=MediaType.VIDEO)
        job = _isolated_manager.create_job(request)
        _isolated_manager.cancel_job(job.id)
        await asyncio.wait_for(_wait_for_terminal(_isolated_manager, job.id), timeout=5)

        finished = _isolated_manager.get_job(job.id)
        assert finished.stage == DownloadStage.CANCELLED

    async def test_list_jobs_returns_all(self, _isolated_manager):
        request = CreateDownloadRequest(url="https://www.youtube.com/watch?v=abc123", media_type=MediaType.VIDEO)
        job = _isolated_manager.create_job(request)
        await asyncio.wait_for(_wait_for_terminal(_isolated_manager, job.id), timeout=5)

        jobs = _isolated_manager.list_jobs()
        assert any(j.id == job.id for j in jobs)


async def _wait_for_terminal(manager: dm_module.DownloadManager, job_id: str) -> None:
    terminal = {DownloadStage.COMPLETED, DownloadStage.CANCELLED, DownloadStage.FAILED}
    while manager.get_job(job_id).stage not in terminal:
        await asyncio.sleep(0.02)
