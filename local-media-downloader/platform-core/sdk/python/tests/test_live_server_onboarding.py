"""Mission 6 (Phase 53, SDK half): a full, real end-to-end proof that a
brand-new product can be onboarded and integrated using ONLY the SDK and
Platform Core's public API - no Platform Core source code is edited to
make this pass.

This starts an actual Platform Core FastAPI app (`app.main:app` from
`platform-core/backend`) on a real local TCP port via uvicorn, then drives
the entire flow as a real HTTP client would: signup, the real
Authorization Code + PKCE redirect, a real token exchange, REAL JWKS
fetch + RS256 signature verification of the ID token (this is the one
step that specifically requires a live server - `PyJWKClient` makes its
own HTTP request and cannot be pointed at an in-process ASGI transport),
a real client-credentials service token, and a real effective-entitlement
lookup through `/api/v1/service/entitlements/{user_id}`.

The only thing done "as an admin" via direct DB access (not the CLI) is
seeding a product/plan/capability/service-grant - i.e., exactly the setup
`register_product.py` (Phase 29) automates. Registering the product and
plan through that CLI, rather than by hand here, is exercised separately
in `platform-core/backend/tests/test_register_product_cli.py`.
"""
from __future__ import annotations

import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[3] / "backend"
sys.path.insert(0, str(_BACKEND_DIR))

_TEST_DIR = tempfile.mkdtemp(prefix="platform_client_live_test_")
_DB_PATH = f"{_TEST_DIR}/platform.db"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


_PORT = _free_port()
_BASE_URL = f"http://127.0.0.1:{_PORT}"

os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH}"
os.environ["JWT_PRIVATE_KEY_PATH"] = f"{_TEST_DIR}/jwt_signing_key.pem"
os.environ["COOKIE_SIGNING_KEY"] = "live-test-cookie-signing-key"
os.environ["APP_ENV"] = "development"
os.environ["PLATFORM_AUTH_BASE_URL"] = _BASE_URL
os.environ["PLATFORM_API_BASE_URL"] = _BASE_URL

import uvicorn  # noqa: E402

from app.database import models  # noqa: E402,F401 - registers models on Base.metadata
from app.database.db import Base, get_engine, get_session_factory  # noqa: E402
from app.database.seed_roles import ensure_roles  # noqa: E402
from app.main import app  # noqa: E402
from app.models.enums import CapabilityValueType  # noqa: E402
from app.services import capability_service, entitlement_service, oidc_service, product_service, service_auth  # noqa: E402

from platform_client import PlatformClient, generate_pkce_pair  # noqa: E402

Base.metadata.create_all(get_engine())
_session = get_session_factory()()
ensure_roles(_session)
_session.close()

_server: uvicorn.Server | None = None
_server_thread: threading.Thread | None = None


