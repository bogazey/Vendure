import json
import logging
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr

from app.config.commercial_settings import CommercialSettings
from app.services import email_service


@pytest.fixture
def configure(monkeypatch):
    def apply(env="production", backend="resend", key="re_test_secret", sender="Loady <noreply@loady.cc>"):
        monkeypatch.setattr(email_service, "get_commercial_settings", lambda: SimpleNamespace(
            app_env=env, email_backend=backend, resend_api_key=SecretStr(key), email_from=sender,
        ))
    apply()
    return apply


@pytest.mark.parametrize("env,backend,expected", [
    ("production", "resend", email_service.ResendEmailBackend),
    ("production", "disabled", email_service.DisabledEmailBackend),
    ("development", "disabled", email_service.DisabledEmailBackend),
    ("development", "log", email_service.LogEmailBackend),
    ("production", "log", email_service.DisabledEmailBackend),
    ("staging", "log", email_service.DisabledEmailBackend),
    ("development", "typo", email_service.DisabledEmailBackend),
    ("production", "typo", email_service.DisabledEmailBackend),
    (" Production ", " RESEND ", email_service.ResendEmailBackend),
])
def test_selection(configure, env, backend, expected):
    configure(env, backend)
    assert isinstance(email_service.get_email_backend(), expected)


def install_transport(monkeypatch, handler):
    original = httpx.Client
    def client(**kwargs):
        assert kwargs["timeout"].connect == 5.0
        assert kwargs["timeout"].read == 10.0
        assert kwargs["timeout"].write == 10.0
        assert kwargs["timeout"].pool == 10.0
        assert kwargs["follow_redirects"] is False
        return original(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(email_service.httpx, "Client", client)


@pytest.mark.parametrize("send,subject", [
    (email_service.send_verification_email, "Verify your email"),
    (email_service.send_password_reset_email, "Reset your password"),
])
def test_resend_payload(configure, monkeypatch, caplog, send, subject):
    requests = []
    def handler(request):
        requests.append(request)
        assert request.method == "POST"
        assert str(request.url) == "https://api.resend.com/emails"
        assert request.headers["Authorization"] == "Bearer re_test_secret"
        payload = json.loads(request.content)
        assert payload["from"] == "Loady <noreply@loady.cc>"
        assert payload["to"] == ["user@example.com"]
        assert payload["subject"] == subject
        assert "https://loady.cc/action?token=private-token" in payload["text"]
        return httpx.Response(200, json={"id": "test-message"})
    install_transport(monkeypatch, handler)
    with caplog.at_level(logging.DEBUG):
        send("user@example.com", "https://loady.cc/action?token=private-token")
    assert len(requests) == 1
    assert "private-token" not in caplog.text
    assert "re_test_secret" not in caplog.text


@pytest.mark.parametrize("failure", [301, 400, 401, 429, 500, "timeout", "network"])
def test_failures_are_sanitized_without_retry(configure, monkeypatch, caplog, failure):
    requests = []
    def handler(request):
        requests.append(request)
        sensitive = "private-token re_test_secret"
        if failure == "timeout":
            raise httpx.ReadTimeout(sensitive, request=request)
        if failure == "network":
            raise httpx.ConnectError(sensitive, request=request)
        return httpx.Response(failure, text=sensitive, headers={"Location": "https://example.com"})
    install_transport(monkeypatch, handler)
    with caplog.at_level(logging.DEBUG):
        assert email_service.send_password_reset_email("user@example.com", "private-token") is None
    assert len(requests) == 1
    assert "Resend delivery failed" in caplog.text
    assert "private-token" not in caplog.text
    assert "re_test_secret" not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.parametrize("key,sender", [("", "a@loady.cc"), ("re_test_secret", ""), ("  ", "  ")])
def test_missing_configuration(configure, monkeypatch, caplog, key, sender):
    configure(key=key, sender=sender)
    def unexpected_client(**kwargs):
        pytest.fail("Missing credentials must not make a request")
    monkeypatch.setattr(email_service.httpx, "Client", unexpected_client)
    email_service.send_verification_email("user@example.com", "private-token")
    assert "set RESEND_API_KEY and EMAIL_FROM" in caplog.text
    assert "private-token" not in caplog.text
    assert "re_test_secret" not in caplog.text


@pytest.mark.parametrize("backend", ["log", "disabled", "unknown"])
def test_production_suppression(configure, caplog, backend):
    configure(backend=backend)
    with caplog.at_level(logging.DEBUG):
        email_service.send_verification_email("user@example.com", "private-token")
        email_service.send_password_reset_email("user@example.com", "private-token")
        # Even a previously created logging backend cannot log in production.
        email_service.LogEmailBackend().send("user@example.com", "private-token", "private-token")
    assert "private-token" not in caplog.text


def test_development_logging(configure, caplog):
    configure("development", "log")
    with caplog.at_level(logging.INFO):
        email_service.send_verification_email("user@example.com", "dev-token")
    assert "dev-token" in caplog.text


def test_settings_from_environment(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test_secret")
    monkeypatch.setenv("EMAIL_FROM", "Loady <noreply@loady.cc>")
    settings = CommercialSettings(_env_file=None)
    assert settings.resend_api_key.get_secret_value() == "re_test_secret"
    assert settings.email_from == "Loady <noreply@loady.cc>"
    assert "re_test_secret" not in repr(settings)
