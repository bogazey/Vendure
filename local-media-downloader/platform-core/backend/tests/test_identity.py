"""Identity: signup, login, verification, refresh, logout, sessions."""
from __future__ import annotations


def test_signup_creates_global_user_with_usr_prefix(client):
    r = client.post("/api/v1/auth/signup", json={"email": "new@example.com", "password": "correct-horse-battery"})
    assert r.status_code == 201
    body = r.json()
    assert body["id"].startswith("usr_")
    assert body["email"] == "new@example.com"
    assert body["email_verified"] is False


def test_duplicate_email_rejected(client):
    client.post("/api/v1/auth/signup", json={"email": "dupe@example.com", "password": "correct-horse-battery"})
    r = client.post("/api/v1/auth/signup", json={"email": "dupe@example.com", "password": "another-password-1"})
    assert r.status_code == 409
    assert r.json()["code"] == "EMAIL_ALREADY_REGISTERED"


def test_login_success(client):
    client.post("/api/v1/auth/signup", json={"email": "login@example.com", "password": "correct-horse-battery"})
    client.cookies.clear()
    r = client.post("/api/v1/auth/login", json={"email": "login@example.com", "password": "correct-horse-battery"})
    assert r.status_code == 200
    assert r.json()["email"] == "login@example.com"


def test_login_wrong_password_rejected(client):
    client.post("/api/v1/auth/signup", json={"email": "wrongpw@example.com", "password": "correct-horse-battery"})
    client.cookies.clear()
    r = client.post("/api/v1/auth/login", json={"email": "wrongpw@example.com", "password": "not-the-password"})
    assert r.status_code == 401
    assert r.json()["code"] == "INVALID_CREDENTIALS"


def test_login_unknown_email_same_error_as_wrong_password(client):
    r = client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "whatever12345"})
    assert r.status_code == 401
    assert r.json()["code"] == "INVALID_CREDENTIALS"


def test_disabled_account_cannot_login(client, db_session):
    from app.database.models import User

    client.post("/api/v1/auth/signup", json={"email": "disabled@example.com", "password": "correct-horse-battery"})
    user = db_session.query(User).filter_by(email="disabled@example.com").first()
    user.status = "disabled"
    db_session.commit()

    client.cookies.clear()
    r = client.post("/api/v1/auth/login", json={"email": "disabled@example.com", "password": "correct-horse-battery"})
    assert r.status_code == 403
    assert r.json()["code"] == "ACCOUNT_DISABLED"


def test_disabled_account_cannot_use_existing_session(client, db_session):
    from app.database.models import User

    client.post("/api/v1/auth/signup", json={"email": "disabled2@example.com", "password": "correct-horse-battery"})
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 200

    user = db_session.query(User).filter_by(email="disabled2@example.com").first()
    user.status = "disabled"
    db_session.commit()

    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401


def test_me_requires_authentication(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401
    assert r.json()["code"] == "AUTH_REQUIRED"


def test_email_verification_flow(client, db_session):
    from app.database.models import EmailVerificationToken, User

    client.post("/api/v1/auth/signup", json={"email": "verify@example.com", "password": "correct-horse-battery"})
    user = db_session.query(User).filter_by(email="verify@example.com").first()
    assert user.email_verified is False

    token_row = db_session.query(EmailVerificationToken).filter_by(user_id=user.id).first()
    # Recover the raw token the same way the dev email backend "sent" it -
    # by minting a fresh one through the service, since only the hash is stored.
    from datetime import timedelta
    from app.security.tokens import generate_hashed_token

    raw, token_hash, expires_at = generate_hashed_token(timedelta(hours=48))
    token_row.token_hash = token_hash
    token_row.expires_at = expires_at
    db_session.commit()

    r = client.post("/api/v1/auth/verify-email", json={"token": raw})
    assert r.status_code == 204

    db_session.refresh(user)
    assert user.email_verified is True


def test_verify_email_rejects_bad_token(client):
    r = client.post("/api/v1/auth/verify-email", json={"token": "not-a-real-token"})
    assert r.status_code == 400
    assert r.json()["code"] == "INVALID_TOKEN"


def test_refresh_rotates_session(client):
    client.post("/api/v1/auth/signup", json={"email": "refresh@example.com", "password": "correct-horse-battery"})
    old_refresh_cookie = client.cookies.get("plat_session_refresh")
    r = client.post("/api/v1/auth/refresh")
    assert r.status_code == 200
    new_refresh_cookie = client.cookies.get("plat_session_refresh")
    assert new_refresh_cookie != old_refresh_cookie


def test_logout_clears_session(client):
    client.post("/api/v1/auth/signup", json={"email": "logout@example.com", "password": "correct-horse-battery"})
    assert client.get("/api/v1/auth/me").status_code == 200
    r = client.post("/api/v1/auth/logout")
    assert r.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_logout_all_revokes_every_session(client, db_session):
    from app.database.models import RefreshToken, User

    client.post("/api/v1/auth/signup", json={"email": "logoutall@example.com", "password": "correct-horse-battery"})
    client.post("/api/v1/auth/refresh")  # a second active session row (rotated)
    user = db_session.query(User).filter_by(email="logoutall@example.com").first()

    r = client.post("/api/v1/auth/logout-all")
    assert r.status_code == 204

    active = db_session.query(RefreshToken).filter_by(user_id=user.id, revoked_at=None).count()
    assert active == 0


def test_change_password_requires_current_password(client):
    client.post("/api/v1/auth/signup", json={"email": "changepw@example.com", "password": "correct-horse-battery"})
    r = client.post("/api/v1/auth/change-password", json={"current_password": "wrong-one", "new_password": "brand-new-pass-1"})
    assert r.status_code == 401

    r = client.post("/api/v1/auth/change-password", json={"current_password": "correct-horse-battery", "new_password": "brand-new-pass-1"})
    assert r.status_code == 204

    client.cookies.clear()
    r = client.post("/api/v1/auth/login", json={"email": "changepw@example.com", "password": "brand-new-pass-1"})
    assert r.status_code == 200


def test_password_reset_revokes_existing_sessions(client, db_session):
    from datetime import timedelta
    from app.database.models import PasswordResetToken, User
    from app.security.tokens import generate_hashed_token

    client.post("/api/v1/auth/signup", json={"email": "reset@example.com", "password": "correct-horse-battery"})
    assert client.get("/api/v1/auth/me").status_code == 200

    user = db_session.query(User).filter_by(email="reset@example.com").first()
    raw, token_hash, expires_at = generate_hashed_token(timedelta(hours=1))
    db_session.add(PasswordResetToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
    db_session.commit()

    r = client.post("/api/v1/auth/reset-password", json={"token": raw, "new_password": "another-new-pass-1"})
    assert r.status_code == 204

    # The refresh token behind the old session is revoked immediately - a
    # stateless access-token JWT already issued still verifies until its own
    # short natural expiry (the same accepted trade-off Loady's own
    # `auth_service.reset_password` makes), but it can never be renewed again.
    refresh_r = client.post("/api/v1/auth/refresh")
    assert refresh_r.status_code == 400

    client.cookies.clear()
    r = client.post("/api/v1/auth/login", json={"email": "reset@example.com", "password": "another-new-pass-1"})
    assert r.status_code == 200


def test_sessions_listing_marks_current_session(client):
    client.post("/api/v1/auth/signup", json={"email": "sessions@example.com", "password": "correct-horse-battery"})
    r = client.get("/api/v1/auth/sessions")
    assert r.status_code == 200
    sessions = r.json()
    assert len(sessions) == 1
    assert sessions[0]["is_current"] is True
