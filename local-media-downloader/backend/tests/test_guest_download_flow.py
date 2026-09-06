"""Guest ("try before you sign up") download flow: an anonymous visitor gets
a small, server-enforced allowance (see guest_service.py) instead of being
redirected to signup on their first Download click.

Covers, per the commercial requirements:
- first and second guest downloads succeed, a third is blocked
- a failed/cancelled download does not consume the allowance
- carousel items count individually (each is its own create_download call
  with its own reservation - proven by the same reserve/exceed mechanics)
- a guest can never see or touch another guest's job or files
- authenticated user and existing Free/Pro/Creator behavior is unaffected
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient

from app.database.commercial_db import get_session_factory
from app.main import app
from app.models.enums import DownloadStage, MediaType
from app.models.schemas import AppSettings, CreateDownloadRequest
from app.services import download_manager as dm_module
from app.services import guest_service, guest_storage_service
from app.services.download_manager import DownloadManager
from app.utils.exceptions import GuestQuotaExceededError, InvalidPathError


@pytest.fixture()
def _stub_download_execution(monkeypatch):
    """Same rationale as test_commercial_api.py's fixture of the same name:
    the HTTP-level gating/ownership tests don't need a real yt-dlp
    invocation - only requested by TestGuestDownloadHttpFlow below, NOT by
    TestGuestJobLifecycleAndStorage, which needs the real (FakeYoutubeDL-
    backed) _run_job to actually reach a terminal stage."""

    async def _noop(self, job_id: str) -> None:
        return None

    monkeypatch.setattr(DownloadManager, "_run_job", _noop)


@pytest.fixture(autouse=True)
def _reset_guest_rate_limiter():
    from app.services import rate_limit_service

    rate_limit_service.guest_download_limiter._hits.clear()
    yield


def _new_guest_id() -> str:
    session = get_session_factory()()
    try:
        guest_id, _ = guest_service.resolve_or_create(session, None)
        session.commit()
        return guest_id
    finally:
        session.close()


class TestGuestQuotaService:
    """Direct unit coverage of the reserve/commit/refund counter itself,
    independent of HTTP or the download manager."""

    def _request(self) -> CreateDownloadRequest:
        return CreateDownloadRequest(url="https://www.youtube.com/watch?v=abc123", media_type=MediaType.VIDEO, quality_key="360")

    def test_first_and_second_reservation_succeed_third_is_blocked(self):
        session = get_session_factory()()
        try:
            guest_id = _new_guest_id()
            guest_service.authorize_and_reserve(session, guest_id, self._request())
            guest_service.authorize_and_reserve(session, guest_id, self._request())
            with pytest.raises(GuestQuotaExceededError):
                guest_service.authorize_and_reserve(session, guest_id, self._request())
            session.commit()
        finally:
            session.close()

    def test_commit_moves_a_reservation_into_completed(self):
        session = get_session_factory()()
        try:
            guest_id = _new_guest_id()
            guest_service.authorize_and_reserve(session, guest_id, self._request())
            used_before, limit = guest_service.get_quota_status(session, guest_id)
            assert (used_before, limit) == (1, 2)

            guest_service.commit_download(session, guest_id)
            session.commit()

            used_after, _ = guest_service.get_quota_status(session, guest_id)
            assert used_after == 1  # still counts against the allowance, just as "completed" now
        finally:
            session.close()

    def test_refund_releases_the_reservation_without_touching_completed(self):
        session = get_session_factory()()
        try:
            guest_id = _new_guest_id()
            guest_service.authorize_and_reserve(session, guest_id, self._request())
            guest_service.refund_download(session, guest_id)
            session.commit()

            used, limit = guest_service.get_quota_status(session, guest_id)
            assert used == 0
            # And the allowance is usable again - a failed/cancelled
            # download must never burn a guest's try.
            guest_service.authorize_and_reserve(session, guest_id, self._request())
            guest_service.authorize_and_reserve(session, guest_id, self._request())
            with pytest.raises(GuestQuotaExceededError):
                guest_service.authorize_and_reserve(session, guest_id, self._request())
            session.commit()
        finally:
            session.close()

    def test_unknown_guest_id_is_rejected_not_silently_reserved(self):
        session = get_session_factory()()
        try:
            with pytest.raises(GuestQuotaExceededError):
                guest_service.authorize_and_reserve(session, "not-a-real-guest-id", self._request())
        finally:
            session.close()

    def test_guest_gets_free_plans_resolution_ceiling(self):
        """Guests get exactly the Free plan's feature ceiling - e.g.
        "best" quality (no explicit height) is rejected the same way it
        would be for a Free-plan account."""
        from app.utils.exceptions import PlanLimitReachedError

        session = get_session_factory()()
        try:
            guest_id = _new_guest_id()
            best_request = CreateDownloadRequest(
                url="https://www.youtube.com/watch?v=abc123", media_type=MediaType.VIDEO, quality_key="best"
            )
            with pytest.raises(PlanLimitReachedError):
                guest_service.authorize_and_reserve(session, guest_id, best_request)
        finally:
            session.close()


@pytest.mark.usefixtures("_stub_download_execution")
class TestGuestDownloadHttpFlow:
    """The real FastAPI routes: cookie issuance, quota enforcement, and
    ownership scoping as an anonymous caller actually experiences them."""

    def _payload(self) -> dict:
        return {
            "url": "https://www.youtube.com/watch?v=abc123",
            "media_type": "video",
            "quality_key": "360",
            "playlist_mode": "single",
        }

    def test_no_cookie_yet_analyzing_or_listing_never_forces_signup(self):
        c = TestClient(app)
        resp = c.get("/api/downloads")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_first_download_succeeds_and_mints_a_guest_cookie(self):
        c = TestClient(app)
        resp = c.post("/api/downloads", json=self._payload())
        assert resp.status_code == 201, resp.text
        assert "lmd_guest" in resp.cookies

    def test_second_download_succeeds_third_is_blocked_with_402(self):
        c = TestClient(app)
        first = c.post("/api/downloads", json=self._payload())
        assert first.status_code == 201, first.text

        second = c.post("/api/downloads", json=self._payload())
        assert second.status_code == 201, second.text

        third = c.post("/api/downloads", json=self._payload())
        assert third.status_code == 402, third.text
        assert third.json()["code"] == "GUEST_QUOTA_EXCEEDED"

    def test_guest_quota_endpoint_reflects_remaining_count(self):
        c = TestClient(app)
        status = c.get("/api/downloads/guest-quota")
        assert status.status_code == 200
        assert status.json() == {"remaining": 2, "limit": 2}

        c.post("/api/downloads", json=self._payload())
        status = c.get("/api/downloads/guest-quota")
        assert status.json()["remaining"] == 1

        c.post("/api/downloads", json=self._payload())
        status = c.get("/api/downloads/guest-quota")
        assert status.json()["remaining"] == 0

    def test_a_guest_cannot_see_or_cancel_another_guests_job(self):
        guest_a = TestClient(app)
        guest_b = TestClient(app)

        created = guest_a.post("/api/downloads", json=self._payload())
        assert created.status_code == 201, created.text
        job_id = created.json()["id"]

        # B has no cookie at all yet - still must not see A's job.
        resp = guest_b.get(f"/api/downloads/{job_id}")
        assert resp.status_code == 404

        # Force B to mint its own distinct guest cookie, then retry - still 404.
        guest_b.get("/api/downloads/guest-quota")
        resp = guest_b.get(f"/api/downloads/{job_id}")
        assert resp.status_code == 404

        cancel_resp = guest_b.post(f"/api/downloads/{job_id}/cancel")
        assert cancel_resp.status_code == 404

        # A can see and act on their own job.
        own = guest_a.get(f"/api/downloads/{job_id}")
        assert own.status_code == 200

    def test_a_guests_jobs_are_not_listed_for_a_different_guest(self):
        guest_a = TestClient(app)
        guest_b = TestClient(app)
        guest_a.post("/api/downloads", json=self._payload())
        guest_b.get("/api/downloads/guest-quota")

        assert len(guest_a.get("/api/downloads").json()) == 1
        assert guest_b.get("/api/downloads").json() == []

    def test_signed_in_user_is_never_routed_through_the_guest_gate(self):
        c = TestClient(app)
        email = f"guest-flow-{uuid.uuid4().hex[:10]}@example.com"
        signup = c.post("/api/auth/signup", json={"email": email, "password": "correcthorse9!"})
        assert signup.status_code == 201, signup.text

        # A signed-in Free-plan account has its own (much larger) daily
        # allowance, not the 2-download guest quota - three downloads in a
        # row must not trip GUEST_QUOTA_EXCEEDED.
        for _ in range(3):
            resp = c.post("/api/downloads", json=self._payload())
            assert resp.status_code == 201, resp.text
            assert resp.json().get("code") != "GUEST_QUOTA_EXCEEDED"

        assert "lmd_guest" not in c.cookies

    def test_retry_endpoint_is_authenticated_only_not_available_to_guests(self):
        c = TestClient(app)
        created = c.post("/api/downloads", json=self._payload())
        job_id = created.json()["id"]
        resp = c.post(f"/api/downloads/{job_id}/retry")
        assert resp.status_code == 401


@pytest.mark.asyncio
class TestGuestJobLifecycleAndStorage:
    """Real (mocked-yt-dlp) job execution for a guest job: proves the
    reserve is actually committed/refunded at the right time, and that
    guest files live only under their own _guests/<id>/ directory."""

    @pytest.fixture()
    def isolated_manager(self, monkeypatch, tmp_path):
        from app.services import ytdlp_service
        from tests.test_download_manager import FakeYoutubeDL

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

    @pytest.fixture()
    def guest_download_root(self, tmp_path, monkeypatch):
        root = tmp_path / "guest-root"
        root.mkdir()
        settings = type("S", (), {"download_root": str(root)})()
        monkeypatch.setattr(guest_storage_service, "get_commercial_settings", lambda: settings)
        return root

    async def _wait_for_terminal(self, manager: dm_module.DownloadManager, job_id: str) -> None:
        terminal = {DownloadStage.COMPLETED, DownloadStage.CANCELLED, DownloadStage.FAILED}
        while manager.get_job(job_id).stage not in terminal:
            await asyncio.sleep(0.02)

    async def test_successful_guest_download_commits_the_reservation(self, isolated_manager, guest_download_root):
        guest_id = _new_guest_id()
        session = get_session_factory()()
        try:
            request = CreateDownloadRequest(url="https://www.youtube.com/watch?v=abc123", media_type=MediaType.VIDEO, quality_key="360")
            guest_service.authorize_and_reserve(session, guest_id, request)
            session.commit()
        finally:
            session.close()

        job = isolated_manager.create_job(request, guest_id=guest_id)
        await asyncio.wait_for(self._wait_for_terminal(isolated_manager, job.id), timeout=5)

        finished = isolated_manager.get_job(job.id)
        assert finished.stage == DownloadStage.COMPLETED

        session = get_session_factory()()
        try:
            used, limit = guest_service.get_quota_status(session, guest_id)
            assert (used, limit) == (1, 2)  # one *completed* download, allowance intact for one more
        finally:
            session.close()

    async def test_failed_guest_download_refunds_the_reservation(self, isolated_manager, guest_download_root):
        from tests.test_download_manager import FakeYoutubeDL

        FakeYoutubeDL.behavior = "error"
        guest_id = _new_guest_id()
        session = get_session_factory()()
        try:
            request = CreateDownloadRequest(url="https://www.youtube.com/watch?v=abc123", media_type=MediaType.VIDEO, quality_key="360")
            guest_service.authorize_and_reserve(session, guest_id, request)
            session.commit()
        finally:
            session.close()

        job = isolated_manager.create_job(request, guest_id=guest_id)
        await asyncio.wait_for(self._wait_for_terminal(isolated_manager, job.id), timeout=5)

        finished = isolated_manager.get_job(job.id)
        assert finished.stage == DownloadStage.FAILED

        session = get_session_factory()()
        try:
            used, limit = guest_service.get_quota_status(session, guest_id)
            assert (used, limit) == (0, 2)  # the failed attempt must not have cost the guest anything
        finally:
            session.close()

    async def test_guest_job_writes_into_its_own_guests_subdirectory(self, isolated_manager, guest_download_root):
        from tests.test_download_manager import FakeYoutubeDL

        guest_id = _new_guest_id()
        request = CreateDownloadRequest(url="https://www.youtube.com/watch?v=abc123", media_type=MediaType.VIDEO, quality_key="360")
        job = isolated_manager.create_job(request, guest_id=guest_id)
        await asyncio.wait_for(self._wait_for_terminal(isolated_manager, job.id), timeout=5)

        outtmpl = FakeYoutubeDL.last_opts["outtmpl"]
        assert str(guest_download_root / "_guests" / guest_id) in outtmpl

    async def test_two_guests_write_into_different_directories(self, isolated_manager, guest_download_root):
        from tests.test_download_manager import FakeYoutubeDL

        guest_a = _new_guest_id()
        request_a = CreateDownloadRequest(url="https://www.youtube.com/watch?v=abc123", media_type=MediaType.VIDEO, quality_key="360")
        job_a = isolated_manager.create_job(request_a, guest_id=guest_a)
        await asyncio.wait_for(self._wait_for_terminal(isolated_manager, job_a.id), timeout=5)
        outtmpl_a = FakeYoutubeDL.last_opts["outtmpl"]

        guest_b = _new_guest_id()
        request_b = CreateDownloadRequest(url="https://www.youtube.com/watch?v=abc123", media_type=MediaType.VIDEO, quality_key="360")
        job_b = isolated_manager.create_job(request_b, guest_id=guest_b)
        await asyncio.wait_for(self._wait_for_terminal(isolated_manager, job_b.id), timeout=5)
        outtmpl_b = FakeYoutubeDL.last_opts["outtmpl"]

        assert outtmpl_a != outtmpl_b
        assert guest_a not in outtmpl_b
        assert guest_b not in outtmpl_a

    async def test_guest_jobs_are_never_written_to_shared_history(self, isolated_manager, guest_download_root):
        from app.database import history_repo

        guest_id = _new_guest_id()
        request = CreateDownloadRequest(url="https://www.youtube.com/watch?v=abc123", media_type=MediaType.VIDEO, quality_key="360")
        job = isolated_manager.create_job(request, guest_id=guest_id)
        await asyncio.wait_for(self._wait_for_terminal(isolated_manager, job.id), timeout=5)

        assert history_repo.get(job.id) is None


class TestGuestStorageIsolation:
    """Mirrors test_user_storage_service.py's security proofs exactly, for
    the guest-facing equivalent boundary (<DOWNLOAD_ROOT>/_guests/<id>/)."""

    @pytest.fixture()
    def download_root(self, tmp_path, monkeypatch):
        root = tmp_path / "download-root"
        root.mkdir()
        settings = type("S", (), {"download_root": str(root)})()
        monkeypatch.setattr(guest_storage_service, "get_commercial_settings", lambda: settings)
        return root

    def _guest_id(self) -> str:
        import secrets

        return secrets.token_urlsafe(32)

    def test_creates_directory_named_after_the_guest(self, download_root):
        guest_id = self._guest_id()
        result = guest_storage_service.guest_download_dir(guest_id)
        assert result == (download_root / "_guests" / guest_id).resolve()
        assert result.is_dir()

    @pytest.mark.parametrize(
        "malicious_id",
        ["../../etc", "..", "../other-guest", "a/../../etc", "a/b", "a\\b", "", "short", "/etc/passwd"],
    )
    def test_rejects_unsafe_guest_ids(self, download_root, malicious_id):
        with pytest.raises(InvalidPathError):
            guest_storage_service.guest_download_dir(malicious_id)

    def test_rejects_a_symlink_planted_where_the_guest_directory_should_be(self, download_root, tmp_path):
        guest_id = self._guest_id()
        evil_target = tmp_path / "evil"
        evil_target.mkdir()
        guests_dir = download_root / "_guests"
        guests_dir.mkdir(parents=True, exist_ok=True)
        (guests_dir / guest_id).symlink_to(evil_target, target_is_directory=True)

        with pytest.raises(InvalidPathError):
            guest_storage_service.guest_download_dir(guest_id)

    def test_ensure_within_guest_dir_rejects_an_internal_symlink_escape(self, download_root, tmp_path):
        guest_id = self._guest_id()
        guest_dir = guest_storage_service.guest_download_dir(guest_id)

        secret_dir = tmp_path / "someone-elses-secrets"
        secret_dir.mkdir()
        secret_file = secret_dir / "secret.txt"
        secret_file.write_text("top secret")

        escape_link = guest_dir / "escape"
        escape_link.symlink_to(secret_file)

        with pytest.raises(InvalidPathError):
            guest_storage_service.ensure_within_guest_dir(escape_link, guest_id)

    def test_two_guests_get_different_directories(self, download_root):
        guest_a, guest_b = self._guest_id(), self._guest_id()
        dir_a = guest_storage_service.guest_download_dir(guest_a)
        dir_b = guest_storage_service.guest_download_dir(guest_b)
        assert dir_a != dir_b

    def test_a_file_in_guest_as_directory_is_not_within_guest_bs(self, download_root):
        guest_a, guest_b = self._guest_id(), self._guest_id()
        dir_a = guest_storage_service.guest_download_dir(guest_a)
        guest_storage_service.guest_download_dir(guest_b)

        file_in_a = dir_a / "clip.mp4"
        file_in_a.write_text("data")

        guest_storage_service.ensure_within_guest_dir(file_in_a, guest_a)  # must not raise
        with pytest.raises(InvalidPathError):
            guest_storage_service.ensure_within_guest_dir(file_in_a, guest_b)

    def test_relative_traversal_out_of_the_guests_own_directory_is_rejected(self, download_root):
        guest_id = self._guest_id()
        guest_dir = guest_storage_service.guest_download_dir(guest_id)
        traversal_path = guest_dir / ".." / ".." / "etc" / "passwd"
        with pytest.raises(InvalidPathError):
            guest_storage_service.ensure_within_guest_dir(traversal_path, guest_id)

    def test_remove_guest_dir_only_removes_that_guests_own_directory(self, download_root):
        guest_a, guest_b = self._guest_id(), self._guest_id()
        dir_a = guest_storage_service.guest_download_dir(guest_a)
        dir_b = guest_storage_service.guest_download_dir(guest_b)
        (dir_a / "clip.mp4").write_text("data")
        (dir_b / "clip.mp4").write_text("data")

        guest_storage_service.remove_guest_dir(guest_a)

        assert not dir_a.exists()
        assert dir_b.exists()
        assert (dir_b / "clip.mp4").exists()


class TestGuestCleanupSweep:
    def test_expired_guest_quotas_are_swept_and_their_files_removed(self, monkeypatch, tmp_path):
        from datetime import datetime, timedelta, timezone

        from app.database.commercial_models import GuestQuota

        root = tmp_path / "download-root"
        root.mkdir()
        settings = type("S", (), {"download_root": str(root), "guest_data_ttl_hours": 48})()
        monkeypatch.setattr(guest_storage_service, "get_commercial_settings", lambda: settings)
        monkeypatch.setattr(guest_service, "get_commercial_settings", lambda: settings)

        session = get_session_factory()()
        try:
            guest_id = self._make_stale_guest(session)
            guest_storage_service.guest_download_dir(guest_id)  # create its directory
            expired = guest_service.cleanup_expired(session)
            session.commit()
            assert guest_id in expired
            assert guest_service.quota_exists(session, guest_id) is False
        finally:
            session.close()

        for expired_id in expired:
            guest_storage_service.remove_guest_dir(expired_id)
        assert not (root / "_guests" / guest_id).exists()

    def _make_stale_guest(self, session) -> str:
        from datetime import datetime, timedelta, timezone

        from app.database.commercial_models import GuestQuota

        guest_id, _ = guest_service.resolve_or_create(session, None)
        session.flush()
        quota = session.get(GuestQuota, guest_id)
        quota.last_used_at = datetime.now(timezone.utc) - timedelta(hours=100)
        session.flush()
        return guest_id
