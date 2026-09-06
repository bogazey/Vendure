import os
import time
from pathlib import Path
from types import SimpleNamespace

from app.services import media_cleanup_service


def _settings(root: Path):
    return SimpleNamespace(
        download_root=str(root),
        authenticated_media_ttl_hours=24,
        partial_media_ttl_hours=6,
        media_cleanup_interval_minutes=60,
        media_max_bytes=40 * 1024**3,
    )


def _age(path: Path, hours: int):
    timestamp = time.time() - hours * 3600
    os.utime(path, (timestamp, timestamp))


def test_stale_authenticated_media_is_removed(tmp_path, monkeypatch):
    media = tmp_path / "user" / "old.mp4"
    media.parent.mkdir()
    media.write_bytes(b"old")
    _age(media, 25)
    monkeypatch.setattr(media_cleanup_service, "get_commercial_settings", lambda: _settings(tmp_path))
    assert media_cleanup_service.cleanup_media_files() == 1
    assert not media.exists()


def test_recent_and_active_media_are_preserved(tmp_path, monkeypatch):
    recent = tmp_path / "user" / "recent.mp4"
    active = tmp_path / "user" / "active.part"
    recent.parent.mkdir()
    recent.write_bytes(b"recent")
    active.write_bytes(b"active")
    _age(active, 8)
    monkeypatch.setattr(media_cleanup_service, "get_commercial_settings", lambda: _settings(tmp_path))
    assert media_cleanup_service.cleanup_media_files(active_paths={active}) == 0
    assert recent.exists() and active.exists()


def test_stale_partial_is_removed(tmp_path, monkeypatch):
    partial = tmp_path / "user" / "video.mp4.part"
    partial.parent.mkdir()
    partial.write_bytes(b"partial")
    _age(partial, 7)
    monkeypatch.setattr(media_cleanup_service, "get_commercial_settings", lambda: _settings(tmp_path))
    assert media_cleanup_service.cleanup_media_files() == 1
    assert not partial.exists()


def test_guest_regular_media_waits_for_guest_ttl_cleanup(tmp_path, monkeypatch):
    media = tmp_path / "_guests" / ("g" * 32) / "old.mp4"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"old")
    _age(media, 30)
    monkeypatch.setattr(media_cleanup_service, "get_commercial_settings", lambda: _settings(tmp_path))
    assert media_cleanup_service.cleanup_media_files() == 0
    assert media.exists()


def test_symlink_boundary_is_never_followed(tmp_path, monkeypatch):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    victim = outside / "victim.part"
    victim.write_bytes(b"keep")
    _age(victim, 10)
    (root / "escape").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(media_cleanup_service, "get_commercial_settings", lambda: _settings(root))
    media_cleanup_service.cleanup_media_files()
    assert victim.exists()


def test_storage_ceiling_removes_oldest_inactive_file(tmp_path, monkeypatch):
    old = tmp_path / "user" / "old.mp4"
    new = tmp_path / "user" / "new.mp4"
    old.parent.mkdir()
    old.write_bytes(b"1234")
    new.write_bytes(b"5678")
    _age(old, 2)
    settings = _settings(tmp_path)
    settings.media_max_bytes = 4
    monkeypatch.setattr(media_cleanup_service, "get_commercial_settings", lambda: settings)
    assert media_cleanup_service.cleanup_media_files() == 1
    assert not old.exists() and new.exists()
