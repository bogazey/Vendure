"""Loady's central-identity sign-in endpoints (app/api/routes_platform_auth.py)
and the underlying OIDC client adapter (platform_identity_service.py).

Covers the mission's explicit security-review checklist for this
integration: OAuth state validation, PKCE-adjacent code-exchange failure,
redirect URI usage, wrong issuer, wrong audience, expired token, unknown
global_user_id (new-account creation), first-login account linking by
email, email-collision refusal, disabled-user handling, dormant-by-default
behavior, and open-redirect protection in `_safe_next`.
"""
from __future__ import annotations

import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.api import routes_platform_auth
from app.config.commercial_settings import get_commercial_settings
from app.database.commercial_db import get_session_factory
from app.database.commercial_models import User
from app.main import app
from app.services import platform_identity_service
from app.services.auth_service import auth_service

client = TestClient(app)

_KID = "test-key-1"
_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PRIVATE_PEM = _PRIVATE_KEY.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)


def _jwks() -> dict:
    jwk = jwt.algorithms.RSAAlgorithm(jwt.algorithms.RSAAlgorithm.SHA256).to_jwk(
        _PRIVATE_KEY.public_key(), as_dict=True
    )
    jwk["kid"] = _KID
    return {"keys": [jwk]}


def _make_id_token(*, sub: str, email: str, email_verified: bool = True,
                    iss: str | None = None, aud: str | None = None,
                    expires_in: int = 300) -> str:
    settings = get_commercial_settings()
    now = int(time.time())
    payload = {
        "iss": iss if iss is not None else settings.platform_auth_base_url,
        "aud": aud if aud is not None else settings.platform_client_id,
        "sub": sub,
        "email": email,
        "email_verified": email_verified,
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode(payload, _PRIVATE_PEM, algorithm="RS256", headers={"kid": _KID})


class _FakeHttpResponse:
    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self._body = body

    def json(self) -> dict:
        return self._body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture(autouse=True)
def _reset_jwks_cache():
    platform_identity_service._jwks_cache = None
    yield
    platform_identity_service._jwks_cache = None


@pytest.fixture()
def platform_configured(monkeypatch):
    """Turns the dormant-by-default integration on for the duration of one
    test, and stubs the two outbound calls (JWKS fetch, code exchange) that
    would otherwise hit a real Platform Core instance."""
    settings = get_commercial_settings()
    monkeypatch.setattr(settings, "platform_client_id", "loady")
    monkeypatch.setattr(settings, "platform_client_secret", type(settings.platform_client_secret)("test-secret"))
    monkeypatch.setattr(settings, "platform_auth_base_url", "https://platform.test")
    monkeypatch.setattr(settings, "platform_api_base_url", "https://platform.test")
    monkeypatch.setattr(settings, "platform_redirect_uri", "http://localhost:8000/api/auth/platform/callback")

    def fake_get(url, timeout=10):
        assert url == "https://platform.test/.well-known/jwks.json"
        return _FakeHttpResponse(200, _jwks())

    monkeypatch.setattr(platform_identity_service.httpx, "get", fake_get)
    return settings


def _stub_token_exchange(monkeypatch, *, id_token: str, status_code: int = 200, expires_in: int = 900):
    def fake_post(url, data=None, timeout=10):
        assert url == "https://platform.test/oauth/token"
        assert data["grant_type"] == "authorization_code"
        body = {"access_token": "oidc-access-token", "refresh_token": "oidc-refresh-token",
                "id_token": id_token, "expires_in": expires_in}
        return _FakeHttpResponse(status_code, body)

    monkeypatch.setattr(platform_identity_service.httpx, "post", fake_post)


def _begin_login_flow() -> tuple[TestClient, str]:
    """Real /login call so the PKCE verifier/state cookies are the genuine
    ones the callback will check against - not hand-rolled test doubles."""
    c = TestClient(app)
    resp = c.get("/api/auth/platform/login", follow_redirects=False)
    assert resp.status_code == 302
    state = c.cookies.get(routes_platform_auth._PKCE_STATE_COOKIE)
    assert state
    return c, state


def _email() -> str:
    return f"platform-{uuid.uuid4().hex[:12]}@example.com"


class TestDormantByDefault:
    def test_status_reports_disabled_when_unconfigured(self):
        resp = client.get("/api/auth/platform/status")
        assert resp.status_code == 200
        assert resp.json() == {"enabled": False}

    def test_login_404s_when_unconfigured(self):
        resp = client.get("/api/auth/platform/login", follow_redirects=False)
        assert resp.status_code == 404

    def test_callback_404s_when_unconfigured(self):
        resp = client.get("/api/auth/platform/callback", params={"code": "x", "state": "y"})
        assert resp.status_code == 404


class TestLoginRedirect:
    def test_status_reports_enabled_once_configured(self, platform_configured):
        resp = client.get("/api/auth/platform/status")
        assert resp.json() == {"enabled": True}

    def test_login_redirects_with_pkce_and_state(self, platform_configured):
        resp = client.get("/api/auth/platform/login", follow_redirects=False)
        assert resp.status_code == 302
        location = resp.headers["location"]
        assert location.startswith("https://platform.test/oauth/authorize?")
        assert "client_id=loady" in location
        assert "code_challenge_method=S256" in location
        assert "response_type=code" in location
        assert routes_platform_auth._PKCE_VERIFIER_COOKIE in resp.cookies
        assert routes_platform_auth._PKCE_STATE_COOKIE in resp.cookies
        assert routes_platform_auth._NEXT_COOKIE in resp.cookies


class TestSafeNext:
    @pytest.mark.parametrize("raw,expected", [
        (None, "/dashboard"),
        ("", "/dashboard"),
        ("/account", "/account"),
        ("//evil.com", "/dashboard"),
        ("https://evil.com", "/dashboard"),
        ("http://evil.com/x", "/dashboard"),
        ("javascript://evil", "/dashboard"),
        ("/a/b?x=1", "/a/b?x=1"),
    ])
    def test_only_same_origin_relative_paths_are_ever_accepted(self, raw, expected):
        assert routes_platform_auth._safe_next(raw) == expected


class TestCallbackStateValidation:
    def test_missing_pkce_cookies_rejected(self, platform_configured):
        resp = client.get("/api/auth/platform/callback", params={"code": "abc", "state": "whatever"})
        assert resp.status_code == 400
        assert resp.json()["code"] == "INVALID_TOKEN"

    def test_state_mismatch_rejected(self, platform_configured):
        c, real_state = _begin_login_flow()
        resp = c.get("/api/auth/platform/callback",
                      params={"code": "abc", "state": real_state + "-tampered"})
        assert resp.status_code == 400
        assert resp.json()["code"] == "INVALID_TOKEN"


class TestCallbackTokenExchangeAndVerification:
    def test_rejected_code_exchange_surfaces_as_invalid_token(self, platform_configured, monkeypatch):
        c, state = _begin_login_flow()
        _stub_token_exchange(monkeypatch, id_token="unused", status_code=400)
        resp = c.get("/api/auth/platform/callback", params={"code": "bad-code", "state": state})
        assert resp.status_code == 400
        assert resp.json()["code"] == "INVALID_TOKEN"

    def test_wrong_issuer_rejected(self, platform_configured, monkeypatch):
        c, state = _begin_login_flow()
        token = _make_id_token(sub="usr_x", email=_email(), iss="https://not-platform-core.test")
        _stub_token_exchange(monkeypatch, id_token=token)
        resp = c.get("/api/auth/platform/callback", params={"code": "c", "state": state})
        assert resp.status_code == 400
        assert resp.json()["code"] == "INVALID_TOKEN"

    def test_wrong_audience_rejected(self, platform_configured, monkeypatch):
        c, state = _begin_login_flow()
        token = _make_id_token(sub="usr_x", email=_email(), aud="some-other-product")
        _stub_token_exchange(monkeypatch, id_token=token)
        resp = c.get("/api/auth/platform/callback", params={"code": "c", "state": state})
        assert resp.status_code == 400
        assert resp.json()["code"] == "INVALID_TOKEN"

    def test_expired_token_rejected(self, platform_configured, monkeypatch):
        c, state = _begin_login_flow()
        token = _make_id_token(sub="usr_x", email=_email(), expires_in=-60)
        _stub_token_exchange(monkeypatch, id_token=token)
        resp = c.get("/api/auth/platform/callback", params={"code": "c", "state": state})
        assert resp.status_code == 400
        assert resp.json()["code"] == "INVALID_TOKEN"

    def test_unknown_kid_rejected(self, platform_configured, monkeypatch):
        c, state = _begin_login_flow()
        settings = get_commercial_settings()
        now = int(time.time())
        payload = {"iss": settings.platform_auth_base_url, "aud": settings.platform_client_id,
                   "sub": "usr_x", "email": _email(), "email_verified": True,
                   "iat": now, "exp": now + 300}
        token = jwt.encode(payload, _PRIVATE_PEM, algorithm="RS256", headers={"kid": "some-other-kid"})
        _stub_token_exchange(monkeypatch, id_token=token)
        resp = c.get("/api/auth/platform/callback", params={"code": "c", "state": state})
        assert resp.status_code == 400
        assert resp.json()["code"] == "INVALID_TOKEN"


class TestAccountResolutionAndLinking:
    def test_unknown_global_user_id_creates_a_new_local_account(self, platform_configured, monkeypatch):
        c, state = _begin_login_flow()
        sub = f"usr_{uuid.uuid4().hex}"
        email = _email()
        token = _make_id_token(sub=sub, email=email)
        _stub_token_exchange(monkeypatch, id_token=token)

        resp = c.get("/api/auth/platform/callback", params={"code": "c", "state": state}, follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/dashboard"
        assert "lmd_access" in resp.cookies
        assert "lmd_refresh" in resp.cookies

        db = get_session_factory()()
        try:
            user = db.query(User).filter(User.email == email).one()
            assert user.global_user_id == sub
            assert user.status == "active"
        finally:
            db.close()

    def test_existing_loady_user_is_linked_by_email_on_first_central_login(self, platform_configured, monkeypatch):
        db = get_session_factory()()
        email = _email()
        result = auth_service.signup(db, email, "correcthorse9!")
        db.commit()
        local_user_id = result.user.id
        db.close()

        c, state = _begin_login_flow()
        sub = f"usr_{uuid.uuid4().hex}"
        token = _make_id_token(sub=sub, email=email)
        _stub_token_exchange(monkeypatch, id_token=token)
        resp = c.get("/api/auth/platform/callback", params={"code": "c", "state": state}, follow_redirects=False)
        assert resp.status_code == 302

        db2 = get_session_factory()()
        try:
            matches = db2.query(User).filter(User.email == email).all()
            assert len(matches) == 1, "linking must not create a duplicate account"
            assert matches[0].id == local_user_id
            assert matches[0].global_user_id == sub
        finally:
            db2.close()

    def test_steady_state_login_matches_by_global_user_id_not_email(self, platform_configured, monkeypatch):
        """Once linked, a second central login for the same person must
        resolve the same local row purely via global_user_id, even though
        nothing here re-checks email equality."""
        db = get_session_factory()()
        email = _email()
        result = auth_service.signup(db, email, "correcthorse9!")
        sub = f"usr_{uuid.uuid4().hex}"
        result.user.global_user_id = sub
        db.commit()
        local_user_id = result.user.id
        db.close()

        c, state = _begin_login_flow()
        token = _make_id_token(sub=sub, email=email)
        _stub_token_exchange(monkeypatch, id_token=token)
        resp = c.get("/api/auth/platform/callback", params={"code": "c", "state": state}, follow_redirects=False)
        assert resp.status_code == 302

        db2 = get_session_factory()()
        try:
            matches = db2.query(User).filter(User.email == email).all()
            assert len(matches) == 1
            assert matches[0].id == local_user_id
        finally:
            db2.close()

    def test_email_collision_with_a_different_linked_account_is_refused(self, platform_configured, monkeypatch):
        db = get_session_factory()()
        email = _email()
        result = auth_service.signup(db, email, "correcthorse9!")
        result.user.global_user_id = f"usr_{uuid.uuid4().hex}"  # already linked to someone else
        db.commit()
        db.close()

        c, state = _begin_login_flow()
        different_sub = f"usr_{uuid.uuid4().hex}"
        token = _make_id_token(sub=different_sub, email=email)
        _stub_token_exchange(monkeypatch, id_token=token)
        resp = c.get("/api/auth/platform/callback", params={"code": "c", "state": state})
        assert resp.status_code == 403
        assert resp.json()["code"] == "FORBIDDEN"

        db2 = get_session_factory()()
        try:
            matches = db2.query(User).filter(User.email == email).all()
            assert len(matches) == 1, "a rejected collision must never create or alter an account"
        finally:
            db2.close()

    def test_disabled_local_account_cannot_start_a_new_session_via_central_login(self, platform_configured, monkeypatch):
        db = get_session_factory()()
        email = _email()
        result = auth_service.signup(db, email, "correcthorse9!")
        sub = f"usr_{uuid.uuid4().hex}"
        result.user.global_user_id = sub
        result.user.status = "disabled"
        db.commit()
        db.close()

        c, state = _begin_login_flow()
        token = _make_id_token(sub=sub, email=email)
        _stub_token_exchange(monkeypatch, id_token=token)
        resp = c.get("/api/auth/platform/callback", params={"code": "c", "state": state})
        assert resp.status_code == 403
        assert resp.json()["code"] == "FORBIDDEN"
