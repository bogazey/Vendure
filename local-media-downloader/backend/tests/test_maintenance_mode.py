"""Mission 5, phase 6: a short, operator-toggled maintenance window for the
production migration cutover - see app/main.py's maintenance_mode_middleware
and docs/platform/PRODUCTION_REHEARSAL_PLAN.md."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.config.commercial_settings import get_commercial_settings
from app.main import app

client = TestClient(app)


def _set_maintenance(monkeypatch, value: bool) -> None:
    monkeypatch.setattr(get_commercial_settings(), "maintenance_mode", value)


def test_get_requests_pass_through_during_maintenance(monkeypatch):
    _set_maintenance(monkeypatch, True)
    response = client.get("/api/history")
    assert response.status_code != 503


def test_health_check_is_never_blocked(monkeypatch):
    _set_maintenance(monkeypatch, True)
    response = client.get("/api/health")
    assert response.status_code == 200


def test_mutating_requests_are_rejected_during_maintenance(monkeypatch):
    _set_maintenance(monkeypatch, True)
    response = client.post("/api/auth/signup", json={"email": "maint-test@example.com", "password": "correcthorse9!"})
    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "MAINTENANCE_MODE"
    assert response.headers["retry-after"] == "300"


def test_mutating_requests_work_normally_when_maintenance_is_off(monkeypatch):
    _set_maintenance(monkeypatch, False)
    response = client.post("/api/auth/signup", json={"email": "maint-test-off@example.com", "password": "correcthorse9!"})
    assert response.status_code == 201
