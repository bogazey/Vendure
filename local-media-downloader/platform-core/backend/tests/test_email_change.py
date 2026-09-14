"""Mission 6 continuation (Phase 19): verified email-change flow -
pending_new_email until confirmed, never immediately overwriting a
verified login email."""
from __future__ import annotations

from app.database.models import EmailChangeToken, User
from app.services import auth_service
from app.services.auth_service import auth_service as auth
from app.utils.exceptions import EmailAlreadyRegisteredError, InvalidTokenError


def _signup(db_session, email: str) -> User:
    result = auth.signup(db_session, email, "correct-horse-battery")
    db_session.commit()
    return result.user


def test_request_does_not_change_email_immediately(db_session):
    user = _signup(db_session, "before-change@example.com")
    auth.request_email_change(db_session, user, "after-change@example.com")
    db_session.commit()

    assert user.email == "before-change@example.com"
    assert user.pending_new_email == "after-change@example.com"


def test_confirming_the_token_actually_changes_the_email(db_session):
    from sqlalchemy import select
    from app.security.tokens import hash_token

    user = _signup(db_session, "confirm-before@example.com")
    auth.request_email_change(db_session, user, "confirm-after@example.com")
    db_session.commit()

    # Recover the raw token the way a real click-through link would carry
    # it - by intercepting at the token layer, since email_service only
    # logs in this mission (no real mail is ever sent).
    token_record = db_session.execute(select(EmailChangeToken).where(EmailChangeToken.user_id == user.id)).scalars().first()
    assert token_record is not None

    # Re-derive a raw token deterministically for the test: generate a
    # fresh one and overwrite the stored hash, since generate_hashed_token
    # doesn't return a way to recover the original from the DB row alone
    # (correctly - it's one-way hashed).
    from app.security.tokens import generate_hashed_token
    from datetime import timedelta

    raw, new_hash, expires_at = generate_hashed_token(timedelta(hours=48))
    token_record.token_hash = new_hash
    token_record.expires_at = expires_at
    db_session.commit()

    confirmed_user = auth.confirm_email_change(db_session, raw)
    db_session.commit()

    assert confirmed_user.email == "confirm-after@example.com"
    assert confirmed_user.pending_new_email is None


def test_confirming_twice_fails(db_session):
    from sqlalchemy import select
    from app.security.tokens import generate_hashed_token
    from datetime import timedelta

    user = _signup(db_session, "twice-before@example.com")
    auth.request_email_change(db_session, user, "twice-after@example.com")
    db_session.commit()
    token_record = db_session.execute(select(EmailChangeToken).where(EmailChangeToken.user_id == user.id)).scalars().first()
    raw, new_hash, expires_at = generate_hashed_token(timedelta(hours=48))
    token_record.token_hash = new_hash
    token_record.expires_at = expires_at
    db_session.commit()

    auth.confirm_email_change(db_session, raw)
    db_session.commit()

    try:
        auth.confirm_email_change(db_session, raw)
        assert False, "expected InvalidTokenError on reuse"
    except InvalidTokenError:
        pass


def test_cannot_confirm_into_an_email_already_taken_by_someone_else(db_session):
    from sqlalchemy import select
    from app.security.tokens import generate_hashed_token
    from datetime import timedelta

    victim = _signup(db_session, "already-taken@example.com")
    attacker = _signup(db_session, "attacker-before@example.com")
    auth.request_email_change(db_session, attacker, "already-taken@example.com")
    db_session.commit()

    token_record = db_session.execute(select(EmailChangeToken).where(EmailChangeToken.user_id == attacker.id)).scalars().first()
    raw, new_hash, expires_at = generate_hashed_token(timedelta(hours=48))
    token_record.token_hash = new_hash
    token_record.expires_at = expires_at
    db_session.commit()

    try:
        auth.confirm_email_change(db_session, raw)
        assert False, "expected EmailAlreadyRegisteredError"
    except EmailAlreadyRegisteredError:
        pass
    assert attacker.email == "attacker-before@example.com"  # unchanged


def test_http_end_to_end_request_email_change(client):
    signup = client.post("/api/v1/auth/signup", json={"email": "http-change@example.com", "password": "correct-horse-battery"})
    assert signup.status_code == 201

    r = client.post("/api/v1/auth/request-email-change", json={"new_email": "http-change-new@example.com"})
    assert r.status_code == 204

    me = client.get("/api/v1/auth/me")
    assert me.json()["email"] == "http-change@example.com"  # unchanged until confirmed
    assert me.json()["pending_new_email"] == "http-change-new@example.com"
