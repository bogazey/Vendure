"""Central entitlement system (mission-brief section 9).

One generic `Entitlement` row represents access to a product-scoped plan,
regardless of how it was obtained — `source` is the only thing that
distinguishes a real Paddle-funded entitlement from a gifted one, and nothing
else in this module (or in `is_entitled`, which every product calls to
gate access) treats them any differently. The revenue/gifted distinction
lives entirely in *reporting* (see `analytics-equivalent` queries in
`routes_admin.py`'s overview endpoint and docs/platform/BILLING.md), never
in what access a user is actually granted.

Every grant/change/revoke is audited (mission-brief section 10) and, for
gifted/internal access specifically, is guaranteed to never touch anything
resembling a payment (mission-brief section 10: "must not generate
revenue... must not create Paddle subscriptions... must not create fake
transactions") — this module has no import of, or reference to, any
payment processor at all.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Entitlement, Plan, User
from app.models.enums import AuditAction, EntitlementSource, EntitlementStatus
from app.services import audit_service
from app.utils.exceptions import InvalidPlanError, NotFoundError

_GIFTED_SOURCES = {EntitlementSource.GIFTED.value, EntitlementSource.INTERNAL.value, EntitlementSource.PROMOTION.value}


def get_or_create_plan(session: Session, product_id: str, slug: str, name: str) -> Plan:
    plan = session.execute(
        select(Plan).where(Plan.product_id == product_id, Plan.slug == slug)
    ).scalars().first()
    if plan is not None:
        return plan
    plan = Plan(product_id=product_id, slug=slug, name=name)
    session.add(plan)
    session.flush()
    return plan


def get_plan(session: Session, product_id: str, slug: str) -> Plan:
    plan = session.execute(
        select(Plan).where(Plan.product_id == product_id, Plan.slug == slug)
    ).scalars().first()
    if plan is None:
        raise InvalidPlanError(f"Product '{product_id}' has no plan '{slug}'.")
    return plan


def _is_effectively_active(entitlement: Entitlement, now: datetime) -> bool:
    if entitlement.status != EntitlementStatus.ACTIVE.value:
        return False
    if entitlement.expires_at is not None and entitlement.expires_at < now:
        return False
    return True


def get_active_entitlement(session: Session, user_id: str, product_id: str) -> Entitlement | None:
    """The single source of truth every product/resource-server should
    call to answer "is this user entitled, right now, in this product" —
    wrong-product and expired rows are both structurally excluded here,
    not left to the caller to remember to check."""
    now = datetime.now(timezone.utc)
    candidates = session.execute(
        select(Entitlement)
        .where(Entitlement.user_id == user_id, Entitlement.product_id == product_id)
        .order_by(Entitlement.updated_at.desc())
    ).scalars().all()
    for entitlement in candidates:
        if _is_effectively_active(entitlement, now):
            return entitlement
    return None


def list_entitlements_for_user(session: Session, user_id: str) -> list[Entitlement]:
    return list(
        session.execute(select(Entitlement).where(Entitlement.user_id == user_id).order_by(Entitlement.created_at.desc()))
        .scalars()
        .all()
    )


def grant_or_change(
    session: Session,
    admin: User,
    target: User,
    product_id: str,
    plan_slug: str,
    source: EntitlementSource,
    expires_at: datetime | None,
    reason: str | None,
) -> Entitlement:
    plan = get_plan(session, product_id, plan_slug)
    now = datetime.now(timezone.utc)
    existing = get_active_entitlement(session, target.id, product_id)

    if source.value in _GIFTED_SOURCES:
        action_granted, action_changed = AuditAction.GIFTED_ACCESS_GRANTED, AuditAction.GIFTED_ACCESS_CHANGED
    else:
        action_granted, action_changed = AuditAction.ENTITLEMENT_GRANTED, AuditAction.ENTITLEMENT_CHANGED

    if existing is not None:
        before = {"plan_id": existing.plan_id, "source": existing.source, "status": existing.status}
        existing.plan_id = plan.id
        existing.source = source.value
        existing.expires_at = expires_at
        existing.granted_by = admin.id
        existing.reason = reason
        existing.status = EntitlementStatus.ACTIVE.value
        session.flush()
        after = {"plan_id": existing.plan_id, "source": existing.source, "status": existing.status}
        audit_service.record(
            session, admin.id, action_changed, "entitlement", existing.id, product_id,
            before_state=before, after_state=after, reason=reason,
        )
        return existing

    entitlement = Entitlement(
        user_id=target.id,
        product_id=product_id,
        plan_id=plan.id,
        source=source.value,
        status=EntitlementStatus.ACTIVE.value,
        starts_at=now,
        expires_at=expires_at,
        granted_by=admin.id,
        reason=reason,
    )
    session.add(entitlement)
    session.flush()
    audit_service.record(
        session, admin.id, action_granted, "entitlement", entitlement.id, product_id,
        before_state=None,
        after_state={"plan_id": entitlement.plan_id, "source": entitlement.source, "status": entitlement.status},
        reason=reason,
    )
    return entitlement


def revoke(session: Session, admin: User, target: User, product_id: str, reason: str | None) -> Entitlement | None:
    existing = get_active_entitlement(session, target.id, product_id)
    if existing is None:
        return None
    was_gifted = existing.source in _GIFTED_SOURCES
    before = {"plan_id": existing.plan_id, "source": existing.source, "status": existing.status}
    existing.status = EntitlementStatus.REVOKED.value
    existing.reason = reason
    session.flush()
    action = AuditAction.GIFTED_ACCESS_REVOKED if was_gifted else AuditAction.ENTITLEMENT_REVOKED
    audit_service.record(
        session, admin.id, action, "entitlement", existing.id, product_id,
        before_state=before, after_state={"status": existing.status}, reason=reason,
    )
    return existing
