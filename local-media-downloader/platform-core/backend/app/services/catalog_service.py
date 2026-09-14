"""The Product Subscription Manager backend (Mission 6 continuation, TOP
PRIORITY): every product's plan catalog - plans, versions, and prices -
is fully independent. Nothing here assumes a fixed plan count, fixed
names, or a shared price list; every operation is scoped by `product_id`
and never reads/writes another product's rows.

Hierarchy implemented:

    Product -> Plan -> PlanVersion (capability snapshot)
                     -> Price (one of possibly several, per currency/interval)

Version-safety (mission brief: "existing users must retain the exact
entitlement/version/provider agreement they are currently assigned to
until explicitly changed"):

- `publish_plan_version` snapshots *current* `PlanEntitlement` values into
  an immutable `PlanVersion.capability_snapshot` and repoints
  `Plan.current_version_id` at it. Prior versions are never edited.
- A `Subscription`/`GiftedAccess`/`PromotionAccess`/legacy `Entitlement`
  row pins whichever `plan_version_id` was current *at grant time*
  (`entitlement_service`, `gift_service`, `subscription_service`,
  `promotion_service` all read `plan.current_version_id` when granting -
  see each module). `capability_service.resolve_effective_entitlements`
  prefers a pinned version's frozen snapshot over live `PlanEntitlement`
  rows whenever one is recorded.
- `Price` rows are never mutated for amount/currency/interval - "editing
  a price" is `retire_price` (old row) + `create_price` (new row);
  `Subscription.price_id` pins the original row forever.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import (
    Entitlement,
    GiftedAccess,
    Plan,
    PlanVersion,
    Price,
    Product,
    PromotionAccess,
    Subscription,
    User,
)
from app.models.enums import AuditAction
from app.services import audit_service, capability_service
from app.utils.exceptions import ConflictError, ForbiddenError, InvalidPlanError, NotFoundError

_MUTABLE_PLAN_FIELDS = {
    "name", "description", "status", "is_public", "sort_order", "upgrade_rank",
    "gifted_eligible", "trial_eligible",
}


# --- Plans -------------------------------------------------------------------


def create_plan(
    session: Session,
    admin: User,
    product_id: str,
    slug: str,
    name: str,
    *,
    description: str | None = None,
    sort_order: int = 0,
    upgrade_rank: int = 0,
    gifted_eligible: bool = True,
    trial_eligible: bool = True,
    is_public: bool = True,
) -> Plan:
    if session.get(Product, product_id) is None:
        raise NotFoundError(f"Unknown product '{product_id}'.")
    existing = session.execute(select(Plan).where(Plan.product_id == product_id, Plan.slug == slug)).scalars().first()
    if existing is not None:
        raise ConflictError(f"Product '{product_id}' already has a plan '{slug}'.")

    plan = Plan(
        product_id=product_id, slug=slug, name=name, description=description, sort_order=sort_order,
        upgrade_rank=upgrade_rank, gifted_eligible=gifted_eligible, trial_eligible=trial_eligible, is_public=is_public,
    )
    session.add(plan)
    session.flush()
    audit_service.record(
        session, admin.id, AuditAction.PLAN_ENTITLEMENT_SET, "plan", plan.id, product_id,
        after_state={"slug": slug, "name": name},
    )
    return plan


def get_plan_or_404(session: Session, plan_id: str) -> Plan:
    plan = session.get(Plan, plan_id)
    if plan is None:
        raise NotFoundError("Plan not found.")
    return plan


def list_plans(session: Session, product_id: str, *, include_archived: bool = True) -> list[Plan]:
    query = select(Plan).where(Plan.product_id == product_id).order_by(Plan.sort_order, Plan.upgrade_rank)
    if not include_archived:
        query = query.where(Plan.status == "active")
    return list(session.execute(query).scalars().all())


def update_plan(session: Session, admin: User, plan: Plan, **fields) -> Plan:
    unknown = set(fields) - _MUTABLE_PLAN_FIELDS
    if unknown:
        raise InvalidPlanError(f"Cannot set field(s) {sorted(unknown)} on a plan.")
    before = {key: getattr(plan, key) for key in fields}
    for key, value in fields.items():
        setattr(plan, key, value)
    session.flush()
    audit_service.record(
        session, admin.id, AuditAction.PLAN_ENTITLEMENT_SET, "plan", plan.id, plan.product_id,
        before_state=before, after_state=fields,
    )
    return plan


def archive_plan(session: Session, admin: User, plan: Plan) -> Plan:
    return update_plan(session, admin, plan, status="archived")


def activate_plan(session: Session, admin: User, plan: Plan) -> Plan:
    return update_plan(session, admin, plan, status="active")


# --- Plan versions -------------------------------------------------------------


def publish_plan_version(session: Session, admin: User, plan: Plan) -> PlanVersion:
    """Freezes the plan's CURRENT `PlanEntitlement` values into a new,
    immutable version and repoints `Plan.current_version_id` at it.
    Prior versions (and everything already pinned to them) are
    completely unaffected - this is what makes a later capability edit
    safe to make without retroactively changing an existing subscriber's
    contractual entitlement."""
    snapshot = capability_service.get_plan_capabilities(session, plan.id)
    latest_version_number = session.execute(
        select(func.max(PlanVersion.version_number)).where(PlanVersion.plan_id == plan.id)
    ).scalar_one_or_none() or 0

    version = PlanVersion(
        plan_id=plan.id, version_number=latest_version_number + 1, capability_snapshot=snapshot,
        status="published", created_by=admin.id, published_at=datetime.now(timezone.utc),
    )
    session.add(version)
    session.flush()
    plan.current_version_id = version.id
    session.flush()
    audit_service.record(
        session, admin.id, AuditAction.PLAN_ENTITLEMENT_SET, "plan_version", version.id, plan.product_id,
        after_state={"plan_id": plan.id, "version_number": version.version_number, "snapshot": snapshot},
    )
    return version


def list_plan_versions(session: Session, plan_id: str) -> list[PlanVersion]:
    return list(
        session.execute(
            select(PlanVersion).where(PlanVersion.plan_id == plan_id).order_by(PlanVersion.version_number.desc())
        ).scalars().all()
    )


def capabilities_for_grant(session: Session, plan: Plan) -> tuple[dict, str | None]:
    """What a NEW grant against this plan should be pinned to right now:
    `(capabilities, plan_version_id)`. If the plan has never been
    published, `plan_version_id` is `None` and callers fall back to the
    live (version-less) `PlanEntitlement` behavior that predates this
    feature - fully backward compatible."""
    if plan.current_version_id is None:
        return capability_service.get_plan_capabilities(session, plan.id), None
    version = session.get(PlanVersion, plan.current_version_id)
    if version is None:
        return capability_service.get_plan_capabilities(session, plan.id), None
    return dict(version.capability_snapshot), version.id


# --- Prices --------------------------------------------------------------------


def create_price(
    session: Session,
    admin: User,
    plan: Plan,
    *,
    provider: str,
    currency: str,
    amount_cents: int,
    interval: str,
    interval_count: int = 1,
    provider_price_id: str | None = None,
    is_public: bool = True,
    pin_current_version: bool = True,
) -> Price:
    price = Price(
        product_id=plan.product_id, plan_id=plan.id,
        plan_version_id=plan.current_version_id if pin_current_version else None,
        provider=provider, provider_price_id=provider_price_id, currency=currency.upper(),
        amount_cents=amount_cents, interval=interval, interval_count=interval_count, is_public=is_public,
    )
    session.add(price)
    session.flush()
    audit_service.record(
        session, admin.id, AuditAction.PLAN_ENTITLEMENT_SET, "price", price.id, plan.product_id,
        after_state={"plan_id": plan.id, "amount_cents": amount_cents, "currency": price.currency, "interval": interval},
    )
    return price


def retire_price(session: Session, admin: User, price: Price, reason: str | None = None) -> Price:
    """The ONLY way to "change" a price (mission brief: "disable old
    prices," "edit prices safely") - the row's amount/currency/interval
    are never mutated in place; retiring it and creating a new `Price`
    row is what guarantees a `Subscription` already pinned to this row
    keeps seeing its original agreement forever."""
    if not price.is_active:
        raise ConflictError("This price is already retired.")
    price.is_active = False
    price.retired_at = datetime.now(timezone.utc)
    session.flush()
    audit_service.record(
        session, admin.id, AuditAction.PLAN_ENTITLEMENT_SET, "price", price.id, price.product_id, reason=reason,
    )
    return price


def list_prices(session: Session, plan_id: str, *, only_active: bool = False) -> list[Price]:
    query = select(Price).where(Price.plan_id == plan_id).order_by(Price.created_at.desc())
    if only_active:
        query = query.where(Price.is_active.is_(True))
    return list(session.execute(query).scalars().all())


def update_price_visibility(session: Session, admin: User, price: Price, *, is_public: bool) -> Price:
    """The one field that IS safe to mutate in place - visibility is not
    part of the billing agreement a subscriber is holding, only whether
    new checkouts can see it."""
    price.is_public = is_public
    session.flush()
    audit_service.record(
        session, admin.id, AuditAction.PLAN_ENTITLEMENT_SET, "price", price.id, price.product_id,
        after_state={"is_public": is_public},
    )
    return price


# --- Stats (mission brief: subscriber counts, source distribution) -------------


def plan_stats(session: Session, plan_id: str) -> dict:
    plan = get_plan_or_404(session, plan_id)
    paid = session.execute(
        select(func.count(func.distinct(Subscription.id))).where(
            Subscription.product_id == plan.product_id, Subscription.status.in_(["active", "trialing", "past_due"])
        )
    ).scalar_one()
    gifted = session.execute(
        select(func.count(GiftedAccess.id)).where(GiftedAccess.plan_id == plan_id, GiftedAccess.status == "active")
    ).scalar_one()
    promotions = session.execute(
        select(func.count(PromotionAccess.id)).where(
            PromotionAccess.plan_id == plan_id, PromotionAccess.status == "active", PromotionAccess.kind == "promotion"
        )
    ).scalar_one()
    trials = session.execute(
        select(func.count(PromotionAccess.id)).where(
            PromotionAccess.plan_id == plan_id, PromotionAccess.status == "active", PromotionAccess.kind == "trial"
        )
    ).scalar_one()
    legacy = session.execute(
        select(func.count(Entitlement.id)).where(Entitlement.plan_id == plan_id, Entitlement.status == "active")
    ).scalar_one()
    return {
        "plan_id": plan_id, "paid_subscriptions": paid, "gifted": gifted,
        "promotions": promotions, "trials": trials, "legacy_entitlements": legacy,
    }
