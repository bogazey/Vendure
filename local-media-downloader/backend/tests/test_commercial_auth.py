"""AuthService: signup/login/refresh/logout/password-reset lifecycle, plus
the auth API's cookie handling and rate limiting."""
import uuid

import pytest

from app.services.auth_service import auth_service
from app.services import security_service
from app.utils.exceptions import (
    AccountDisabledError,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidTokenError,
)


def _email() -> str:
    return f"user-{uuid.uuid4().hex[:12]}@example.com"


class TestSignupLogin:
    def test_signup_creates_active_free_user(self, db_session):
        result = auth_service.signup(db_session, _email(), "correcthorse9!")
        assert result.user.status == "active"
        assert result.user.role == "user"
        assert result.user.email_verified is False
        assert result.access_token
        assert result.refresh_token

    def test_signup_duplicate_email_rejected(self, db_session):
        email = _email()
        auth_service.signup(db_session, email, "correcthorse9!")
        with pytest.raises(EmailAlreadyRegisteredError):
            auth_service.signup(db_session, email, "anotherpass9!")

    def test_signup_normalizes_email_case(self, db_session):
        email = _email()
        auth_service.signup(db_session, email.upper(), "correcthorse9!")
        with pytest.raises(EmailAlreadyRegisteredError):
            auth_service.signup(db_session, email.lower(), "correcthorse9!")

    def test_login_with_correct_password(self, db_session):
        email = _email()
        auth_service.signup(db_session, email, "correcthorse9!")
        result = auth_service.login(db_session, email, "correcthorse9!")
        assert result.user.email == email

    def test_login_wrong_password_rejected(self, db_session):
        email = _email()
        auth_service.signup(db_session, email, "correcthorse9!")
        with pytest.raises(InvalidCredentialsError):
            auth_service.login(db_session, email, "wrongpassword9!")

    def test_login_unknown_email_rejected_same_error_as_wrong_password(self, db_session):
        # Same exception type/message for "no such user" and "wrong password"
        # - the API must not let an attacker distinguish account existence.
        with pytest.raises(InvalidCredentialsError):
            auth_service.login(db_session, _email(), "whatever9!")

    def test_login_disabled_account_rejected(self, db_session):
        email = _email()
        result = auth_service.signup(db_session, email, "correcthorse9!")
        result.user.status = "disabled"
        db_session.flush()
        with pytest.raises(AccountDisabledError):
            auth_service.login(db_session, email, "correcthorse9!")


class TestRememberMe:
    """"Keep me logged in": whether a session's cookies get a Max-Age
    (persistent, survives browser restarts) or none at all (a true session
    cookie, cleared once the browser closes) - see
    routes_auth._set_session_cookies. AuthService itself only tracks the
    boolean choice through signup/login/refresh; the HTTP-level Set-Cookie
    assertions live in test_commercial_api.py."""

    def test_login_defaults_to_remember_me_false(self, db_session):
        email = _email()
        auth_service.signup(db_session, email, "correcthorse9!")
        result = auth_service.login(db_session, email, "correcthorse9!")
        assert result.remember_me is False

    def test_login_remember_me_true_is_carried_on_the_result(self, db_session):
        email = _email()
        auth_service.signup(db_session, email, "correcthorse9!")
        result = auth_service.login(db_session, email, "correcthorse9!", remember_me=True)
        assert result.remember_me is True

    def test_signup_is_always_remember_me_true(self, db_session):
        # Signup has no checkbox - preserves the pre-existing, always-
        # persistent behavior a fresh signup had before this option existed.
        result = auth_service.signup(db_session, _email(), "correcthorse9!")
        assert result.remember_me is True

    def test_refresh_preserves_remember_me_true_across_rotation(self, db_session):
        email = _email()
        auth_service.signup(db_session, email, "correcthorse9!")
        login = auth_service.login(db_session, email, "correcthorse9!", remember_me=True)
        db_session.flush()

        refreshed = auth_service.refresh(db_session, login.refresh_token)
        db_session.flush()
        assert refreshed.remember_me is True

        # And it keeps carrying forward through a second rotation.
        refreshed_again = auth_service.refresh(db_session, refreshed.refresh_token)
        assert refreshed_again.remember_me is True

    def test_refresh_preserves_remember_me_false_across_rotation(self, db_session):
        email = _email()
        auth_service.signup(db_session, email, "correcthorse9!")
        login = auth_service.login(db_session, email, "correcthorse9!", remember_me=False)
        db_session.flush()

        refreshed = auth_service.refresh(db_session, login.refresh_token)
        assert refreshed.remember_me is False


