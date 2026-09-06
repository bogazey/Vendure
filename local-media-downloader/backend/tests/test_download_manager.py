"""Download job lifecycle tests. yt-dlp itself is mocked; no network access occurs."""
from __future__ import annotations

import asyncio

import httpx
import pytest

from app.database import history_repo
from app.models.enums import DownloadStage, MediaType
from app.models.schemas import AppSettings, CreateDownloadRequest
from app.services import download_manager as dm_module
from app.services import ytdlp_service


class FakeYoutubeDL:
    """Stand-in for yt_dlp.YoutubeDL that never touches the network."""

    behavior = "success"  # "success" | "cancel" | "unavailable" | "error" | "cancel_after_finish"
    finish_filename = "/tmp/fake_video [abc123].mp4"
    cancel_event_to_set_on_finish = None
    last_opts: dict | None = None

    def __init__(self, opts):
        self.opts = opts
        FakeYoutubeDL.last_opts = opts

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
            hook({"status": "finished", "filename": FakeYoutubeDL.finish_filename})

        if FakeYoutubeDL.behavior == "unavailable":
            return None

        if FakeYoutubeDL.behavior == "cancel_after_finish":
            # Simulates cancel arriving after the download itself finished
            # (e.g. during the merge/convert step) - too late for the
            # progress_hook's DownloadCancelled raise to interrupt anything,
            # but the job must still end up cancelled, not completed.
            FakeYoutubeDL.cancel_event_to_set_on_finish.set()

        return {"title": "Fake Title", "uploader": "Fake Uploader", "thumbnail": "https://example.com/t.jpg", "id": "abc123"}

    def prepare_filename(self, info):
        return FakeYoutubeDL.finish_filename


@pytest.fixture(autouse=True)
def _isolated_manager(monkeypatch, tmp_path):
    manager = dm_module.DownloadManager()
    monkeypatch.setattr(dm_module, "manager", manager)

    fake_settings = AppSettings(download_dir=str(tmp_path), max_concurrent_downloads=2)
    monkeypatch.setattr(dm_module, "get_settings", lambda: fake_settings)
    monkeypatch.setattr(ytdlp_service, "check_ffmpeg", lambda: (True, "/usr/bin/ffmpeg"))
    monkeypatch.setattr(dm_module, "yt_dlp", type("M", (), {"YoutubeDL": FakeYoutubeDL}))
    FakeYoutubeDL.behavior = "success"
    FakeYoutubeDL.finish_filename = "/tmp/fake_video [abc123].mp4"
    FakeYoutubeDL.cancel_event_to_set_on_finish = None
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

    async def test_cancel_arriving_after_download_finishes_is_still_honored(self, _isolated_manager, tmp_path):
        # Regression test: cancelling during the merge/convert step (after
        # the download itself has finished) must not silently report the
        # job as completed, and must clean up the file it just finished.
        real_file = tmp_path / "fake_video [abc123].mp4"
        real_file.write_text("fake video bytes")
        FakeYoutubeDL.behavior = "cancel_after_finish"
        FakeYoutubeDL.finish_filename = str(real_file)

        request = CreateDownloadRequest(url="https://www.youtube.com/watch?v=abc123", media_type=MediaType.VIDEO)
        job = _isolated_manager.create_job(request)
        FakeYoutubeDL.cancel_event_to_set_on_finish = job.cancel_event

        await asyncio.wait_for(_wait_for_terminal(_isolated_manager, job.id), timeout=5)

        finished = _isolated_manager.get_job(job.id)
        assert finished.stage == DownloadStage.CANCELLED
        assert not real_file.exists()

        history = history_repo.get(job.id)
        assert history is not None
        assert history.status == DownloadStage.CANCELLED

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


def _make_real_user() -> str:
    """A job's per-user directory is keyed off a real users.id (FK-enforced
    in the commercial DB), so tests need an actual signed-up account, not
    just any UUID string."""
    import uuid

    from app.database.commercial_db import get_session_factory
    from app.services.auth_service import auth_service

    session = get_session_factory()()
    try:
        result = auth_service.signup(session, f"dm-{uuid.uuid4().hex[:10]}@example.com", "correcthorse9!")
        session.commit()
        return result.user.id
    finally:
        session.close()