def _wait_for_server(timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            httpx.get(f"{_BASE_URL}/health", timeout=0.5)
            return
        except httpx.HTTPError:
            time.sleep(0.05)
    raise RuntimeError("Platform Core test server did not start in time.")


@pytest.fixture(scope="module", autouse=True)
def _live_server():
    global _server, _server_thread
    config = uvicorn.Config(app, host="127.0.0.1", port=_PORT, log_level="error")
    _server = uvicorn.Server(config)
    _server_thread = threading.Thread(target=_server.run, daemon=True)
    _server_thread.start()
    _wait_for_server()
    yield
    _server.should_exit = True
    _server_thread.join(timeout=10)


@pytest.fixture(scope="module")
def sample_future_product():
    """Stands in for what `register_product.py` (Phase 29) automates -
    onboarding "Sample Future Product" without touching Platform Core
    source (mission-brief Phase 53)."""
    session = get_session_factory()()
    from app.database.models import User

    bootstrap_admin = User(email="bootstrap-sfp@example.com", password_hash="x", email_verified=True)
    session.add(bootstrap_admin)
    session.flush()

    product = product_service.create_product(
        session, "sample-future-product", "Sample Future Product", "sfp.example", "live", None
    )
    free_plan = entitlement_service.get_or_create_plan(session, product.id, "free", "Free")
    pro_plan = entitlement_service.get_or_create_plan(session, product.id, "pro", "Pro")
    capability_service.define_capability(session, product.id, "widgets.max", CapabilityValueType.INTEGER)
    capability_service.set_plan_entitlement(session, free_plan, "widgets.max", 3)
    capability_service.set_plan_entitlement(session, pro_plan, "widgets.max", capability_service.UNLIMITED)

    oauth_client, client_secret = oidc_service.register_client(
        session, bootstrap_admin, "sample-future-product-client", "Sample Future Product",
        product.id, [f"{_BASE_URL}/sfp/callback"],
    )
    service_auth.grant_scope(session, bootstrap_admin, oauth_client, "service:entitlements:read")
    session.commit()

    return {
        "product_id": product.id, "client_id": oauth_client.client_id, "client_secret": client_secret,
        "free_plan": free_plan, "pro_plan": pro_plan,
    }


def test_full_sso_and_entitlement_flow_using_only_the_sdk(sample_future_product):
    client = PlatformClient(
        base_url=_BASE_URL,
        client_id=sample_future_product["client_id"],
        client_secret=sample_future_product["client_secret"],
        redirect_uri=f"{_BASE_URL}/sfp/callback",
    )

    http = httpx.Client(base_url=_BASE_URL)

    signup = http.post("/api/v1/auth/signup", json={"email": "sfp-user@example.com", "password": "correct-horse-battery"})
    assert signup.status_code == 201

    verifier, challenge = generate_pkce_pair()
    state = "sfp-state-123"
    authorize_url = client.authorize_url(state=state, code_challenge=challenge)
    # Strip the base_url prefix since `http` already has it as base_url.
    authorize_path = authorize_url[len(_BASE_URL):]
    redirect = http.get(authorize_path, follow_redirects=False)
    assert redirect.status_code == 302, redirect.text
    parsed = urlparse(redirect.headers["location"])
    query = parse_qs(parsed.query)
    assert query["state"] == [state]
    code = query["code"][0]

    tokens = client.exchange_code(code=code, code_verifier=verifier, http_client=http)
    assert tokens.access_token
    assert tokens.id_token

    # The one step that specifically requires a real live server: fetching
    # JWKS over real HTTP and verifying a real RS256 signature.
    user = client.verify_id_token(tokens.id_token)
    assert user.email == "sfp-user@example.com"
    assert user.sub.startswith("usr_")

    # No entitlement granted yet.
    entitlement = client.get_my_entitlement(tokens.access_token, http_client=http)
    assert entitlement["entitled"] is False

    # Grant the free plan directly (standing in for a real signup flow
    # that would auto-grant a free plan - out of scope for this SDK test).
    session = get_session_factory()()
    from app.database.models import User as UserModel

    admin = session.query(UserModel).filter_by(email="bootstrap-sfp@example.com").first()
    target = session.query(UserModel).filter_by(email="sfp-user@example.com").first()
    from app.models.enums import EntitlementSource

    entitlement_service.grant_or_change(
        session, admin, target, sample_future_product["product_id"], "free", EntitlementSource.FREE, None, None
    )
    session.commit()
    session.close()

    entitlement_after_grant = client.get_my_entitlement(tokens.access_token, http_client=http)
    assert entitlement_after_grant["entitled"] is True
    assert entitlement_after_grant["entitlement"]["plan_slug"] == "free"

    # Service-to-service: this product's OWN backend asking for the
    # effective (typed-capability) entitlement view, no user token
    # involved.
    service_token = client.get_service_token(http_client=http)
    effective = client.get_effective_entitlements(user.sub, service_token, http_client=http)
    assert effective["product_id"] == sample_future_product["product_id"]
    assert effective["capabilities"]["widgets.max"] == 3  # the free plan's value

    assert client.has_capability(effective, "widgets.max", at_least=1) is True
    assert client.has_capability(effective, "widgets.max", at_least=10) is False
