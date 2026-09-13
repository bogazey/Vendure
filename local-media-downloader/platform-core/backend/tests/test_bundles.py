"""Mission 6 (Phases 15-16): bundles and bundle-access lifecycle - most
importantly, that an independent per-product subscription/gift survives a
bundle change (nothing in bundle_service ever touches those tables)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.database.models import Product, User
from app.models.enums import EntitlementSource
from app.services import bundle_service, entitlement_service
from app.utils.exceptions import ConflictError


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


def test_duplicate_bundle_slug_rejected(db_session):
    admin = _user(db_session, "admin-bundle1@example.com")
    bundle_service.create_bundle(db_session, admin, "creator-suite-1", "Creator Suite")
    db_session.commit()
    try:
        bundle_service.create_bundle(db_session, admin, "creator-suite-1", "Creator Suite Again")
        assert False, "expected ConflictError"
    except ConflictError:
        pass


def test_bundle_grants_access_across_multiple_products(db_session):
    admin = _user(db_session, "admin-bundle2@example.com")
    target = _user(db_session, "user-bundle2@example.com")
    loady = _product(db_session, "bundle-loady")
    filey = _product(db_session, "bundle-filey")
    loady_plan = entitlement_service.get_or_create_plan(db_session, loady.id, "creator", "Creator")
    filey_plan = entitlement_service.get_or_create_plan(db_session, filey.id, "pro", "Pro")

    bundle = bundle_service.create_bundle(db_session, admin, "creator-suite-2", "Creator Suite")
    bundle_service.add_product_plan(db_session, bundle, loady_plan)
    bundle_service.add_product_plan(db_session, bundle, filey_plan)
    db_session.commit()

    bundle_service.grant_bundle_access(db_session, admin, target, bundle, source="paddle")
    db_session.commit()

    from app.services import capability_service

    loady_result = capability_service.resolve_effective_entitlements(db_session, target.id, loady.id)
    filey_result = capability_service.resolve_effective_entitlements(db_session, target.id, filey.id)
    assert any(s.plan_id == loady_plan.id for s in loady_result.sources)
    assert any(s.plan_id == filey_plan.id for s in filey_result.sources)


def test_bundle_expiry_does_not_touch_independent_subscription(db_session):
    """Mission-brief Phase 16's explicit lifecycle test: a user with both
    a bundle grant and their own independent paid subscription to the
    same product keeps the independent one when the bundle expires."""
    admin = _user(db_session, "admin-bundle3@example.com")
    target = _user(db_session, "user-bundle3@example.com")
    product = _product(db_session, "bundle-product-3")
    plan = entitlement_service.get_or_create_plan(db_session, product.id, "pro", "Pro")

    bundle = bundle_service.create_bundle(db_session, admin, "creator-suite-3", "Creator Suite")
    bundle_service.add_product_plan(db_session, bundle, plan)
    db_session.commit()

    # Independent paid entitlement, unrelated to the bundle.
    entitlement_service.grant_or_change(db_session, admin, target, product.id, "pro", EntitlementSource.PADDLE, None, None)
    access = bundle_service.grant_bundle_access(
        db_session, admin, target, bundle, source="gifted", expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)
    )
    db_session.commit()

    expired_count = bundle_service.expire_bundle_accesses(db_session)
    db_session.commit()
    assert expired_count == 1

    # The independent paid Entitlement row is completely untouched.
    legacy = entitlement_service.get_active_entitlement(db_session, target.id, product.id)
    assert legacy is not None
    assert legacy.source == EntitlementSource.PADDLE.value


def test_revoke_bundle_access(db_session):
    admin = _user(db_session, "admin-bundle4@example.com")
    target = _user(db_session, "user-bundle4@example.com")
    product = _product(db_session, "bundle-product-4")
    plan = entitlement_service.get_or_create_plan(db_session, product.id, "pro", "Pro")
    bundle = bundle_service.create_bundle(db_session, admin, "creator-suite-4", "Creator Suite")
    bundle_service.add_product_plan(db_session, bundle, plan)
    db_session.commit()

    access = bundle_service.grant_bundle_access(db_session, admin, target, bundle, source="internal")
    db_session.commit()
    bundle_service.revoke_bundle_access(db_session, admin, access.id, "mistake")
    db_session.commit()

    remaining = bundle_service.list_user_bundle_access(db_session, target.id)
    assert remaining[0].status == "revoked"
