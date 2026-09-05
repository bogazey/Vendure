"""Accountability trail for administrative actions - records who (an admin)
did what, to which user, and why. Deliberately separate from UsageEvent
(the credit-lifecycle ledger, an unrelated concern) and from BillingEvent
(Paddle's own webhook history) - this is specifically "what did an admin
do," queried by routes_admin.py for the Activity section and the Overview
dashboard's "recent admin actions" panel.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.commercial_models import AdminActionLog, User
from app.models.commercial_enums import AdminActionType


class AdminAuditService:
    def record(
        self,
        session: Session,
        admin: User,
        action: AdminActionType,
        target_user_id: str | None,
        details: dict | None = None,
    ) -> AdminActionLog:
        entry = AdminActionLog(
            admin_id=admin.id,
            action=action.value,
            target_user_id=target_user_id,
            details=details or {},
        )
        session.add(entry)
        session.flush()
        return entry

    def list_recent(
        self, session: Session, limit: int = 50, target_user_id: str | None = None
    ) -> list[AdminActionLog]:
        query = select(AdminActionLog).order_by(AdminActionLog.created_at.desc()).limit(limit)
        if target_user_id:
            query = query.where(AdminActionLog.target_user_id == target_user_id)
        return list(session.execute(query).scalars().all())


admin_audit_service = AdminAuditService()