class TestRefreshAndLogout:
    def test_refresh_rotates_token_and_revokes_old_one(self, db_session):
        email = _email()
        signup = auth_service.signup(db_session, email, "correcthorse9!")
        db_session.flush()

        refreshed = auth_service.refresh(db_session, signup.refresh_token)
        assert refreshed.refresh_token != signup.refresh_token

        # The old refresh token must no longer work (rotation, not reuse).
        with pytest.raises(InvalidTokenError):
            auth_service.refresh(db_session, signup.refresh_token)

    def test_refresh_with_garbage_token_rejected(self, db_session):
        with pytest.raises(InvalidTokenError):
            auth_service.refresh(db_session, "not-a-real-token")

    def test_logout_revokes_refresh_token(self, db_session):
        email = _email()
        signup = auth_service.signup(db_session, email, "correcthorse9!")
        db_session.flush()
        auth_service.logout(db_session, signup.refresh_token)
        db_session.flush()
        with pytest.raises(InvalidTokenError):
            auth_service.refresh(db_session, signup.refresh_token)


class TestPasswordReset:
    def test_reset_password_flow(self, db_session, monkeypatch):
        email = _email()
        auth_service.signup(db_session, email, "correcthorse9!")
        db_session.flush()

        captured = {}
        monkeypatch.setattr(
            "app.services.email_service.send_password_reset_email",
            lambda to, url: captured.update(to=to, url=url),
        )
        auth_service.request_password_reset(db_session, email)
        db_session.flush()
        assert captured["to"] == email
        token = captured["url"].split("token=")[1]

        auth_service.reset_password(db_session, token, "brandnewpass9!")
        db_session.flush()

        # New password works, old one doesn't.
        auth_service.login(db_session, email, "brandnewpass9!")
        with pytest.raises(InvalidCredentialsError):
            auth_service.login(db_session, email, "correcthorse9!")

    def test_reset_password_token_is_single_use(self, db_session, monkeypatch):
        email = _email()
        auth_service.signup(db_session, email, "correcthorse9!")
        db_session.flush()
        captured = {}
        monkeypatch.setattr(
            "app.services.email_service.send_password_reset_email",
            lambda to, url: captured.update(url=url),
        )
        auth_service.request_password_reset(db_session, email)
        db_session.flush()
        token = captured["url"].split("token=")[1]

        auth_service.reset_password(db_session, token, "brandnewpass9!")
        db_session.flush()
        with pytest.raises(InvalidTokenError):
            auth_service.reset_password(db_session, token, "yetanotherpass9!")

    def test_forgot_password_does_not_reveal_account_existence(self, db_session):
        # No exception, no signal either way, for an email that was never registered.
        auth_service.request_password_reset(db_session, _email())

    def test_reset_password_revokes_active_sessions(self, db_session, monkeypatch):
        email = _email()
        signup = auth_service.signup(db_session, email, "correcthorse9!")
        db_session.flush()
        captured = {}
        monkeypatch.setattr(
            "app.services.email_service.send_password_reset_email",
            lambda to, url: captured.update(url=url),
        )
        auth_service.request_password_reset(db_session, email)
        db_session.flush()
        token = captured["url"].split("token=")[1]
        auth_service.reset_password(db_session, token, "brandnewpass9!")
        db_session.flush()

        with pytest.raises(InvalidTokenError):
            auth_service.refresh(db_session, signup.refresh_token)


class TestEmailVerification:
    def test_verify_email_flow(self, db_session, monkeypatch):
        email = _email()
        captured = {}
        monkeypatch.setattr(
            "app.services.email_service.send_verification_email",
            lambda to, url: captured.update(to=to, url=url),
        )
        result = auth_service.signup(db_session, email, "correcthorse9!")
        db_session.flush()
        assert result.user.email_verified is False
        token = captured["url"].split("token=")[1]

        auth_service.verify_email(db_session, token)
        db_session.flush()
        assert result.user.email_verified is True

    def test_verify_email_rejects_bad_token(self, db_session):
        with pytest.raises(InvalidTokenError):
            auth_service.verify_email(db_session, "not-a-real-token")