@pytest.mark.asyncio
class TestPerUserDownloadDirectory:
    """A job's actual write location (what's handed to yt-dlp as outtmpl)
    must be this user's own <DOWNLOAD_ROOT>/<user_id>/ directory - never
    the shared global download_dir this fixture configures - and never
    another user's directory either."""

    @pytest.fixture()
    def download_root(self, tmp_path, monkeypatch):
        from app.services import user_storage_service

        root = tmp_path / "per-user-root"
        root.mkdir()
        settings = type("S", (), {"download_root": str(root)})()
        monkeypatch.setattr(user_storage_service, "get_commercial_settings", lambda: settings)
        return root

    async def test_job_writes_into_its_owners_directory(self, _isolated_manager, download_root):
        user_id = _make_real_user()
        request = CreateDownloadRequest(url="https://www.youtube.com/watch?v=abc123", media_type=MediaType.VIDEO)
        job = _isolated_manager.create_job(request, user_id=user_id, reservation_id=None)
        await asyncio.wait_for(_wait_for_terminal(_isolated_manager, job.id), timeout=5)

        finished = _isolated_manager.get_job(job.id)
        assert finished.stage == DownloadStage.COMPLETED
        outtmpl = FakeYoutubeDL.last_opts["outtmpl"]
        assert str(download_root / user_id) in outtmpl

    async def test_two_users_jobs_write_into_different_directories(self, _isolated_manager, download_root):
        user_a = _make_real_user()
        request_a = CreateDownloadRequest(url="https://www.youtube.com/watch?v=abc123", media_type=MediaType.VIDEO)
        job_a = _isolated_manager.create_job(request_a, user_id=user_a, reservation_id=None)
        await asyncio.wait_for(_wait_for_terminal(_isolated_manager, job_a.id), timeout=5)
        outtmpl_a = FakeYoutubeDL.last_opts["outtmpl"]

        user_b = _make_real_user()
        request_b = CreateDownloadRequest(url="https://www.youtube.com/watch?v=abc123", media_type=MediaType.VIDEO)
        job_b = _isolated_manager.create_job(request_b, user_id=user_b, reservation_id=None)
        await asyncio.wait_for(_wait_for_terminal(_isolated_manager, job_b.id), timeout=5)
        outtmpl_b = FakeYoutubeDL.last_opts["outtmpl"]

        assert str(download_root / user_a) in outtmpl_a
        assert str(download_root / user_b) in outtmpl_b
        assert outtmpl_a != outtmpl_b

    async def test_job_with_no_user_id_falls_back_to_the_shared_global_dir(self, _isolated_manager, download_root, tmp_path):
        # Backward compatibility: programmatic/legacy jobs created with no
        # user_id (e.g. the lower-level manager.retry_job()) keep the old
        # global-download_dir behavior untouched.
        request = CreateDownloadRequest(url="https://www.youtube.com/watch?v=abc123", media_type=MediaType.VIDEO)
        job = _isolated_manager.create_job(request)
        await asyncio.wait_for(_wait_for_terminal(_isolated_manager, job.id), timeout=5)

        outtmpl = FakeYoutubeDL.last_opts["outtmpl"]
        assert str(tmp_path) in outtmpl  # the fixture's global fake_settings.download_dir
        assert str(download_root) not in outtmpl


class _FakeStreamResponse:
    def __init__(self, chunks: list[bytes], headers: dict | None = None, raise_exc: Exception | None = None):
        self._chunks = chunks
        self.headers = headers or {}
        self._raise_exc = raise_exc

    def raise_for_status(self) -> None:
        if self._raise_exc is not None:
            raise self._raise_exc

    def iter_bytes(self, chunk_size: int = 65536):
        yield from self._chunks


class _FakeStreamCtx:
    def __init__(self, response: _FakeStreamResponse):
        self._response = response

    def __enter__(self):
        return self._response

    def __exit__(self, *exc_info):
        return False


class FakeHttpxClient:
    chunks: list[bytes] = [b"\xff\xd8\xff" + b"0" * 200]
    headers: dict = {}
    raise_exc: Exception | None = None
    last_headers: dict | None = None

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def stream(self, method, url, headers=None):
        FakeHttpxClient.last_headers = headers
        return _FakeStreamCtx(_FakeStreamResponse(FakeHttpxClient.chunks, FakeHttpxClient.headers, FakeHttpxClient.raise_exc))


