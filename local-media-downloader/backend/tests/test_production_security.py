from types import SimpleNamespace
import asyncio

from starlette.requests import Request

from app import main
from app.api import routes_health
from app.services import email_service
from app.utils.exceptions import ExtractorFailureError


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


def test_production_error_responses_hide_technical_details(monkeypatch):
    monkeypatch.setattr(main, "get_commercial_settings", lambda: SimpleNamespace(app_env="production"))
    request = Request({"type": "http", "method": "GET", "path": "/api/test", "headers": []})
    response = asyncio.run(main.app_error_handler(request, ExtractorFailureError("Try again.", technical="secret path")))
    assert b"secret path" not in response.body
    assert b'"technical":null' in response.body

    response = asyncio.run(main.unhandled_error_handler(request, RuntimeError("database password leaked")))
    assert b"database password leaked" not in response.body
    assert b'"technical":null' in response.body
