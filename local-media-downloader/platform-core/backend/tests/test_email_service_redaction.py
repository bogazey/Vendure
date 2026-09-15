"""Mission 15, Phase 43: regression test for the email-logging redaction
fix - outside app_env == "development", the real verification/reset/
email-change URL (which embeds a security-sensitive token) must never
appear in the application log, mirroring Loady's own already-tested
`DisabledEmailBackend` behavior."""
from __future__ import annotations

from app.config.settings import get_settings
from app.services import email_service


def test_development_still_logs_the_real_url(caplog, monkeypatch):
    monkeypatch.setattr(get_settings(), "app_env", "development")
    with caplog.at_level("INFO"):
        email_service.send_password_reset_email("user@example.com", "https://id.example/reset?token=SECRET123")
    assert "SECRET123" in caplog.text


def test_non_development_never_logs_the_url_for_password_reset(caplog, monkeypatch):
    monkeypatch.setattr(get_settings(), "app_env", "production")
    with caplog.at_level("INFO"):
        email_service.send_password_reset_email("user@example.com", "https://id.example/reset?token=SECRET123")
    assert "SECRET123" not in caplog.text
    assert "suppressed" in caplog.text.lower()


def test_non_development_never_logs_the_url_for_verification(caplog, monkeypatch):
    monkeypatch.setattr(get_settings(), "app_env", "staging")
    with caplog.at_level("INFO"):
        email_service.send_verification_email("user@example.com", "https://id.example/verify?token=SECRET456")
    assert "SECRET456" not in caplog.text


def test_non_development_never_logs_the_url_for_email_change(caplog, monkeypatch):
    monkeypatch.setattr(get_settings(), "app_env", "production")
    with caplog.at_level("INFO"):
        email_service.send_email_change_verification("new@example.com", "https://id.example/email-change?token=SECRET789")
    assert "SECRET789" not in caplog.text
