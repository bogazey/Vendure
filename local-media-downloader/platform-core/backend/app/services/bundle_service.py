"""Ecosystem bundles (mission-brief Phases 15-16). A bundle purchase/gift
grants access across multiple products at once via `BundleAccess` +
`BundleProductPlan`; `capability_service.resolve_effective_entitlements`
is what expands a `BundleAccess` row into per-product capabilities - this
module only manages the bundle's own lifecycle (create, activate, expire,
revoke) and never touches another product's independent `Subscription` or
`GiftedAccess` row, which is what guarantees "a user's independent
subscription survives a bundle change" (Phase 16) - there is structurally
no code path here that reads or writes those tables."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Bundle, BundleAccess, BundleProductPlan, Plan, User
from app.models.enums import AuditAction
from app.services import audit_service
from app.utils.exceptions import ConflictError, NotFoundError


def create_bundle(session: Session, admin: User, slug: str, name: str) -> Bundle:
    existing = session.execute(select(Bundle).where(Bundle.slug == slug)).scalars().first()
    if existing is not None:
        raise ConflictError(f"Bundle '{slug}' already exists.")
    bundle = Bundle(slug=slug, name=name, status="active")
    session.add(bundle)
    session.flush()
    audit_service.record(session, admin.id, AuditAction.BUNDLE_CREATED, "bundle", bundle.id, after_state={"slug": slug, "name": name})
    return bundle


def get_bundle(session: Session, bundle_id: str) -> Bundle:
    bundle = session.get(Bundle, bundle_id)
    if bundle is None:
        raise NotFoundError(f"Unknown bundle '{bundle_id}'.")
    return bundle


def add_product_plan(session: Session, bundle: Bundle, plan: Plan) -> BundleProductPlan:
    existing = session.execute(
        select(BundleProductPlan).where(
            BundleProductPlan.bundle_id == bundle.id, BundleProductPlan.product_id == plan.product_id
        )
    ).scalars().first()
    if existing is not None:
        existing.plan_id = plan.id
        session.flush()
        return existing
    row = BundleProductPlan(bundle_id=bundle.id, product_id=plan.product_id, plan_id=plan.id)
    session.add(row)
    session.flush()
    return row


def list_bundle_products(session: Session, bundle_id: str) -> list[BundleProductPlan]:
    return list(session.execute(select(BundleProductPlan).where(BundleProductPlan.bundle_id == bundle_id)).scalars().all())


def grant_bundle_access(
    session: Session,
    admin: User,
    target: User,
    bundle: Bundle,
    source: str,
    expires_at: datetime | None = None,
    subscription_id: str | None = None,
) -> BundleAccess:
    now = datetime.now(timezone.utc)
    existing = session.execute(
        select(BundleAccess).where(BundleAccess.user_id == target.id, BundleAccess.bundle_id == bundle.id)
    ).scalars().first()
    if existing is not None:
        # Re-activate/upgrade in place, matching entitlement_service's
        # own idempotency precedent (one live row per user+bundle).
        existing.source = source
        existing.subscription_id = subscription_id
        existing.status = "active"
        existing.starts_at = now
        existing.expires_at = expires_at
        session.flush()
        audit_service.record(
            session, admin.id, AuditAction.BUNDLE_ACCESS_GRANTED, "bundle_access", existing.id,
            after_state={"bundle_id": bundle.id, "source": source},
        )
        return existing

    access = BundleAccess(
        user_id=target.id, bundle_id=bundle.id, source=source, subscription_id=subscription_id,
        status="active", starts_at=now, expires_at=expires_at,
    )
    session.add(access)
    session.flush()
    audit_service.record(
        session, admin.id, AuditAction.BUNDLE_ACCESS_GRANTED, "bundle_access", access.id,
        after_state={"bundle_id": bundle.id, "source": source},
    )
    return access


def revoke_bundle_access(session: Session, admin: User, access_id: str, reason: str | None = None) -> BundleAccess:
    access = session.get(BundleAccess, access_id)
    if access is None:
        raise NotFoundError("Bundle access not found.")
    access.status = "revoked"
    session.flush()
    audit_service.record(
        session, admin.id, AuditAction.BUNDLE_ACCESS_REVOKED, "bundle_access", access.id, reason=reason,
    )
    return access


def expire_bundle_accesses(session: Session, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    expired = session.execute(
        select(BundleAccess).where(
            BundleAccess.status == "active", BundleAccess.expires_at.is_not(None), BundleAccess.expires_at <= now
        )
    ).scalars().all()
    for access in expired:
        access.status = "expired"
    session.flush()
    return len(expired)


def list_user_bundle_access(session: Session, user_id: str) -> list[BundleAccess]:
    return list(session.execute(select(BundleAccess).where(BundleAccess.user_id == user_id)).scalars().all())
