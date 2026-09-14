"""Mission 6 continuation: tests for `platform_client.fastapi_ext.build_platform_router`
- the reference backend implementation of the contract
`@platform-core/react-client` expects (`GET /session`, `GET /entitlements`,
`POST /logout`). Also covers `PlatformClient.primary_source`, the small
helper the router uses to pick one plan to display out of possibly many
contributing sources."""
from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from platform_client.client import PlatformClient
from platform_client.fastapi_ext import LocalSession, build_platform_router

CURRENT_SESSION: LocalSession | None = None
LOGOUT_CALLS: list[bool] = []


def _session_lookup() -> LocalSession | None:
    return CURRENT_SESSION


def _logout() -> None:
    LOGOUT_CALLS.append(True)


@pytest.fixture(autouse=True)
def _reset():
    global CURRENT_SESSION
    CURRENT_SESSION = None
    LOGOUT_CALLS.clear()
    yield
    CURRENT_SESSION = None
    LOGOUT_CALLS.clear()


def _client_and_app(handler, *, product_id: str = "demo") -> tuple[TestClient, httpx.Client]:
    platform_client = PlatformClient(base_url="https://auth.example.test", client_id="demo-client", client_secret="s3cr3t")
    mock_http = httpx.Client(transport=httpx.MockTransport(handler))
    app = FastAPI()
    app.include_router(
        build_platform_router(platform_client, _session_lookup, product_id=product_id, logout=_logout, http_client=mock_http),
        prefix="/api/platform",
    )
    return TestClient(app), mock_http


# --- GET /session --------------------------------------------------------------


def test_session_returns_401_when_signed_out():
    client, _ = _client_and_app(lambda r: httpx.Response(404))
    resp = client.get("/api/platform/session")
    assert resp.status_code == 401


def test_session_returns_user_when_signed_in():
    global CURRENT_SESSION
    CURRENT_SESSION = LocalSession(sub="usr_1", email="a@example.test", email_verified=True)
    client, _ = _client_and_app(lambda r: httpx.Response(404))
    resp = client.get("/api/platform/session")
    assert resp.status_code == 200
    assert resp.json() == {"user": {"sub": "usr_1", "email": "a@example.test", "email_verified": True}}


# --- GET /entitlements -----------------------------------------------------------


def test_entitlements_returns_401_when_signed_out():
    client, _ = _client_and_app(lambda r: httpx.Response(404))
    resp = client.get("/api/platform/entitlements")
    assert resp.status_code == 401


def test_entitlements_picks_the_highest_precedence_source():
    global CURRENT_SESSION
    CURRENT_SESSION = LocalSession(sub="usr_2", email="b@example.test", email_verified=True)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "svc-token", "expires_in": 900})
        if request.url.path == "/api/v1/service/entitlements/usr_2":
            return httpx.Response(
                200,
                json={
                    "product_id": "demo",
                    "capabilities": {"max_saves": 50},
                    # A trial and a real subscription both contribute -
                    # subscription (rank 100) must win over trial (rank 35).
                    "sources": [
                        {"kind": "trial", "plan_id": "p1", "plan_slug": "trial-plan", "status": "active", "expires_at": None},
                        {"kind": "subscription", "plan_id": "p2", "plan_slug": "gamer-plus", "status": "active", "expires_at": None},
                    ],
                },
            )
        return httpx.Response(404)

    client, _ = _client_and_app(handler)
    resp = client.get("/api/platform/entitlements", params={"product_id": "demo"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["plan_slug"] == "gamer-plus"
    assert body["source"] == "subscription"
    assert body["capabilities"] == {"max_saves": 50}
    assert body["product_id"] == "demo"


def test_entitlements_defaults_product_id_to_the_router_configured_one():
    global CURRENT_SESSION
    CURRENT_SESSION = LocalSession(sub="usr_3", email="c@example.test", email_verified=True)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "svc-token", "expires_in": 900})
        return httpx.Response(200, json={"product_id": "demo", "capabilities": {}, "sources": []})

    client, _ = _client_and_app(handler, product_id="filey")
    resp = client.get("/api/platform/entitlements")
    assert resp.status_code == 200
    assert resp.json()["product_id"] == "filey"
    assert resp.json()["plan_slug"] is None
    assert resp.json()["source"] is None


def test_entitlements_returns_503_when_platform_core_is_unreachable():
    global CURRENT_SESSION
    CURRENT_SESSION = LocalSession(sub="usr_4", email="d@example.test", email_verified=True)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated outage", request=request)

    client, _ = _client_and_app(handler)
    resp = client.get("/api/platform/entitlements")
    assert resp.status_code == 503
    assert resp.status_code not in (200, 403)


# --- POST /logout ------------------------------------------------------------------


def test_logout_calls_the_product_supplied_callback_and_returns_204():
    client, _ = _client_and_app(lambda r: httpx.Response(404))
    resp = client.post("/api/platform/logout")
    assert resp.status_code == 204
    assert LOGOUT_CALLS == [True]


def test_logout_works_even_without_an_active_session():
    client, _ = _client_and_app(lambda r: httpx.Response(404))
    resp = client.post("/api/platform/logout")
    assert resp.status_code == 204


# --- PlatformClient.primary_source ------------------------------------------------


def test_primary_source_returns_none_for_no_sources():
    assert PlatformClient.primary_source({"capabilities": {}, "sources": []}) is None


def test_primary_source_picks_highest_ranked_kind():
    sources = [
        {"kind": "legacy:free", "plan_slug": "free"},
        {"kind": "legacy:paddle", "plan_slug": "pro"},
        {"kind": "gifted", "plan_slug": "gifted-plan"},
    ]
    picked = PlatformClient.primary_source({"capabilities": {}, "sources": sources})
    assert picked is not None
    assert picked["plan_slug"] == "pro"