class TestSessionCookieLifetimeHttp:
    """HTTP-level: the actual Set-Cookie headers /api/auth/login and
    /api/auth/refresh produce, which is what a real browser (and the
    frontend's silent-refresh fix for the "logged out on refresh" bug)
    actually depends on."""

    @pytest.fixture(autouse=True)
    def _reset_rate_limiters(self):
        # signup_limiter/login_limiter are process-lifetime singletons keyed
        # by client host, and TestClient always reports the same fake host -
        # this class makes several signup/login calls per test, so without a
        # reset it would eventually rate-limit itself (or a later test file
        # in the same run) - same fixture/pattern test_commercial_api.py
        # already uses for exactly this reason.
        from app.services import rate_limit_service

        for limiter in (rate_limit_service.login_limiter, rate_limit_service.signup_limiter):
            limiter._hits.clear()
        yield

    def _client(self):
        from fastapi.testclient import TestClient
        from app.main import app

        return TestClient(app)

    def _signup(self, client, email: str) -> None:
        resp = client.post("/api/auth/signup", json={"email": email, "password": "correcthorse9!"})
        assert resp.status_code == 201, resp.text
        # Signup's own cookies aren't under test here - only login's.
        client.cookies.clear()

    def _set_cookie_headers(self, resp) -> list[str]:
        return resp.headers.get_list("set-cookie")

    def test_login_without_remember_me_sets_session_cookies_no_max_age(self):
        client = self._client()
        email = _email()
        self._signup(client, email)

        resp = client.post("/api/auth/login", json={"email": email, "password": "correcthorse9!"})
        assert resp.status_code == 200, resp.text
        headers = self._set_cookie_headers(resp)
        assert len(headers) == 2
        for header in headers:
            assert "max-age" not in header.lower()

    def test_login_with_remember_me_sets_persistent_cookies_with_max_age(self):
        client = self._client()
        email = _email()
        self._signup(client, email)

        resp = client.post(
            "/api/auth/login", json={"email": email, "password": "correcthorse9!", "remember_me": True}
        )
        assert resp.status_code == 200, resp.text
        headers = self._set_cookie_headers(resp)
        assert len(headers) == 2
        for header in headers:
            assert "max-age" in header.lower()

    def test_refresh_preserves_no_max_age_for_a_non_remembered_session(self):
        client = self._client()
        email = _email()
        self._signup(client, email)
        login_resp = client.post("/api/auth/login", json={"email": email, "password": "correcthorse9!"})
        assert login_resp.status_code == 200, login_resp.text

        refresh_resp = client.post("/api/auth/refresh")
        assert refresh_resp.status_code == 200, refresh_resp.text
        for header in self._set_cookie_headers(refresh_resp):
            assert "max-age" not in header.lower()

    def test_refresh_preserves_max_age_for_a_remembered_session(self):
        client = self._client()
        email = _email()
        self._signup(client, email)
        login_resp = client.post(
            "/api/auth/login", json={"email": email, "password": "correcthorse9!", "remember_me": True}
        )
        assert login_resp.status_code == 200, login_resp.text

        refresh_resp = client.post("/api/auth/refresh")
        assert refresh_resp.status_code == 200, refresh_resp.text
        for header in self._set_cookie_headers(refresh_resp):
            assert "max-age" in header.lower()

    def test_logout_clears_cookies_regardless_of_remember_me(self):
        client = self._client()
        email = _email()
        self._signup(client, email)
        login_resp = client.post(
            "/api/auth/login", json={"email": email, "password": "correcthorse9!", "remember_me": True}
        )
        assert login_resp.status_code == 200, login_resp.text

        logout_resp = client.post("/api/auth/logout")
        assert logout_resp.status_code == 204, logout_resp.text

        # A logged-out client's next authenticated call must be rejected -
        # the cookies were genuinely cleared, not just left as-is.
        me_resp = client.get("/api/account")
        assert me_resp.status_code == 401

    def test_all_cookies_are_httponly_secure_flag_and_samesite_unchanged(self):
        # This patch only changes Max-Age presence - it must never touch the
        # other protections regardless of remember_me.
        client = self._client()
        email = _email()
        self._signup(client, email)
        for remember_me in (False, True):
            resp = client.post(
                "/api/auth/login",
                json={"email": email, "password": "correcthorse9!", "remember_me": remember_me},
            )
            assert resp.status_code == 200, resp.text
            for header in self._set_cookie_headers(resp):
                lowered = header.lower()
                assert "httponly" in lowered
                assert "samesite=lax" in lowered


class TestSecurityService:
    def test_password_hash_is_not_plaintext_and_verifies_correctly(self):
        hashed = security_service.hash_password("correcthorse9!")
        assert hashed != "correcthorse9!"
        assert security_service.verify_password("correcthorse9!", hashed)
        assert not security_service.verify_password("wrongpassword9!", hashed)

    def test_refresh_token_stored_only_as_hash(self):
        raw, token_hash, _ = security_service.generate_refresh_token()
        assert raw != token_hash
        assert security_service.hash_refresh_token(raw) == token_hash


class TestRateLimiter:
    def test_allows_up_to_the_limit_then_blocks(self):
        from app.services.rate_limit_service import RateLimiter

        limiter = RateLimiter()
        key = uuid.uuid4().hex
        for _ in range(5):
            assert limiter.allow(key, max_events=5, window_seconds=60) is True
        assert limiter.allow(key, max_events=5, window_seconds=60) is False

    def test_different_keys_have_independent_budgets(self):
        from app.services.rate_limit_service import RateLimiter

        limiter = RateLimiter()
        key_a, key_b = uuid.uuid4().hex, uuid.uuid4().hex
        for _ in range(5):
            limiter.allow(key_a, max_events=5, window_seconds=60)
        assert limiter.allow(key_a, max_events=5, window_seconds=60) is False
        assert limiter.allow(key_b, max_events=5, window_seconds=60) is True

    def test_reset_clears_a_keys_budget(self):
        from app.services.rate_limit_service import RateLimiter

        limiter = RateLimiter()
        key = uuid.uuid4().hex
        for _ in range(5):
            limiter.allow(key, max_events=5, window_seconds=60)
        assert limiter.allow(key, max_events=5, window_seconds=60) is False
        limiter.reset(key)
        assert limiter.allow(key, max_events=5, window_seconds=60) is True
