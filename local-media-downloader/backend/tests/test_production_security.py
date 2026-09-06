from types import SimpleNamespace

from app.api import routes_health
from app.services import email_service


def test_production_email_never_uses_log_backend(monkeypatch):
    monkeypatch.setattr(email_service, "get_commercial_settings", lambda: SimpleNamespace(app_env="production", email_backend="log"))
    assert isinstance(email_service.get_email_backend(), email_service.DisabledEmailBackend)


def test_explicit_disabled_email_backend(monkeypatch):
    monkeypatch.setattr(email_service, "get_commercial_settings", lambda: SimpleNamespace(app_env="development", email_backend="disabled"))
    assert isinstance(email_service.get_email_backend(), email_service.DisabledEmailBackend)


def test_production_health_hides_filesystem_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(routes_health, "get_commercial_settings", lambda: SimpleNamespace(app_env="production"))
    monkeypatch.setattr(routes_health, "get_settings", lambda: SimpleNamespace(download_dir=str(tmp_path)))
    monkeypatch.setattr(routes_health.ytdlp_service, "check_ffmpeg", lambda: (True, "/usr/bin/ffmpeg"))
    monkeypatch.setattr(routes_health.ytdlp_service, "get_ytdlp_version", lambda: "test")
    monkeypatch.setattr(routes_health, "database_healthy", lambda: True)
    monkeypatch.setattr(routes_health, "is_directory_writable", lambda path: True)
    health = routes_health.compute_health()
    assert health.ffmpeg_path is None
    assert health.download_dir == ""
