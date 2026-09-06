from pathlib import Path
from types import SimpleNamespace

import pytest

from app.api import routes_downloads
from app.models.enums import DownloadStage
from app.utils.exceptions import InvalidPathError, JobNotFoundError


def _user(user_id="11111111-1111-1111-1111-111111111111"):
    return SimpleNamespace(id=user_id)


def _record(path: Path, status=DownloadStage.COMPLETED):
    return SimpleNamespace(filepath=str(path), status=status)


def _job(path: Path, guest_id: str, stage=DownloadStage.COMPLETED):
    return SimpleNamespace(filepath=str(path), stage=stage, guest_id=guest_id)


def test_authenticated_owner_can_resolve_completed_file(tmp_path, monkeypatch):
    media = tmp_path / "owned.mp4"
    media.write_bytes(b"media")
    monkeypatch.setattr(routes_downloads.history_repo, "get", lambda job_id, user_id: _record(media))
    monkeypatch.setattr(routes_downloads, "ensure_within_user_dir", lambda path, user_id: path)
    assert routes_downloads._completed_file_for_owner("job", _user(), None) == media


def test_guest_owner_can_resolve_completed_file(tmp_path, monkeypatch):
    media = tmp_path / "guest.jpg"
    media.write_bytes(b"image")
    guest_id = "g" * 32
    monkeypatch.setattr(routes_downloads.manager, "get_job", lambda job_id, guest_id: _job(media, guest_id))
    monkeypatch.setattr(routes_downloads, "ensure_within_guest_dir", lambda path, guest_id: path)
    assert routes_downloads._completed_file_for_owner("job", None, guest_id) == media


def test_another_authenticated_user_cannot_resolve(monkeypatch):
    monkeypatch.setattr(routes_downloads.history_repo, "get", lambda job_id, user_id: None)
    with pytest.raises(JobNotFoundError):
        routes_downloads._completed_file_for_owner("other-job", _user(), None)


def test_another_guest_cannot_resolve(monkeypatch):
    monkeypatch.setattr(routes_downloads.manager, "get_job", lambda job_id, guest_id: (_ for _ in ()).throw(JobNotFoundError("not found")))
    with pytest.raises(JobNotFoundError):
        routes_downloads._completed_file_for_owner("other-job", None, "x" * 32)


def test_traversal_is_rejected(tmp_path, monkeypatch):
    media = tmp_path / "outside.mp4"
    media.write_bytes(b"media")
    monkeypatch.setattr(routes_downloads.history_repo, "get", lambda job_id, user_id: _record(media))
    monkeypatch.setattr(routes_downloads, "ensure_within_user_dir", lambda path, user_id: (_ for _ in ()).throw(InvalidPathError("outside")))
    with pytest.raises(InvalidPathError):
        routes_downloads._completed_file_for_owner("job", _user(), None)


def test_missing_file_is_rejected(tmp_path, monkeypatch):
    missing = tmp_path / "missing.mp4"
    monkeypatch.setattr(routes_downloads.history_repo, "get", lambda job_id, user_id: _record(missing))
    monkeypatch.setattr(routes_downloads, "ensure_within_user_dir", lambda path, user_id: path)
    with pytest.raises(JobNotFoundError):
        routes_downloads._completed_file_for_owner("job", _user(), None)


def test_incomplete_download_is_rejected(tmp_path, monkeypatch):
    media = tmp_path / "partial.mp4"
    media.write_bytes(b"partial")
    monkeypatch.setattr(routes_downloads.history_repo, "get", lambda job_id, user_id: _record(media, DownloadStage.DOWNLOADING))
    with pytest.raises(JobNotFoundError):
        routes_downloads._completed_file_for_owner("job", _user(), None)
