"""Gifted access v2 (mission-brief Phase 13): a dedicated, append-by-
convention history table (`GiftedAccess`), separate from the single
mutable `Entitlement` row `entitlement_service` maintains. This module
never imports anything from `app.services.billing` or writes a
`PaymentRecord` - a gift structurally cannot generate revenue because
nothing here has the ability to.

Every grant here also updates the legacy `Entitlement` cache (via
`entitlement_service.grant_or_change`, source=GIFTED) so existing callers
(`GET /api/v1/entitlements/me`, Loady's integration) see the gift
immediately - `GiftedAccess` is the source of truth for gift *history and
detail*; `Entitlement` remains the source of truth for the fast "is this
user entitled right now" question.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import GiftedAccess, Plan, User
from app.models.enums import AuditAction, EntitlementSource
from app.services import audit_service, entitlement_service
from app.utils.exceptions import ForbiddenError


def grant_gift(
    session: Session,
    admin: User,
    target: User,
    plan: Plan,
    reason: str | None,
    expires_at: datetime | None,
) -> GiftedAccess:
    if not plan.gifted_eligible:
        raise ForbiddenError(f"Plan '{plan.slug}' is not eligible for gifting.")

    from app.services import catalog_service

    _capabilities, plan_version_id = catalog_service.capabilities_for_grant(session, plan)

    now = datetime.now(timezone.utc)
    gift = GiftedAccess(
        user_id=target.id,
        product_id=plan.product_id,
        plan_id=plan.id,
        plan_version_id=plan_version_id,
        reason=reason,
        granted_by=admin.id,
        granted_at=now,
        starts_at=now,
        expires_at=expires_at,
        status="active",
    )
    session.add(gift)
    session.flush()
    audit_service.record(
        session, admin.id, AuditAction.GIFT_V2_GRANTED, "gifted_access", gift.id, plan.product_id,
        after_state={"plan_id": plan.id, "expires_at": expires_at.isoformat() if expires_at else None}, reason=reason,
    )

    # Keep the legacy fast-path cache in sync. Mirrors the existing
    # paid-precedence guard in routes_admin.py: never silently downgrade
    # an active paddle-sourced Entitlement via a gift.
    existing = entitlement_service.get_active_entitlement(session, target.id, plan.product_id)
    if existing is not None and existing.source == EntitlementSource.PADDLE.value:
        raise ForbiddenError(
            "This user has an active paid entitlement in this product. "
            "A gift cannot silently replace it - grant the gift, and let "
            "capability_service.resolve_effective_entitlements combine them, "
            "instead of overwriting the paid entitlement's plan."
        )
    entitlement_service.grant_or_change(
        session, admin, target, plan.product_id, plan.slug, EntitlementSource.GIFTED, expires_at, reason
    )
    return gift


def revoke_gift(session: Session, admin: User, gift_id: str, reason: str | None) -> GiftedAccess:
    gift = session.get(GiftedAccess, gift_id)
    if gift is None:
        raise ForbiddenError("Gift not found.")
    now = datetime.now(timezone.utc)
    gift.status = "revoked"
    gift.revoked_by = admin.id
    gift.revoked_at = now
    gift.revoke_reason = reason
    session.flush()
    audit_service.record(
        session, admin.id, AuditAction.GIFT_V2_REVOKED, "gifted_access", gift.id, gift.product_id, reason=reason,
    )

    # Only clear the legacy cache if no other gift/paid entitlement should
    # still be active - resolved by re-checking whether any other active
    # GiftedAccess row exists for this (user, product) before revoking the
    # legacy Entitlement, so revoking a stacked/duplicate gift never
    # revokes access a different, still-active gift also grants.
    remaining = session.execute(
        select(GiftedAccess).where(
            GiftedAccess.user_id == gift.user_id, GiftedAccess.product_id == gift.product_id,
            GiftedAccess.status == "active", GiftedAccess.id != gift.id,
        )
    ).scalars().first()
    if remaining is None:
        target = session.get(User, gift.user_id)
        existing = entitlement_service.get_active_entitlement(session, gift.user_id, gift.product_id)
        if existing is not None and existing.source in (
            EntitlementSource.GIFTED.value, EntitlementSource.INTERNAL.value, EntitlementSource.PROMOTION.value
        ):
            entitlement_service.revoke(session, admin, target, gift.product_id, reason)
    return gift


def list_active_gifts(session: Session, user_id: str | None = None) -> list[GiftedAccess]:
    query = select(GiftedAccess).where(GiftedAccess.status == "active").order_by(GiftedAccess.granted_at.desc())
    if user_id is not None:
        query = query.where(GiftedAccess.user_id == user_id)
    return list(session.execute(query).scalars().all())


def list_gift_history(session: Session, user_id: str) -> list[GiftedAccess]:
    return list(
        session.execute(
            select(GiftedAccess).where(GiftedAccess.user_id == user_id).order_by(GiftedAccess.granted_at.desc())
        ).scalars().all()
    )


def sync_expired_gifts(session: Session, now: datetime | None = None) -> int:
    """Hygiene sweep, safe to call from anywhere (an admin action, a test,
    a future scheduled job) - purely cosmetic bookkeeping. Correctness of
    "is this gift still active" never depends on this having run:
    `capability_service.resolve_effective_entitlements` and
    `_gift_contributes` both check `expires_at` independently at read
    time."""
    now = now or datetime.now(timezone.utc)
    expired = session.execute(
        select(GiftedAccess).where(
            GiftedAccess.status == "active", GiftedAccess.expires_at.is_not(None), GiftedAccess.expires_at <= now
        )
    ).scalars().all()
    for gift in expired:
        gift.status = "expired"
    session.flush()
    return len(expired)
