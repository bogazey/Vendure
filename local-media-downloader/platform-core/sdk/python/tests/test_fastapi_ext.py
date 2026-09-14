"""Dedicated FastAPI integration tests for `platform_client.fastapi_ext`
(previously reported as UNTESTED). Wires the real dependency factories
into a real, minimal FastAPI app and drives it with `TestClient` - proves
auth dependency behavior, identity resolution, entitlement retrieval,
require_capability, error behavior, and service-outage behavior."""
from __future__ import annotations

import httpx
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from platform_client.client import PlatformClient
from platform_client.fastapi_ext import LocalSession, make_get_current_platform_user, make_require_capability

CURRENT_SESSION: LocalSession | None = None


def _session_lookup() -> LocalSession | None:
    return CURRENT_SESSION


@pytest.fixture(autouse=True)
def _reset_session():
    global CURRENT_SESSION
    CURRENT_SESSION = None
    yield
    CURRENT_SESSION = None


def _make_client(handler) -> PlatformClient:
    return PlatformClient(base_url="https://auth.example.test", client_id="demo-client", client_secret="s3cr3t")


def _mock_http_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


# --- get_current_platform_user -------------------------------------------------


def test_auth_dependency_rejects_when_no_local_session():
    app = FastAPI()

    @app.get("/me")
    def me(user=Depends(make_get_current_platform_user(_session_lookup))):
        return {"sub": user.sub}

    client = TestClient(app)
    resp = client.get("/me")
    assert resp.status_code == 401


def test_auth_dependency_resolves_identity_when_session_present():
    global CURRENT_SESSION
    CURRENT_SESSION = LocalSession(sub="usr_abc123", email="user@example.test", email_verified=True)

    app = FastAPI()

    @app.get("/me")
    def me(user=Depends(make_get_current_platform_user(_session_lookup))):
        return {"sub": user.sub, "email": user.email, "email_verified": user.email_verified}

    client = TestClient(app)
    resp = client.get("/me")
    assert resp.status_code == 200
    assert resp.json() == {"sub": "usr_abc123", "email": "user@example.test", "email_verified": True}


# --- require_capability: auth, entitlement retrieval, success/failure ----------


def test_require_capability_rejects_when_no_local_session():
    app = FastAPI()
    platform_client = _make_client(None)

    @app.get("/gated")
    def gated(user=Depends(make_require_capability(platform_client, _session_lookup, "widgets.enabled"))):
        return {"sub": user.sub}

    client = TestClient(app)
    resp = client.get("/gated")
    assert resp.status_code == 401


def test_require_capability_grants_access_when_capability_present():
    global CURRENT_SESSION
    CURRENT_SESSION = LocalSession(sub="usr_cap1", email="cap1@example.test", email_verified=True)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "svc-token", "scope": "service:entitlements:read", "expires_in": 900})
        if request.url.path == "/api/v1/service/entitlements/usr_cap1":
            return httpx.Response(200, json={"product_id": "demo", "capabilities": {"widgets.enabled": True}, "sources": []})
        return httpx.Response(404)

    platform_client = _make_client(handler)
    mock_http = _mock_http_client(handler)

    app = FastAPI()

    @app.get("/gated")
    def gated(user=Depends(make_require_capability(platform_client, _session_lookup, "widgets.enabled", http_client=mock_http))):
        return {"sub": user.sub}

    client = TestClient(app)
    resp = client.get("/gated")
    assert resp.status_code == 200
    assert resp.json() == {"sub": "usr_cap1"}


def test_require_capability_denies_access_when_capability_absent():
    global CURRENT_SESSION
    CURRENT_SESSION = LocalSession(sub="usr_cap2", email="cap2@example.test", email_verified=True)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "svc-token", "scope": "service:entitlements:read", "expires_in": 900})
        if request.url.path == "/api/v1/service/entitlements/usr_cap2":
            return httpx.Response(200, json={"product_id": "demo", "capabilities": {}, "sources": []})
        return httpx.Response(404)

    platform_client = _make_client(handler)
    mock_http = _mock_http_client(handler)

    app = FastAPI()

    @app.get("/gated")
    def gated(user=Depends(make_require_capability(platform_client, _session_lookup, "widgets.enabled", http_client=mock_http))):
        return {"sub": user.sub}

    client = TestClient(app)
    resp = client.get("/gated")
    assert resp.status_code == 403


def test_require_capability_at_least_threshold_enforced():
    global CURRENT_SESSION
    CURRENT_SESSION = LocalSession(sub="usr_cap3", email="cap3@example.test", email_verified=True)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "svc-token", "scope": "service:entitlements:read", "expires_in": 900})
        if request.url.path == "/api/v1/service/entitlements/usr_cap3":
            return httpx.Response(200, json={"product_id": "demo", "capabilities": {"download.max_resolution": 480}, "sources": []})
        return httpx.Response(404)

    platform_client = _make_client(handler)
    mock_http = _mock_http_client(handler)

    app = FastAPI()

    @app.get("/gated")
    def gated(user=Depends(make_require_capability(platform_client, _session_lookup, "download.max_resolution", at_least=1080, http_client=mock_http))):
        return {"sub": user.sub}

    client = TestClient(app)
    resp = client.get("/gated")
    assert resp.status_code == 403  # 480 does not satisfy at_least=1080


# --- service outage behavior -----------------------------------------------------


def test_require_capability_returns_503_when_platform_core_is_unreachable():
    global CURRENT_SESSION
    CURRENT_SESSION = LocalSession(sub="usr_outage", email="outage@example.test", email_verified=True)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated Platform Core outage", request=request)

    platform_client = _make_client(handler)
    mock_http = _mock_http_client(handler)

    app = FastAPI()

    @app.get("/gated")
    def gated(user=Depends(make_require_capability(platform_client, _session_lookup, "widgets.enabled", http_client=mock_http))):
        return {"sub": user.sub}

    client = TestClient(app)
    resp = client.get("/gated")
    # Critically NOT 200 (fail open) and NOT 403 (which would incorrectly
    # imply the user's account lacks the capability) - a distinct 503
    # that a caller can tell apart from "access denied."
    assert resp.status_code == 503
    assert resp.status_code not in (200, 403)


def test_require_capability_returns_503_on_a_5xx_from_platform_core():
    global CURRENT_SESSION
    CURRENT_SESSION = LocalSession(sub="usr_outage2", email="outage2@example.test", email_verified=True)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    platform_client = _make_client(handler)
    mock_http = _mock_http_client(handler)

    app = FastAPI()

    @app.get("/gated")
    def gated(user=Depends(make_require_capability(platform_client, _session_lookup, "widgets.enabled", http_client=mock_http))):
        return {"sub": user.sub}

    client = TestClient(app)
    resp = client.get("/gated")
    assert resp.status_code == 503
