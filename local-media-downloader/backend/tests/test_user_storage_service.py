"""user_storage_service: the single security boundary confining every
authenticated user's downloads to their own <DOWNLOAD_ROOT>/<user_id>/
directory - path traversal, symlink escape, and cross-account access must
all be provably blocked, not just "probably fine"."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.database import history_repo
from app.main import app
from app.services import filesystem_service, user_storage_service
from app.utils.exceptions import InvalidPathError


@pytest.fixture()
def download_root(tmp_path, monkeypatch):
    root = tmp_path / "download-root"
    root.mkdir()
    settings = type("S", (), {"download_root": str(root)})()
    monkeypatch.setattr(user_storage_service, "get_commercial_settings", lambda: settings)
    return root


def _uid() -> str:
    return str(uuid.uuid4())


class TestUserDownloadDir:
    def test_creates_directory_named_after_the_user(self, download_root):
        user_id = _uid()
        result = user_storage_service.user_download_dir(user_id)
        assert result == (download_root / user_id).resolve()
        assert result.is_dir()

    def test_is_idempotent(self, download_root):
        user_id = _uid()
        first = user_storage_service.user_download_dir(user_id)
        second = user_storage_service.user_download_dir(user_id)
        assert first == second

    def test_create_false_does_not_create_the_directory(self, download_root):
        user_id = _uid()
        result = user_storage_service.user_download_dir(user_id, create=False)
        assert not result.exists()


class TestPathTraversalViaUserId:
    @pytest.mark.parametrize(
        "malicious_id",
        [
            "../../etc",
            "..",
            "../other-user",
            "a/../../etc",
            "a/b",
            "a\\b",
            "",
            "   ",
            "/etc/passwd",
        ],
    )
    def test_rejects_unsafe_user_ids(self, download_root, malicious_id):
        with pytest.raises(InvalidPathError):
            user_storage_service.user_download_dir(malicious_id)

    def test_traversal_user_id_never_escapes_download_root(self, download_root, tmp_path):
        """Even if the safe-id regex were ever loosened, prove the actual
        escape attempt fails: a user_id crafted to walk out of
        download_root must never resolve to a path outside it."""
        outside = tmp_path / "outside-secret"
        outside.mkdir()
        traversal_id = f"../{outside.name}"
        with pytest.raises(InvalidPathError):
            user_storage_service.user_download_dir(traversal_id)


class TestSymlinkEscape:
    def test_rejects_a_symlink_planted_where_the_user_directory_should_be(self, download_root, tmp_path):
        user_id = _uid()
        evil_target = tmp_path / "evil"
        evil_target.mkdir()
        (download_root / user_id).symlink_to(evil_target, target_is_directory=True)

        with pytest.raises(InvalidPathError):
            user_storage_service.user_download_dir(user_id)

    def test_ensure_within_user_dir_rejects_a_symlink_planted_inside_the_users_own_directory(
        self, download_root, tmp_path
    ):
        """A symlink INSIDE an otherwise-legitimate user directory that
        points elsewhere must not be usable to escape it - resolving both
        sides before comparing is what catches this."""
        user_id = _uid()
        user_dir = user_storage_service.user_download_dir(user_id)

        secret_dir = tmp_path / "someone-elses-secrets"
        secret_dir.mkdir()
        secret_file = secret_dir / "secret.txt"
        secret_file.write_text("top secret")

        escape_link = user_dir / "escape"
        escape_link.symlink_to(secret_file)

        with pytest.raises(InvalidPathError):
            user_storage_service.ensure_within_user_dir(escape_link, user_id)


class TestCrossUserIsolation:
    def test_two_users_get_different_directories(self, download_root):
        user_a, user_b = _uid(), _uid()
        dir_a = user_storage_service.user_download_dir(user_a)
        dir_b = user_storage_service.user_download_dir(user_b)
        assert dir_a != dir_b

    def test_a_file_in_user_as_directory_is_not_within_user_bs(self, download_root):
        user_a, user_b = _uid(), _uid()
        dir_a = user_storage_service.user_download_dir(user_a)
        user_storage_service.user_download_dir(user_b)  # create B's dir too

        file_in_a = dir_a / "clip.mp4"
        file_in_a.write_text("data")

        # A can act on their own file.
        user_storage_service.ensure_within_user_dir(file_in_a, user_a)  # must not raise

        # B must be denied, even though B is a real, valid authenticated user.
        with pytest.raises(InvalidPathError):
            user_storage_service.ensure_within_user_dir(file_in_a, user_b)

    def test_relative_traversal_out_of_the_users_own_directory_is_rejected(self, download_root):
        user_id = _uid()
        user_dir = user_storage_service.user_download_dir(user_id)
        traversal_path = user_dir / ".." / ".." / "etc" / "passwd"
        with pytest.raises(InvalidPathError):
            user_storage_service.ensure_within_user_dir(traversal_path, user_id)


class TestFilesystemServiceIntegration:
    """ensure_path_permitted(path, user_id=...) - what routes_filesystem.py
    and routes_history.py actually call - delegates to user_storage_service
    for every authenticated caller."""

    def test_open_allowed_within_own_directory(self, download_root):
        user_id = _uid()
        user_dir = user_storage_service.user_download_dir(user_id)
        my_file = user_dir / "clip.mp4"
        my_file.write_text("data")
        filesystem_service.ensure_path_permitted(my_file, user_id=user_id)  # must not raise

    def test_open_denied_for_another_users_file(self, download_root):
        user_a, user_b = _uid(), _uid()
        dir_a = user_storage_service.user_download_dir(user_a)
        user_storage_service.user_download_dir(user_b)
        their_file = dir_a / "clip.mp4"
        their_file.write_text("data")
        with pytest.raises(InvalidPathError):
            filesystem_service.ensure_path_permitted(their_file, user_id=user_b)

    def test_open_denied_for_symlink_escape(self, download_root, tmp_path):
        user_id = _uid()
        user_dir = user_storage_service.user_download_dir(user_id)
        secret = tmp_path / "secret.txt"
        secret.write_text("nope")
        link = user_dir / "link.mp4"
        link.symlink_to(secret)
        with pytest.raises(InvalidPathError):
            filesystem_service.ensure_path_permitted(link, user_id=user_id)


class TestHttpLevelIsolation:
    """The same guarantees at the actual HTTP surface: two real accounts,
    real cookies, real routes - never a query param or header a caller
    could spoof, only the authenticated session."""

    def test_settings_get_returns_a_path_confined_to_this_user(self, download_root):
        c = TestClient(app)
        c.post(
            "/api/auth/signup",
            json={"email": f"storage-{uuid.uuid4().hex[:10]}@example.com", "password": "correcthorse9!"},
        )
        resp = c.get("/api/settings")
        assert resp.status_code == 200
        download_dir = resp.json()["download_dir"]
        assert str(download_root.resolve()) in download_dir

    def test_settings_put_rejects_download_dir_changes(self, download_root, tmp_path):
        c = TestClient(app)
        c.post(
            "/api/auth/signup",
            json={"email": f"storage-{uuid.uuid4().hex[:10]}@example.com", "password": "correcthorse9!"},
        )
        resp = c.put("/api/settings", json={"download_dir": str(tmp_path / "anywhere-i-want")})
        assert resp.status_code == 400

    def test_two_accounts_cannot_open_each_others_files(self, download_root, monkeypatch):
        # This sandbox has no xdg-open/open/explorer installed - stub the OS
        # handler so a successful authorization check doesn't fail on that
        # unrelated missing binary.
        monkeypatch.setattr(filesystem_service, "_open_with_os_handler", lambda path: None)

        client_a = TestClient(app)
        client_b = TestClient(app)

        email_a = f"storage-a-{uuid.uuid4().hex[:8]}@example.com"
        email_b = f"storage-b-{uuid.uuid4().hex[:8]}@example.com"
        resp_a = client_a.post("/api/auth/signup", json={"email": email_a, "password": "correcthorse9!"})
        resp_b = client_b.post("/api/auth/signup", json={"email": email_b, "password": "correcthorse9!"})
        user_a_id = resp_a.json()["id"]

        # Actually write a file into A's real per-user directory and record it.
        dir_a = user_storage_service.user_download_dir(user_a_id)
        clip = dir_a / "my-clip [abc123].mp4"
        clip.write_text("data")
        history_repo.upsert(
            {
                "id": str(uuid.uuid4()),
                "url": "https://www.youtube.com/watch?v=abc123",
                "platform": "youtube",
                "title": "My Clip",
                "uploader": None,
                "thumbnail": None,
                "format_label": "1080p",
                "resolution": "1080p",
                "filepath": str(clip),
                "filesize": 4,
                "created_at": "2026-01-01T00:00:00+00:00",
                "completed_at": "2026-01-01T00:01:00+00:00",
                "status": "completed",
                "error_message": None,
                "user_id": user_a_id,
            }
        )

        # A can open their own file.
        resp = client_a.post("/api/fs/open", json={"path": str(clip)})
        assert resp.status_code == 204

        # B cannot, even knowing the exact path.
        resp = client_b.post("/api/fs/open", json={"path": str(clip)})
        assert resp.status_code == 400

        resp = client_b.post("/api/fs/open-folder", json={"path": str(clip)})
        assert resp.status_code == 400
