"""Mission 6 continuation (Phase 39): the safe-minimum account closure
lifecycle."""
from __future__ import annotations

from app.database.models import User
from app.services import account_closure_service, auth_service
from app.utils.exceptions import ConflictError, NotFoundError


def _signup_via_service(db_session, email: str) -> User:
    result = auth_service.auth_service.signup(db_session, email, "correct-horse-battery")
    db_session.commit()
    return result.user


def test_request_then_confirm_disables_account_and_revokes_sessions(db_session):
    user = _signup_via_service(db_session, "closure1@example.com")
    assert user.status == "active"
    assert len(auth_service.auth_service.list_active_sessions(db_session, user.id)) == 1

    request = account_closure_service.request_closure(db_session, user, "no longer needed")
    db_session.commit()
    assert request.status == "requested"

    confirmed = account_closure_service.confirm_closure(db_session, user, request.id)
    db_session.commit()
    assert confirmed.status == "closing"
    assert user.status == "disabled"
    assert auth_service.auth_service.list_active_sessions(db_session, user.id) == []


def test_cannot_request_a_second_closure_while_one_is_pending(db_session):
    user = _signup_via_service(db_session, "closure2@example.com")
    account_closure_service.request_closure(db_session, user, "first")
    db_session.commit()
    try:
        account_closure_service.request_closure(db_session, user, "second")
        assert False, "expected ConflictError"
    except ConflictError:
        pass


def test_cancel_before_confirmation(db_session):
    user = _signup_via_service(db_session, "closure3@example.com")
    request = account_closure_service.request_closure(db_session, user, "changed my mind coming")
    db_session.commit()

    canceled = account_closure_service.cancel_closure(db_session, user, request.id)
    db_session.commit()
    assert canceled.status == "canceled"
    assert user.status == "active"

    # A cancellation clears the way for a fresh request.
    new_request = account_closure_service.request_closure(db_session, user, "actually yes")
    db_session.commit()
    assert new_request.id != request.id


def test_cannot_confirm_someone_elses_closure_request(db_session):
    victim = _signup_via_service(db_session, "closure-victim@example.com")
    attacker = _signup_via_service(db_session, "closure-attacker@example.com")
    request = account_closure_service.request_closure(db_session, victim, "victim's own request")
    db_session.commit()

    try:
        account_closure_service.confirm_closure(db_session, attacker, request.id)
        assert False, "expected NotFoundError (IDOR-safe: not found, not forbidden, to avoid confirming existence)"
    except NotFoundError:
        pass
    assert victim.status == "active"  # untouched by the attacker's attempt


def test_cannot_confirm_an_already_closing_request_twice(db_session):
    user = _signup_via_service(db_session, "closure4@example.com")
    request = account_closure_service.request_closure(db_session, user, "once")
    db_session.commit()
    account_closure_service.confirm_closure(db_session, user, request.id)
    db_session.commit()
    try:
        account_closure_service.confirm_closure(db_session, user, request.id)
        assert False, "expected ConflictError"
    except ConflictError:
        pass


def test_http_closure_flow_end_to_end(client):
    signup = client.post("/api/v1/auth/signup", json={"email": "closure-http@example.com", "password": "correct-horse-battery"})
    assert signup.status_code == 201

    r = client.post("/api/v1/account/closure", json={"reason": "http e2e"})
    assert r.status_code == 200
    request_id = r.json()["id"]
    assert r.json()["status"] == "requested"

    status = client.get("/api/v1/account/closure")
    assert status.status_code == 200
    assert status.json()["id"] == request_id

    confirm = client.post(f"/api/v1/account/closure/{request_id}/confirm")
    assert confirm.status_code == 200
    assert confirm.json()["status"] == "closing"

    # The now-disabled account can no longer authenticate.
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 401
