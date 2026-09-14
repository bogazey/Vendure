"""Account closure - the safe minimum lifecycle (mission-brief Phase 39:
"do not implement irreversible deletion casually"). This module can
disable a central account and record why; it CANNOT and does not attempt
to delete a single row, anonymize PII, or notify a product to purge its
own operational data - all of that is explicitly future work, documented
as unsupported in `docs/platform/ACCOUNT_DELETION.md`.

Lifecycle: requested -> confirmed -> closing -> (closed | canceled at any
point before closing takes effect).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import AccountClosureRequest, User
from app.models.enums import AuditAction
from app.services import audit_service, auth_service
from app.utils.exceptions import ConflictError, NotFoundError


def _latest_open_request(session: Session, user_id: str) -> AccountClosureRequest | None:
    return session.execute(
        select(AccountClosureRequest)
        .where(AccountClosureRequest.user_id == user_id, AccountClosureRequest.status.in_(["requested", "confirmed"]))
        .order_by(AccountClosureRequest.requested_at.desc())
    ).scalars().first()


def request_closure(session: Session, user: User, reason: str | None) -> AccountClosureRequest:
    if _latest_open_request(session, user.id) is not None:
        raise ConflictError("An account closure request is already pending for this account.")
    request = AccountClosureRequest(user_id=user.id, status="requested", reason=reason)
    session.add(request)
    session.flush()
    audit_service.record(session, user.id, AuditAction.ALL_SESSIONS_REVOKED, "account_closure_request", request.id, reason=reason)
    return request


def confirm_closure(session: Session, user: User, request_id: str) -> AccountClosureRequest:
    """Confirmation is the point of no return in THIS mission's supported
    scope: the account is disabled and every session is revoked
    immediately. No data is deleted - "closing" is a terminal, reversible
    (by a super_admin re-enabling the account) safe state, not a deletion."""
    request = session.get(AccountClosureRequest, request_id)
    if request is None or request.user_id != user.id:
        raise NotFoundError("Closure request not found.")
    if request.status != "requested":
        raise ConflictError(f"Cannot confirm a closure request in status '{request.status}'.")

    now = datetime.now(timezone.utc)
    request.status = "closing"
    request.confirmed_at = now
    user.status = "disabled"
    auth_service.auth_service.logout_all_sessions(session, user.id)
    session.flush()
    audit_service.record(
        session, user.id, AuditAction.ALL_SESSIONS_REVOKED, "account_closure_request", request.id,
        after_state={"status": "closing"},
    )
    return request


def cancel_closure(session: Session, user: User, request_id: str) -> AccountClosureRequest:
    request = session.get(AccountClosureRequest, request_id)
    if request is None or request.user_id != user.id:
        raise NotFoundError("Closure request not found.")
    if request.status not in ("requested", "confirmed"):
        raise ConflictError(f"Cannot cancel a closure request in status '{request.status}'.")
    request.status = "canceled"
    request.canceled_at = datetime.now(timezone.utc)
    session.flush()
    return request


def get_status(session: Session, user_id: str) -> AccountClosureRequest | None:
    return session.execute(
        select(AccountClosureRequest).where(AccountClosureRequest.user_id == user_id).order_by(AccountClosureRequest.requested_at.desc())
    ).scalars().first()
