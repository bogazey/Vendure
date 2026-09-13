"""Data-driven capability registry + deterministic effective-entitlement
resolution (mission-brief Phases 5-7).

Two responsibilities, deliberately kept in one module because the second
is meaningless without the first:

1. **Registry** (`define_capability`, `set_plan_entitlement`,
   `get_plan_capabilities`) - a typed capability is declared once per
   product (`EntitlementDefinition`) and given a value per plan
   (`PlanEntitlement`). No product's capability set is ever a Python
   `if plan == "pro": ...` conditional here - see
   `docs/platform/ENTITLEMENT_ENGINE.md`.

2. **Resolution** (`resolve_effective_entitlements`) - the single function
   that answers "what can this user actually do in this product right
   now, and why" across every simultaneous access source (a still-active
   legacy `Entitlement` row, a `Subscription`, a `GiftedAccess` grant, or
   a `BundleAccess`). It is strictly additive to
   `entitlement_service.get_active_entitlement` - nothing here replaces
   that function or changes its behavior; existing callers (Loady's OIDC
   integration, `GET /api/v1/entitlements/me`) are unaffected.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import (
    Bundle,
    BundleAccess,
    BundleProductPlan,
    Entitlement,
    EntitlementDefinition,
    GiftedAccess,
    Plan,
    PlanEntitlement,
    Subscription,
    SubscriptionItem,
)
from app.models.enums import CapabilityValueType, EffectiveSourceKind
from app.utils.exceptions import InvalidPlanError

CapabilityValue = bool | int | str

# Sentinel used by integer capabilities to mean "unlimited" - the
# max-across-sources merge rule (see `_merge_integer`) treats it as
# strictly greater than any finite value.
UNLIMITED = -1

# Statuses that still contribute to effective entitlement for a
# Subscription. `past_due` is included deliberately: a provider retrying a
# failed payment does not instantly revoke access (mirrors common Paddle/
# Stripe dunning practice) - `paused`/`expired` do not contribute.
_SUBSCRIPTION_ACTIVE_STATUSES = {"trialing", "active", "past_due"}

# Tie-break rank for STRING/ENUM capabilities only (booleans OR together,
# integers take the max - see `_merge_capabilities`). Higher wins. A real
# paid subscription outranks a bundle, which outranks a gift, which
# outranks any legacy free-tier row - chosen so "which plan's exact
# string value wins" never surprises a paying user.
_TIE_BREAK_RANK: dict[str, int] = {
    "subscription": 100,
    "bundle": 80,
    "gifted": 60,
    "legacy:paddle": 90,
    "legacy:lifetime": 85,
    "legacy:bundle": 75,
    "legacy:gifted": 60,
    "legacy:promotion": 50,
    "legacy:trial": 40,
    "legacy:internal": 30,
    "legacy:free": 10,
}


# --- Registry ----------------------------------------------------------------


def define_capability(
    session: Session,
    product_id: str,
    key: str,
    value_type: CapabilityValueType,
    description: str | None = None,
    allowed_values: list[str] | None = None,
) -> EntitlementDefinition:
    existing = session.execute(
        select(EntitlementDefinition).where(
            EntitlementDefinition.product_id == product_id, EntitlementDefinition.key == key
        )
    ).scalars().first()
    if existing is not None:
        existing.value_type = value_type.value
        existing.description = description
        existing.allowed_values = allowed_values
        session.flush()
        return existing
    definition = EntitlementDefinition(
        product_id=product_id,
        key=key,
        value_type=value_type.value,
        description=description,
        allowed_values=allowed_values,
    )
    session.add(definition)
    session.flush()
    return definition


def list_capabilities(session: Session, product_id: str) -> list[EntitlementDefinition]:
    return list(
        session.execute(
            select(EntitlementDefinition).where(EntitlementDefinition.product_id == product_id).order_by(EntitlementDefinition.key)
        ).scalars().all()
    )


def _get_definition(session: Session, product_id: str, key: str) -> EntitlementDefinition:
    definition = session.execute(
        select(EntitlementDefinition).where(EntitlementDefinition.product_id == product_id, EntitlementDefinition.key == key)
    ).scalars().first()
    if definition is None:
        raise InvalidPlanError(f"Product '{product_id}' has no capability '{key}'. Define it first.")
    return definition


def set_plan_entitlement(session: Session, plan: Plan, key: str, value: CapabilityValue) -> PlanEntitlement:
    """Validates `value` against the capability's declared `value_type`
    before writing - this, not a DB CHECK constraint, is what keeps
    `PlanEntitlement` typed (mission-brief Phase 6)."""
    definition = _get_definition(session, plan.product_id, key)
    value_type = CapabilityValueType(definition.value_type)

    value_boolean: bool | None = None
    value_integer: int | None = None
    value_string: str | None = None

    if value_type == CapabilityValueType.BOOLEAN:
        if not isinstance(value, bool):
            raise InvalidPlanError(f"Capability '{key}' requires a boolean value.")
        value_boolean = value
    elif value_type == CapabilityValueType.INTEGER:
        if isinstance(value, bool) or not isinstance(value, int):
            raise InvalidPlanError(f"Capability '{key}' requires an integer value.")
        value_integer = value
    elif value_type == CapabilityValueType.STRING:
        if not isinstance(value, str):
            raise InvalidPlanError(f"Capability '{key}' requires a string value.")
        value_string = value
    else:  # ENUM
        if not isinstance(value, str):
            raise InvalidPlanError(f"Capability '{key}' requires a string value.")
        allowed = definition.allowed_values or []
        if value not in allowed:
            raise InvalidPlanError(f"'{value}' is not one of the allowed values for '{key}': {allowed}.")
        value_string = value

    existing = session.execute(
        select(PlanEntitlement).where(
            PlanEntitlement.plan_id == plan.id, PlanEntitlement.entitlement_definition_id == definition.id
        )
    ).scalars().first()
    if existing is not None:
        existing.value_boolean = value_boolean
        existing.value_integer = value_integer
        existing.value_string = value_string
        session.flush()
        return existing

    row = PlanEntitlement(
        plan_id=plan.id,
        entitlement_definition_id=definition.id,
        value_boolean=value_boolean,
        value_integer=value_integer,
        value_string=value_string,
    )
    session.add(row)
    session.flush()
    return row


def _typed_value(row: PlanEntitlement, value_type: str) -> CapabilityValue | None:
    if value_type == CapabilityValueType.BOOLEAN.value:
        return row.value_boolean
    if value_type == CapabilityValueType.INTEGER.value:
        return row.value_integer
    return row.value_string


def get_plan_capabilities(session: Session, plan_id: str) -> dict[str, CapabilityValue]:
    rows = session.execute(
        select(PlanEntitlement, EntitlementDefinition)
        .join(EntitlementDefinition, PlanEntitlement.entitlement_definition_id == EntitlementDefinition.id)
        .where(PlanEntitlement.plan_id == plan_id)
    ).all()
    result: dict[str, CapabilityValue] = {}
    for plan_entitlement, definition in rows:
        value = _typed_value(plan_entitlement, definition.value_type)
        if value is not None:
            result[definition.key] = value
    return result


# --- Effective-entitlement resolution -----------------------------------------


@dataclass
class EffectiveSource:
    kind: str
    plan_id: str
    plan_slug: str
    status: str
    expires_at: datetime | None


@dataclass
class EffectiveEntitlementResult:
    product_id: str
    capabilities: dict[str, CapabilityValue] = field(default_factory=dict)
    sources: list[EffectiveSource] = field(default_factory=list)


def _subscription_contributes(subscription: Subscription, now: datetime) -> bool:
    if subscription.status in _SUBSCRIPTION_ACTIVE_STATUSES:
        return True
    # Cancelled-but-not-yet-lapsed: access continues through the paid
    # period end (mission-brief Phase 7: "follow
    # entitlement-through-period-end rules").
    if subscription.status == "canceled" and subscription.current_period_end is not None:
        return subscription.current_period_end > now
    return False


def _gift_contributes(gift: GiftedAccess, now: datetime) -> bool:
    if gift.status != "active":
        return False
    if gift.starts_at > now:
        return False
    if gift.expires_at is not None and gift.expires_at <= now:
        return False
    return True


def _bundle_access_contributes(access: BundleAccess, now: datetime) -> bool:
    if access.status != "active":
        return False
    if access.expires_at is not None and access.expires_at <= now:
        return False
    return True


def _merge_boolean(current: bool | None, candidate: bool) -> bool:
    return bool(current) or candidate


def _merge_integer(current: int | None, candidate: int) -> int:
    if current is None:
        return candidate
    if current == UNLIMITED or candidate == UNLIMITED:
        return UNLIMITED
    return max(current, candidate)


def resolve_effective_entitlements(
    session: Session, user_id: str, product_id: str, now: datetime | None = None
) -> EffectiveEntitlementResult:
    """Deterministic multi-source resolution (mission-brief Phase 7).
    Read-only: never mutates `Entitlement`/`GiftedAccess`/`Subscription`/
    `BundleAccess` rows, and never deletes or hides a losing source - every
    row that contributed is returned in `.sources`, satisfying "preserve
    BOTH sources for audit/history" even when only one plan's string/enum
    values "win" the merge."""
    now = now or datetime.now(timezone.utc)
    result = EffectiveEntitlementResult(product_id=product_id)

    candidates: list[tuple[str, str, Plan]] = []  # (tier_key, status, plan)

    # 1. Legacy Entitlement (paid/free/gifted/trial/etc. not yet migrated
    # onto a dedicated V2 table).
    legacy = session.execute(
        select(Entitlement)
        .where(Entitlement.user_id == user_id, Entitlement.product_id == product_id, Entitlement.status == "active")
        .order_by(Entitlement.updated_at.desc())
    ).scalars().first()
    if legacy is not None and (legacy.expires_at is None or legacy.expires_at > now):
        plan = session.get(Plan, legacy.plan_id)
        if plan is not None:
            tier = f"legacy:{legacy.source}"
            candidates.append((tier, legacy.status, plan))
            result.sources.append(
                EffectiveSource(
                    kind=EffectiveSourceKind.LEGACY_ENTITLEMENT.value,
                    plan_id=plan.id, plan_slug=plan.slug, status=legacy.status, expires_at=legacy.expires_at,
                )
            )

    # 2. Subscriptions (provider-neutral).
    subscriptions = session.execute(
        select(Subscription).where(Subscription.user_id == user_id, Subscription.product_id == product_id)
    ).scalars().all()
    for subscription in subscriptions:
        if not _subscription_contributes(subscription, now):
            continue
        items = session.execute(
            select(SubscriptionItem).where(SubscriptionItem.subscription_id == subscription.id)
        ).scalars().all()
        for item in items:
            plan = session.get(Plan, item.plan_id)
            if plan is None:
                continue
            candidates.append(("subscription", subscription.status, plan))
            result.sources.append(
                EffectiveSource(
                    kind=EffectiveSourceKind.SUBSCRIPTION.value,
                    plan_id=plan.id, plan_slug=plan.slug, status=subscription.status,
                    expires_at=subscription.current_period_end,
                )
            )

    # 3. Gifted access v2.
    gifts = session.execute(
        select(GiftedAccess).where(GiftedAccess.user_id == user_id, GiftedAccess.product_id == product_id)
    ).scalars().all()
    for gift in gifts:
        if not _gift_contributes(gift, now):
            continue
        plan = session.get(Plan, gift.plan_id)
        if plan is None:
            continue
        candidates.append(("gifted", gift.status, plan))
        result.sources.append(
            EffectiveSource(
                kind=EffectiveSourceKind.GIFTED.value,
                plan_id=plan.id, plan_slug=plan.slug, status=gift.status, expires_at=gift.expires_at,
            )
        )

    # 4. Bundle-derived access.
    bundle_accesses = session.execute(
        select(BundleAccess).where(BundleAccess.user_id == user_id)
    ).scalars().all()
    for access in bundle_accesses:
        if not _bundle_access_contributes(access, now):
            continue
        bpp = session.execute(
            select(BundleProductPlan).where(
                BundleProductPlan.bundle_id == access.bundle_id, BundleProductPlan.product_id == product_id
            )
        ).scalars().first()
        if bpp is None:
            continue
        plan = session.get(Plan, bpp.plan_id)
        if plan is None:
            continue
        candidates.append(("bundle", access.status, plan))
        result.sources.append(
            EffectiveSource(
                kind=EffectiveSourceKind.BUNDLE.value,
                plan_id=plan.id, plan_slug=plan.slug, status=access.status, expires_at=access.expires_at,
            )
        )

    # --- Merge capabilities across every contributing plan ---
    best_string_rank: dict[str, int] = {}
    for tier, _status, plan in candidates:
        rank = _TIE_BREAK_RANK.get(tier, 0)
        plan_caps = get_plan_capabilities(session, plan.id)
        for key, value in plan_caps.items():
            if isinstance(value, bool):
                result.capabilities[key] = _merge_boolean(result.capabilities.get(key), value)  # type: ignore[arg-type]
            elif isinstance(value, int):
                result.capabilities[key] = _merge_integer(result.capabilities.get(key), value)  # type: ignore[arg-type]
            else:
                if key not in best_string_rank or rank > best_string_rank[key]:
                    result.capabilities[key] = value
                    best_string_rank[key] = rank

    return result
