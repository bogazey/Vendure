"""Mission 6 (Phases 21-23): single-session revoke, ecosystem-wide
sign-out-all (central session epoch + product OAuth refresh token
revocation), and the user-facing security-events feed."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.database.models import OAuthRefreshToken, User
from app.security.jwt_tokens import create_session_access_token, decode_session_access_token
from app.services import oidc_service
from app.services.auth_service import auth_service


def _signup(client, email: str) -> User:
    r = client.post("/api/v1/auth/signup", json={"email": email, "password": "correct-horse-battery"})
    assert r.status_code == 201
    return r


def test_sign_out_all_bumps_epoch_and_invalidates_an_already_issued_access_token(client, db_session):
    _signup(client, "epoch1@example.com")
    user = db_session.query(User).filter_by(email="epoch1@example.com").first()

    # Token minted with the epoch at the time of issuance (as the real
    # login/signup flow does via `_set_session_cookies`).
    old_token = create_session_access_token(user.id, user.security_epoch)
    payload = decode_session_access_token(old_token)
    assert payload["epoch"] == 1

    auth_service.logout_all_sessions(db_session, user.id)
    db_session.commit()
    db_session.refresh(user)
    assert user.security_epoch == 2

    # The route-level check happens in api/deps.py::get_optional_user by
    # comparing payload["epoch"] to the CURRENT user.security_epoch - here
    # we exercise that same comparison directly against a fresh DB read,
    # since a full HTTP round trip through the cookie jar would just
    # re-verify the identical logic `client` already goes through
    # elsewhere in this suite.
    fresh_user = db_session.get(User, user.id)
    assert payload["epoch"] != fresh_user.security_epoch


def test_sign_out_all_revokes_every_central_refresh_token(client, db_session):
    _signup(client, "epoch2@example.com")
    user = db_session.query(User).filter_by(email="epoch2@example.com").first()
    active_before = auth_service.list_active_sessions(db_session, user.id)
    assert len(active_before) == 1  # the signup itself issued one

    auth_service.logout_all_sessions(db_session, user.id)
    db_session.commit()

    active_after = auth_service.list_active_sessions(db_session, user.id)
    assert active_after == []


def test_sign_out_all_revokes_product_oauth_refresh_tokens_too(client, db_session):
    from app.database.models import Product

    _signup(client, "epoch3@example.com")
    user = db_session.query(User).filter_by(email="epoch3@example.com").first()
    product = Product(id="epoch-product", name="Epoch Product", domain="epoch.example", status="live")
    db_session.add(product)
    db_session.flush()
    reg_client, _secret = oidc_service.register_client(db_session, user, "epoch-oauth-client", "Epoch", product.id, [])
    db_session.add(
        OAuthRefreshToken(
            token_hash="deadbeef" * 8, client_id=reg_client.client_id, user_id=user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
    )
    db_session.commit()

    auth_service.logout_all_sessions(db_session, user.id)
    db_session.commit()

    tokens = db_session.query(OAuthRefreshToken).filter_by(user_id=user.id).all()
    assert all(t.revoked_at is not None for t in tokens)


def test_revoke_single_session_only_affects_that_session(client, db_session):
    _signup(client, "session1@example.com")
    user = db_session.query(User).filter_by(email="session1@example.com").first()
    second_raw = auth_service.reissue_session(db_session, user, remember_me=True)
    db_session.commit()

    sessions = auth_service.list_active_sessions(db_session, user.id)
    assert len(sessions) == 2
    target = sessions[0]

    revoked = auth_service.revoke_session(db_session, user, target.id)
    db_session.commit()
    assert revoked is True

    remaining = auth_service.list_active_sessions(db_session, user.id)
    assert len(remaining) == 1
    assert remaining[0].id != target.id


def test_revoke_session_is_idor_safe_across_users(client, db_session):
    """A user cannot revoke another user's session by guessing/enumerating
    its id - `revoke_session` scopes the lookup by (id, user_id) together,
    not id alone."""
    _signup(client, "victim@example.com")
    victim = db_session.query(User).filter_by(email="victim@example.com").first()
    victim_session = auth_service.list_active_sessions(db_session, victim.id)[0]

    attacker = User(email="attacker@example.com", password_hash="x", email_verified=True)
    db_session.add(attacker)
    db_session.commit()

    revoked = auth_service.revoke_session(db_session, attacker, victim_session.id)
    db_session.commit()
    assert revoked is False
    assert auth_service.list_active_sessions(db_session, victim.id)[0].id == victim_session.id


def test_change_password_with_revoke_other_sessions_keeps_caller_signed_in(client, db_session):
    _signup(client, "changepw1@example.com")

    resp = client.post("/api/v1/auth/change-password", json={
        "current_password": "correct-horse-battery", "new_password": "new-correct-horse-battery", "revoke_other_sessions": True,
    })
    assert resp.status_code == 204

    # The caller's OWN session (via the TestClient's cookie jar, refreshed
    # by the route) must still be authenticated.
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "changepw1@example.com"


def test_security_events_feed_shows_login_and_password_change(client, db_session):
    _signup(client, "secevents@example.com")
    client.post("/api/v1/auth/change-password", json={
        "current_password": "correct-horse-battery", "new_password": "another-correct-horse", "revoke_other_sessions": False,
    })

    r = client.get("/api/v1/me/security-events")
    assert r.status_code == 200
    actions = [e["action"] for e in r.json()]
    assert "user_signup" in actions
    assert "password_changed" in actions


def test_http_logout_all_rejects_a_previously_valid_still_unexpired_cookie(client, db_session):
    """End-to-end through the real cookie-auth dependency chain, not just
    the service function: a session_access cookie captured before
    logout-all is well-formed, correctly signed, and not yet expired -
    and must still be rejected, because its baked-in epoch no longer
    matches the user's current one."""
    _signup(client, "httpepoch@example.com")
    old_cookie = client.cookies.get("plat_session_access")
    assert old_cookie

    logout_resp = client.post("/api/v1/auth/logout-all")
    assert logout_resp.status_code == 204

    # Re-present the OLD (pre-logout-all) cookie explicitly, bypassing
    # whatever the TestClient's jar currently holds.
    r = client.get("/api/v1/auth/me", cookies={"plat_session_access": old_cookie})
    assert r.status_code == 401


def test_security_events_feed_never_shows_another_users_events(client, db_session):
    _signup(client, "secevents-a@example.com")
    a_events = client.get("/api/v1/me/security-events").json()

    client.post("/api/v1/auth/logout")
    _signup(client, "secevents-b@example.com")
    b_events = client.get("/api/v1/me/security-events").json()

    assert all(e["action"] != "" for e in a_events)
    # Simplest structural check: B's feed only ever contains as many
    # entries as B's own actions produced (signup) - it did not inherit A's.
    assert len(b_events) == 1
    assert b_events[0]["action"] == "user_signup"