@pytest.mark.asyncio
class TestImageDownloads:
    """Image downloads must bypass yt-dlp's video pipeline and FFmpeg
    entirely, validate the actual bytes received (never trust a URL
    extension or Content-Type alone), and still respect cancellation and
    per-user directory isolation."""

    @pytest.fixture(autouse=True)
    def _patch_image_pipeline(self, monkeypatch, tmp_path):
        monkeypatch.setattr(dm_module, "httpx", type("M", (), {"Client": FakeHttpxClient, "HTTPError": httpx.HTTPError}))
        # No ffmpeg available at all - proves the image path never needs it.
        monkeypatch.setattr(ytdlp_service, "check_ffmpeg", lambda: (False, None))
        monkeypatch.setattr(
            ytdlp_service,
            "extract_entry_for_download",
            lambda url, settings, playlist_item_indices=None: {
                "id": "img1",
                "title": "A nice photo",
                "uploader": "someone",
                "thumbnail": "https://cdn.example.com/photo.jpg",
                "http_headers": {"Referer": "https://www.instagram.com/"},
            },
        )
        monkeypatch.setattr(
            ytdlp_service,
            "pick_best_image",
            lambda info: ("https://cdn.example.com/photo.jpg", 1080, 1080, "jpg"),
        )
        FakeHttpxClient.chunks = [b"\xff\xd8\xff" + b"0" * 200]
        FakeHttpxClient.raise_exc = None
        FakeHttpxClient.last_headers = None
        yield

    async def test_image_download_completes_without_ffmpeg(self, _isolated_manager):
        request = CreateDownloadRequest(url="https://www.instagram.com/p/ABC123/", media_type=MediaType.IMAGE)
        job = _isolated_manager.create_job(request)
        await asyncio.wait_for(_wait_for_terminal(_isolated_manager, job.id), timeout=5)

        finished = _isolated_manager.get_job(job.id)
        assert finished.stage == DownloadStage.COMPLETED
        assert finished.filepath and finished.filepath.endswith(".jpg")
        assert finished.title == "A nice photo"

        history = history_repo.get(job.id)
        assert history is not None
        assert history.format_label is not None and "Image" in history.format_label

    async def test_image_download_propagates_extractor_headers(self, _isolated_manager):
        request = CreateDownloadRequest(url="https://www.instagram.com/p/ABC123/", media_type=MediaType.IMAGE)
        job = _isolated_manager.create_job(request)
        await asyncio.wait_for(_wait_for_terminal(_isolated_manager, job.id), timeout=5)
        assert FakeHttpxClient.last_headers.get("Referer") == "https://www.instagram.com/"

    async def test_html_response_is_rejected_not_saved_as_an_image(self, _isolated_manager):
        # A blocked/expired CDN link can return an HTML error page with a
        # 200 status - the magic-byte check must catch this even though the
        # URL itself ends in .jpg and nothing raised an HTTP error.
        FakeHttpxClient.chunks = [b"<html><body>blocked</body></html>"]
        request = CreateDownloadRequest(url="https://www.instagram.com/p/ABC123/", media_type=MediaType.IMAGE)
        job = _isolated_manager.create_job(request)
        await asyncio.wait_for(_wait_for_terminal(_isolated_manager, job.id), timeout=5)

        finished = _isolated_manager.get_job(job.id)
        assert finished.stage == DownloadStage.FAILED
        assert finished.filepath is None

    async def test_http_error_marks_job_failed_with_friendly_message(self, _isolated_manager):
        FakeHttpxClient.raise_exc = httpx.HTTPStatusError(
            "403", request=httpx.Request("GET", "https://cdn.example.com/photo.jpg"), response=httpx.Response(403)
        )
        request = CreateDownloadRequest(url="https://www.instagram.com/p/ABC123/", media_type=MediaType.IMAGE)
        job = _isolated_manager.create_job(request)
        await asyncio.wait_for(_wait_for_terminal(_isolated_manager, job.id), timeout=5)

        finished = _isolated_manager.get_job(job.id)
        assert finished.stage == DownloadStage.FAILED
        assert "unavailable" in finished.error_message.lower()

    async def test_cancel_during_image_download_is_honored_and_cleans_up(self, _isolated_manager, tmp_path):
        FakeHttpxClient.chunks = [b"\xff\xd8\xff" + b"0" * 100, b"1" * 100, b"2" * 100]
        request = CreateDownloadRequest(url="https://www.instagram.com/p/ABC123/", media_type=MediaType.IMAGE)
        job = _isolated_manager.create_job(request)
        job.cancel_event.set()
        await asyncio.wait_for(_wait_for_terminal(_isolated_manager, job.id), timeout=5)

        finished = _isolated_manager.get_job(job.id)
        assert finished.stage == DownloadStage.CANCELLED
        # No stray .part file left behind under the configured download dir.
        assert not any(tmp_path.rglob("*.part"))

    async def test_image_job_writes_into_its_owners_directory(self, _isolated_manager, monkeypatch, tmp_path):
        from app.services import user_storage_service

        root = tmp_path / "per-user-root"
        root.mkdir()
        settings = type("S", (), {"download_root": str(root)})()
        monkeypatch.setattr(user_storage_service, "get_commercial_settings", lambda: settings)

        user_id = _make_real_user()
        request = CreateDownloadRequest(url="https://www.instagram.com/p/ABC123/", media_type=MediaType.IMAGE)
        job = _isolated_manager.create_job(request, user_id=user_id, reservation_id=None)
        await asyncio.wait_for(_wait_for_terminal(_isolated_manager, job.id), timeout=5)

        finished = _isolated_manager.get_job(job.id)
        assert finished.stage == DownloadStage.COMPLETED
        assert str(root / user_id) in finished.filepath
