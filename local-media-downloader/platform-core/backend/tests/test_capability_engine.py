"""Mission 6 (Phases 5-7): the data-driven capability registry and the
deterministic effective-entitlement resolution engine."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.database.models import (
    BundleAccess,
    BundleProductPlan,
    GiftedAccess,
    Product,
    Subscription,
    SubscriptionItem,
    User,
)
from app.models.enums import CapabilityValueType, EntitlementSource
from app.services import bundle_service, capability_service, entitlement_service
from app.utils.exceptions import InvalidPlanError


def _user(db_session, email: str) -> User:
    user = User(email=email, password_hash="x", email_verified=True)
    db_session.add(user)
    db_session.flush()
    return user


def _product(db_session, product_id: str) -> Product:
    if db_session.get(Product, product_id) is None:
        db_session.add(Product(id=product_id, name=product_id, domain=f"{product_id}.example", status="live"))
        db_session.flush()
    return db_session.get(Product, product_id)


def test_capability_value_type_validation(db_session):
    product = _product(db_session, "cap-product-a")
    plan = entitlement_service.get_or_create_plan(db_session, product.id, "pro", "Pro")
    capability_service.define_capability(db_session, product.id, "download.max_resolution", CapabilityValueType.INTEGER)
    db_session.commit()

    try:
        capability_service.set_plan_entitlement(db_session, plan, "download.max_resolution", "not-an-int")
        assert False, "expected InvalidPlanError"
    except InvalidPlanError:
        pass

    capability_service.set_plan_entitlement(db_session, plan, "download.max_resolution", 720)
    db_session.commit()
    assert capability_service.get_plan_capabilities(db_session, plan.id) == {"download.max_resolution": 720}


def test_enum_capability_rejects_value_outside_allowed_set(db_session):
    product = _product(db_session, "cap-product-b")
    plan = entitlement_service.get_or_create_plan(db_session, product.id, "pro", "Pro")
    capability_service.define_capability(
        db_session, product.id, "download.quality", CapabilityValueType.ENUM, allowed_values=["480p", "720p", "4k"]
    )
    db_session.commit()

    try:
        capability_service.set_plan_entitlement(db_session, plan, "download.quality", "8k")
        assert False, "expected InvalidPlanError"
    except InvalidPlanError:
        pass

    capability_service.set_plan_entitlement(db_session, plan, "download.quality", "4k")
    db_session.commit()
    assert capability_service.get_plan_capabilities(db_session, plan.id)["download.quality"] == "4k"


def test_resolution_merges_paid_and_gifted_and_preserves_both_sources(db_session):
    """The mission-brief's own worked example: paid Pro + gifted Creator ->
    effective Creator-level capability, with BOTH sources still visible."""
    admin = _user(db_session, "admin-cap1@example.com")
    target = _user(db_session, "user-cap1@example.com")
    product = _product(db_session, "cap-product-c")
    pro = entitlement_service.get_or_create_plan(db_session, product.id, "pro", "Pro")
    creator = entitlement_service.get_or_create_plan(db_session, product.id, "creator", "Creator")
    capability_service.define_capability(db_session, product.id, "ads.enabled", CapabilityValueType.BOOLEAN)
    capability_service.define_capability(db_session, product.id, "download.max_resolution", CapabilityValueType.INTEGER)
    db_session.flush()
    capability_service.set_plan_entitlement(db_session, pro, "ads.enabled", True)
    capability_service.set_plan_entitlement(db_session, pro, "download.max_resolution", 720)
    capability_service.set_plan_entitlement(db_session, creator, "ads.enabled", False)
    capability_service.set_plan_entitlement(db_session, creator, "download.max_resolution", capability_service.UNLIMITED)
    db_session.commit()

    entitlement_service.grant_or_change(db_session, admin, target, product.id, "pro", EntitlementSource.PADDLE, None, None)
    db_session.add(
        GiftedAccess(
            user_id=target.id, product_id=product.id, plan_id=creator.id, granted_by=admin.id,
            granted_at=datetime.now(timezone.utc), starts_at=datetime.now(timezone.utc), status="active",
        )
    )
    db_session.commit()

    result = capability_service.resolve_effective_entitlements(db_session, target.id, product.id)
    # boolean: OR across sources -> True (from paid pro) wins over False (gifted creator)
    assert result.capabilities["ads.enabled"] is True
    # integer: max/unlimited wins -> creator's UNLIMITED
    assert result.capabilities["download.max_resolution"] == capability_service.UNLIMITED
    # both contributing sources are preserved for audit/history, never dropped
    kinds = {s.kind for s in result.sources}
    assert "legacy_entitlement" in kinds or "gifted" in kinds
    assert len(result.sources) >= 2

    # Mission 7: `rank` (exposed via /api/v1/capabilities/me for a bearer
    # caller with no single "winning plan" concept of its own) must pick
    # the paid entitlement over the gift here, matching this exact
    # worked example's own stated tie-break philosophy - a real paid
    # subscription outranks a gift.
    winner = max(result.sources, key=lambda s: s.rank)
    assert winner.plan_slug == "pro"


def test_expired_gift_falls_away_automatically(db_session):
    admin = _user(db_session, "admin-cap2@example.com")
    target = _user(db_session, "user-cap2@example.com")
    product = _product(db_session, "cap-product-d")
    plan = entitlement_service.get_or_create_plan(db_session, product.id, "creator", "Creator")
    capability_service.define_capability(db_session, product.id, "ads.enabled", CapabilityValueType.BOOLEAN)
    capability_service.set_plan_entitlement(db_session, plan, "ads.enabled", False)
    db_session.add(
        GiftedAccess(
            user_id=target.id, product_id=product.id, plan_id=plan.id, granted_by=admin.id,
            granted_at=datetime.now(timezone.utc) - timedelta(days=10),
            starts_at=datetime.now(timezone.utc) - timedelta(days=10),
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            status="active",
        )
    )
    db_session.commit()

    result = capability_service.resolve_effective_entitlements(db_session, target.id, product.id)
    assert result.capabilities == {}
    assert result.sources == []


def test_canceled_subscription_still_active_through_period_end(db_session):
    admin = _user(db_session, "admin-cap3@example.com")
    target = _user(db_session, "user-cap3@example.com")
    product = _product(db_session, "cap-product-e")
    plan = entitlement_service.get_or_create_plan(db_session, product.id, "pro", "Pro")
    capability_service.define_capability(db_session, product.id, "ads.enabled", CapabilityValueType.BOOLEAN)
    capability_service.set_plan_entitlement(db_session, plan, "ads.enabled", True)
    db_session.commit()

    subscription = Subscription(
        user_id=target.id, product_id=product.id, provider="fake", provider_customer_ref="cust_1",
        provider_subscription_ref="sub_1", status="canceled",
        current_period_end=datetime.now(timezone.utc) + timedelta(days=5),
    )
    db_session.add(subscription)
    db_session.flush()
    db_session.add(SubscriptionItem(subscription_id=subscription.id, plan_id=plan.id))
    db_session.commit()

    result = capability_service.resolve_effective_entitlements(db_session, target.id, product.id)
    assert result.capabilities["ads.enabled"] is True

    # Once the period has actually lapsed, it must stop contributing.
    subscription.current_period_end = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.commit()
    result2 = capability_service.resolve_effective_entitlements(db_session, target.id, product.id)
    assert result2.capabilities == {}


def test_bundle_derived_access_expands_into_per_product_capability(db_session):
    admin = _user(db_session, "admin-cap4@example.com")
    target = _user(db_session, "user-cap4@example.com")
    product = _product(db_session, "cap-product-f")
    plan = entitlement_service.get_or_create_plan(db_session, product.id, "creator", "Creator")
    capability_service.define_capability(db_session, product.id, "ads.enabled", CapabilityValueType.BOOLEAN)
    capability_service.set_plan_entitlement(db_session, plan, "ads.enabled", False)
    bundle = bundle_service.create_bundle(db_session, admin, "creator-suite-cap4", "Creator Suite")
    bundle_service.add_product_plan(db_session, bundle, plan)
    db_session.commit()

    bundle_service.grant_bundle_access(db_session, admin, target, bundle, source="gifted")
    db_session.commit()

    result = capability_service.resolve_effective_entitlements(db_session, target.id, product.id)
    assert result.capabilities["ads.enabled"] is False
    assert any(s.kind == "bundle" for s in result.sources)
