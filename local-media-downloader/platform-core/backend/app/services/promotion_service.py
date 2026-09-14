"""Promotions and trials (mission brief: "must remain distinct from
gifted/paid/bundle/internal"). One table (`PromotionAccess`), one `kind`
column - a marketing promotion and a product trial share an identical
lifecycle shape (time-boxed, always has an `expires_at`, never touches
billing), so two near-identical tables would be pure duplication.

Like `gift_service.py`, this module has no import of
`app.services.billing` anywhere - a promotion/trial structurally cannot
create a `PaymentRecord`."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Plan, PromotionAccess, User
from app.models.enums import AuditAction, EntitlementSource
from app.services import audit_service, catalog_service, entitlement_service
from app.utils.exceptions import ForbiddenError

_KIND_TO_LEGACY_SOURCE = {
    "promotion": EntitlementSource.PROMOTION,
    "trial": EntitlementSource.TRIAL,
}


def grant_promotion_or_trial(
    session: Session,
    admin: User,
    target: User,
    plan: Plan,
    kind: str,
    expires_at: datetime,
    *,
    source_code: str | None = None,
) -> PromotionAccess:
    if kind not in ("promotion", "trial"):
        raise ValueError(f"Unknown kind '{kind}' - must be 'promotion' or 'trial'.")
    if kind == "trial" and not plan.trial_eligible:
        raise ForbiddenError(f"Plan '{plan.slug}' does not allow trials.")

    capabilities, plan_version_id = catalog_service.capabilities_for_grant(session, plan)
    now = datetime.now(timezone.utc)
    grant = PromotionAccess(
        user_id=target.id, product_id=plan.product_id, plan_id=plan.id, plan_version_id=plan_version_id,
        kind=kind, source_code=source_code, granted_by=admin.id, starts_at=now, expires_at=expires_at, status="active",
    )
    session.add(grant)
    session.flush()
    audit_service.record(
        session, admin.id, AuditAction.GIFT_V2_GRANTED, "promotion_access", grant.id, plan.product_id,
        after_state={"kind": kind, "plan_id": plan.id, "expires_at": expires_at.isoformat()},
    )

    # Keep the legacy fast-path cache in sync, same paid-precedence guard
    # gift_service uses.
    existing = entitlement_service.get_active_entitlement(session, target.id, plan.product_id)
    if existing is not None and existing.source == EntitlementSource.PADDLE.value:
        raise ForbiddenError(
            "This user has an active paid entitlement in this product. "
            "A promotion/trial cannot silently replace it."
        )
    entitlement_service.grant_or_change(
        session, admin, target, plan.product_id, plan.slug, _KIND_TO_LEGACY_SOURCE[kind], expires_at, source_code,
    )
    return grant


def revoke(session: Session, admin: User, grant_id: str, reason: str | None = None) -> PromotionAccess:
    grant = session.get(PromotionAccess, grant_id)
    if grant is None:
        raise ForbiddenError("Promotion/trial grant not found.")
    grant.status = "revoked"
    session.flush()
    audit_service.record(session, admin.id, AuditAction.GIFT_V2_REVOKED, "promotion_access", grant.id, reason=reason)
    return grant


def sync_expired(session: Session, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    expired = session.execute(
        select(PromotionAccess).where(PromotionAccess.status == "active", PromotionAccess.expires_at <= now)
    ).scalars().all()
    for grant in expired:
        grant.status = "expired"
    session.flush()
    return len(expired)


def list_active(session: Session, user_id: str) -> list[PromotionAccess]:
    return list(
        session.execute(
            select(PromotionAccess).where(PromotionAccess.user_id == user_id, PromotionAccess.status == "active")
        ).scalars().all()
    )
