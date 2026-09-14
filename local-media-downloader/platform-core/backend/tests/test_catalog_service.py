"""Mission 6 continuation (TOP PRIORITY): the Product Subscription
Manager backend - independent per-product catalogs, plan versioning, and
version-safe pricing."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.database.models import GiftedAccess, Product, Subscription, SubscriptionItem, User
from app.models.enums import CapabilityValueType, EntitlementSource
from app.services import capability_service, catalog_service, entitlement_service, gift_service
from app.utils.exceptions import ConflictError, ForbiddenError, InvalidPlanError


def _admin(db_session, email: str) -> User:
    user = User(email=email, password_hash="x", email_verified=True)
    db_session.add(user)
    db_session.flush()
    return user


def _product(db_session, product_id: str) -> Product:
    if db_session.get(Product, product_id) is None:
        db_session.add(Product(id=product_id, name=product_id, domain=f"{product_id}.example", status="live"))
        db_session.flush()
    return db_session.get(Product, product_id)


# --- Independent catalogs ------------------------------------------------------


def test_two_products_can_have_completely_different_plan_counts_and_names(db_session):
    admin = _admin(db_session, "admin-cat1@example.com")
    loady = _product(db_session, "cat-loady")
    gamey = _product(db_session, "cat-gamey")

    catalog_service.create_plan(db_session, admin, loady.id, "free", "Free")
    catalog_service.create_plan(db_session, admin, loady.id, "pro", "Pro")
    catalog_service.create_plan(db_session, admin, loady.id, "creator", "Creator")

    catalog_service.create_plan(db_session, admin, gamey.id, "free", "Free")
    catalog_service.create_plan(db_session, admin, gamey.id, "gamer-plus", "Gamer+")

    loady_plans = catalog_service.list_plans(db_session, loady.id)
    gamey_plans = catalog_service.list_plans(db_session, gamey.id)
    assert len(loady_plans) == 3
    assert len(gamey_plans) == 2
    assert {p.slug for p in gamey_plans} == {"free", "gamer-plus"}


def test_duplicate_plan_slug_within_a_product_rejected(db_session):
    admin = _admin(db_session, "admin-cat2@example.com")
    product = _product(db_session, "cat-dup")
    catalog_service.create_plan(db_session, admin, product.id, "pro", "Pro")
    try:
        catalog_service.create_plan(db_session, admin, product.id, "pro", "Pro Again")
        assert False, "expected ConflictError"
    except ConflictError:
        pass


def test_same_slug_is_fine_across_different_products(db_session):
    admin = _admin(db_session, "admin-cat3@example.com")
    a = _product(db_session, "cat-product-a")
    b = _product(db_session, "cat-product-b")
    plan_a = catalog_service.create_plan(db_session, admin, a.id, "pro", "Pro")
    plan_b = catalog_service.create_plan(db_session, admin, b.id, "pro", "Pro")
    assert plan_a.id != plan_b.id


def test_archive_and_activate_plan(db_session):
    admin = _admin(db_session, "admin-cat4@example.com")
    product = _product(db_session, "cat-archive")
    plan = catalog_service.create_plan(db_session, admin, product.id, "legacy", "Legacy")
    catalog_service.archive_plan(db_session, admin, plan)
    assert plan.status == "archived"
    catalog_service.activate_plan(db_session, admin, plan)
    assert plan.status == "active"


def test_update_plan_rejects_unknown_field(db_session):
    admin = _admin(db_session, "admin-cat5@example.com")
    product = _product(db_session, "cat-badfield")
    plan = catalog_service.create_plan(db_session, admin, product.id, "pro", "Pro")
    try:
        catalog_service.update_plan(db_session, admin, plan, product_id="hijacked")
        assert False, "expected InvalidPlanError"
    except InvalidPlanError:
        pass


# --- Plan versioning: historical stability -------------------------------------


def test_publishing_a_new_version_does_not_retroactively_change_an_existing_grant(db_session):
    """The mission's own worked example, generalized: a user granted
    while the plan had 720p access must keep 720p even after the plan is
    later upgraded to unlimited - only NEW grants see the new version."""
    admin = _admin(db_session, "admin-ver1@example.com")
    early_user = _admin(db_session, "early-ver1@example.com")
    late_user = _admin(db_session, "late-ver1@example.com")
    product = _product(db_session, "ver-product-a")
    plan = catalog_service.create_plan(db_session, admin, product.id, "pro", "Pro")
    capability_service.define_capability(db_session, product.id, "download.max_resolution", CapabilityValueType.INTEGER)
    capability_service.set_plan_entitlement(db_session, plan, "download.max_resolution", 720)
    v1 = catalog_service.publish_plan_version(db_session, admin, plan)
    assert v1.version_number == 1
    assert v1.capability_snapshot == {"download.max_resolution": 720}

    entitlement_service.grant_or_change(db_session, admin, early_user, product.id, "pro", EntitlementSource.PADDLE, None, None)
    db_session.commit()

    # Now the catalog changes: Pro becomes unlimited.
    capability_service.set_plan_entitlement(db_session, plan, "download.max_resolution", capability_service.UNLIMITED)
    v2 = catalog_service.publish_plan_version(db_session, admin, plan)
    assert v2.version_number == 2
    db_session.commit()

    entitlement_service.grant_or_change(db_session, admin, late_user, product.id, "pro", EntitlementSource.PADDLE, None, None)
    db_session.commit()

    early_result = capability_service.resolve_effective_entitlements(db_session, early_user.id, product.id)
    late_result = capability_service.resolve_effective_entitlements(db_session, late_user.id, product.id)

    assert early_result.capabilities["download.max_resolution"] == 720  # frozen at grant time
    assert late_result.capabilities["download.max_resolution"] == capability_service.UNLIMITED


def test_plan_that_never_published_a_version_uses_live_capabilities_as_before(db_session):
    """Backward compatibility: a plan that never calls
    `publish_plan_version` behaves exactly like pre-versioning Mission 6 -
    live `PlanEntitlement` values, no snapshot involved."""
    admin = _admin(db_session, "admin-ver2@example.com")
    target = _admin(db_session, "target-ver2@example.com")
    product = _product(db_session, "ver-product-b")
    plan = catalog_service.create_plan(db_session, admin, product.id, "pro", "Pro")
    capability_service.define_capability(db_session, product.id, "ads.enabled", CapabilityValueType.BOOLEAN)
    capability_service.set_plan_entitlement(db_session, plan, "ads.enabled", True)

    entitlement_service.grant_or_change(db_session, admin, target, product.id, "pro", EntitlementSource.PADDLE, None, None)
    db_session.commit()
    result = capability_service.resolve_effective_entitlements(db_session, target.id, product.id)
    assert result.capabilities["ads.enabled"] is True

    # Live edit with NO published version - takes effect immediately,
    # exactly like Mission 6 phase 1's original (pre-versioning) behavior.
    capability_service.set_plan_entitlement(db_session, plan, "ads.enabled", False)
    db_session.commit()
    result_after = capability_service.resolve_effective_entitlements(db_session, target.id, product.id)
    assert result_after.capabilities["ads.enabled"] is False


def test_gift_pins_plan_version_too(db_session):
    admin = _admin(db_session, "admin-ver3@example.com")
    target = _admin(db_session, "target-ver3@example.com")
    product = _product(db_session, "ver-product-c")
    plan = catalog_service.create_plan(db_session, admin, product.id, "creator", "Creator")
    capability_service.define_capability(db_session, product.id, "watermark.enabled", CapabilityValueType.BOOLEAN)
    capability_service.set_plan_entitlement(db_session, plan, "watermark.enabled", False)
    catalog_service.publish_plan_version(db_session, admin, plan)

    gift_service.grant_gift(db_session, admin, target, plan, "beta", None)
    db_session.commit()

    # Catalog changes after the gift was granted.
    capability_service.set_plan_entitlement(db_session, plan, "watermark.enabled", True)
    catalog_service.publish_plan_version(db_session, admin, plan)
    db_session.commit()

    result = capability_service.resolve_effective_entitlements(db_session, target.id, product.id)
    assert result.capabilities["watermark.enabled"] is False  # frozen at gift time


def test_gift_ineligible_plan_rejected(db_session):
    admin = _admin(db_session, "admin-ver4@example.com")
    target = _admin(db_session, "target-ver4@example.com")
    product = _product(db_session, "ver-product-d")
    plan = catalog_service.create_plan(db_session, admin, product.id, "enterprise", "Enterprise", gifted_eligible=False)
    try:
        gift_service.grant_gift(db_session, admin, target, plan, "nope", None)
        assert False, "expected ForbiddenError"
    except ForbiddenError:
        pass


# --- Prices: version-safe, never mutated in place -------------------------------


def test_creating_a_new_price_does_not_touch_an_existing_subscriptions_price(db_session):
    admin = _admin(db_session, "admin-price1@example.com")
    target = _admin(db_session, "target-price1@example.com")
    product = _product(db_session, "price-product-a")
    plan = catalog_service.create_plan(db_session, admin, product.id, "creator", "Creator")

    old_price = catalog_service.create_price(
        db_session, admin, plan, provider="paddle", currency="usd", amount_cents=499, interval="month",
    )
    db_session.commit()

    subscription = Subscription(
        user_id=target.id, product_id=product.id, provider="paddle", provider_customer_ref="cust_1",
        provider_subscription_ref="sub_price_1", status="active", price_id=old_price.id,
    )
    db_session.add(subscription)
    db_session.flush()
    db_session.add(SubscriptionItem(subscription_id=subscription.id, plan_id=plan.id))
    db_session.commit()

    # The mission's own worked example: $4.99 -> $5.99.
    catalog_service.retire_price(db_session, admin, old_price, reason="price increase")
    new_price = catalog_service.create_price(
        db_session, admin, plan, provider="paddle", currency="usd", amount_cents=599, interval="month",
    )
    db_session.commit()

    # The existing subscriber's pinned price is completely unaffected.
    refreshed_sub = db_session.get(Subscription, subscription.id)
    pinned_price = db_session.get(type(old_price), refreshed_sub.price_id)
    assert pinned_price.id == old_price.id
    assert pinned_price.amount_cents == 499
    assert old_price.is_active is False
    assert old_price.retired_at is not None
    assert new_price.amount_cents == 599
    assert new_price.is_active is True


def test_retiring_an_already_retired_price_is_rejected(db_session):
    admin = _admin(db_session, "admin-price2@example.com")
    product = _product(db_session, "price-product-b")
    plan = catalog_service.create_plan(db_session, admin, product.id, "pro", "Pro")
    price = catalog_service.create_price(db_session, admin, plan, provider="paddle", currency="usd", amount_cents=999, interval="month")
    catalog_service.retire_price(db_session, admin, price)
    try:
        catalog_service.retire_price(db_session, admin, price)
        assert False, "expected ConflictError"
    except ConflictError:
        pass


def test_multiple_prices_per_plan_different_intervals_and_currencies(db_session):
    admin = _admin(db_session, "admin-price3@example.com")
    product = _product(db_session, "price-product-c")
    plan = catalog_service.create_plan(db_session, admin, product.id, "creator", "Creator")

    monthly = catalog_service.create_price(db_session, admin, plan, provider="paddle", currency="usd", amount_cents=999, interval="month")
    annual = catalog_service.create_price(db_session, admin, plan, provider="paddle", currency="usd", amount_cents=9999, interval="year")
    eur_monthly = catalog_service.create_price(db_session, admin, plan, provider="paddle", currency="eur", amount_cents=899, interval="month")

    prices = catalog_service.list_prices(db_session, plan.id)
    assert len(prices) == 3
    assert {p.interval for p in prices} == {"month", "year"}
    assert {p.currency for p in prices} == {"USD", "EUR"}


def test_price_visibility_can_be_toggled_without_retiring(db_session):
    admin = _admin(db_session, "admin-price4@example.com")
    product = _product(db_session, "price-product-d")
    plan = catalog_service.create_plan(db_session, admin, product.id, "pro", "Pro")
    price = catalog_service.create_price(db_session, admin, plan, provider="paddle", currency="usd", amount_cents=499, interval="month")
    catalog_service.update_price_visibility(db_session, admin, price, is_public=False)
    assert price.is_public is False
    assert price.is_active is True  # still purchasable via direct link/promo, just not listed


# --- Stats -----------------------------------------------------------------------


def test_plan_stats_counts_by_source_never_conflated(db_session):
    admin = _admin(db_session, "admin-stats1@example.com")
    paid_user = _admin(db_session, "paid-stats1@example.com")
    gifted_user = _admin(db_session, "gifted-stats1@example.com")
    product = _product(db_session, "stats-product-a")
    plan = catalog_service.create_plan(db_session, admin, product.id, "pro", "Pro")

    entitlement_service.grant_or_change(db_session, admin, paid_user, product.id, "pro", EntitlementSource.PADDLE, None, None)
    gift_service.grant_gift(db_session, admin, gifted_user, plan, "support", None)
    db_session.commit()

    stats = catalog_service.plan_stats(db_session, plan.id)
    assert stats["gifted"] == 1
    assert stats["legacy_entitlements"] == 2  # both paid and gifted currently sync to the legacy cache
