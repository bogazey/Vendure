"""Append-only accountability trail for every privileged Platform Core
action (mission-brief section 18). Callers pass already-scrubbed
`before_state`/`after_state` dicts — this service never accepts a raw ORM
object, which structurally prevents an accidental secret/PII leak into the
audit log (there is no `__dict__` dump path available to a caller)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import AuditLog
from app.models.enums import AuditAction


def record(
    session: Session,
    actor_user_id: str | None,
    action: AuditAction,
    target_type: str,
    target_id: str | None,
    product_id: str | None = None,
    before_state: dict | None = None,
    after_state: dict | None = None,
    reason: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_user_id=actor_user_id,
        action=action.value,
        target_type=target_type,
        target_id=target_id,
        product_id=product_id,
        before_state=before_state,
        after_state=after_state,
        reason=reason,
    )
    session.add(entry)
    session.flush()
    return entry


def list_recent(session: Session, limit: int = 100, target_id: str | None = None) -> list[AuditLog]:
    query = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    if target_id:
        query = query.where(AuditLog.target_id == target_id)
    return list(session.execute(query).scalars().all())


def list_for_actor(session: Session, actor_user_id: str, actions: set[str] | None = None, limit: int = 50) -> list[AuditLog]:
    """Mission 6 (Phase 23): a user's own security-event feed - always
    scoped to `actor_user_id`, never a parameter another user's session
    could redirect to see someone else's history."""
    query = select(AuditLog).where(AuditLog.actor_user_id == actor_user_id).order_by(AuditLog.created_at.desc()).limit(limit)
    if actions:
        query = query.where(AuditLog.action.in_(actions))
    return list(session.execute(query).scalars().all())
