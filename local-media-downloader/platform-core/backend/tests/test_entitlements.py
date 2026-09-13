"""Central entitlement system: product isolation, expiry, gifted vs paid,
and revocation."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.database.models import Plan, Product, User
from app.models.enums import EntitlementSource, EntitlementStatus
from app.services import entitlement_service


def _make_user(db_session, email: str) -> User:
    user = User(email=email, password_hash="x", email_verified=True)
    db_session.add(user)
    db_session.flush()
    return user


def _make_product(db_session, product_id: str) -> Product:
    if db_session.get(Product, product_id) is None:
        db_session.add(Product(id=product_id, name=product_id, domain=f"{product_id}.example", status="live"))
        db_session.flush()
    entitlement_service.get_or_create_plan(db_session, product_id, "pro", "Pro")
    return db_session.get(Product, product_id)


def test_grant_creates_active_entitlement(db_session):
    admin = _make_user(db_session, "admin-ent1@example.com")
    target = _make_user(db_session, "user-ent1@example.com")
    product = _make_product(db_session, "ent-product-a")

    entitlement = entitlement_service.grant_or_change(
        db_session, admin, target, product.id, "pro", EntitlementSource.PADDLE, None, None
    )
    db_session.commit()

    active = entitlement_service.get_active_entitlement(db_session, target.id, product.id)
    assert active is not None
    assert active.id == entitlement.id
    assert active.source == "paddle"


def test_wrong_product_denied(db_session):
    admin = _make_user(db_session, "admin-ent2@example.com")
    target = _make_user(db_session, "user-ent2@example.com")
    product_a = _make_product(db_session, "ent-product-b")
    product_b = _make_product(db_session, "ent-product-c")

    entitlement_service.grant_or_change(db_session, admin, target, product_a.id, "pro", EntitlementSource.PADDLE, None, None)
    db_session.commit()

    assert entitlement_service.get_active_entitlement(db_session, target.id, product_a.id) is not None
    assert entitlement_service.get_active_entitlement(db_session, target.id, product_b.id) is None


def test_expired_entitlement_denied(db_session):
    admin = _make_user(db_session, "admin-ent3@example.com")
    target = _make_user(db_session, "user-ent3@example.com")
    product = _make_product(db_session, "ent-product-d")

    past = datetime.now(timezone.utc) - timedelta(days=1)
    entitlement_service.grant_or_change(db_session, admin, target, product.id, "pro", EntitlementSource.TRIAL, past, None)
    db_session.commit()

    assert entitlement_service.get_active_entitlement(db_session, target.id, product.id) is None


def test_future_expiry_still_active(db_session):
    admin = _make_user(db_session, "admin-ent4@example.com")
    target = _make_user(db_session, "user-ent4@example.com")
    product = _make_product(db_session, "ent-product-e")

    future = datetime.now(timezone.utc) + timedelta(days=30)
    entitlement_service.grant_or_change(db_session, admin, target, product.id, "pro", EntitlementSource.TRIAL, future, None)
    db_session.commit()

    assert entitlement_service.get_active_entitlement(db_session, target.id, product.id) is not None


def test_gifted_access_grants_identical_entitlement_shape_to_paid(db_session):
    admin = _make_user(db_session, "admin-ent5@example.com")
    paid_user = _make_user(db_session, "paid-ent5@example.com")
    gifted_user = _make_user(db_session, "gifted-ent5@example.com")
    product = _make_product(db_session, "ent-product-f")

    entitlement_service.grant_or_change(db_session, admin, paid_user, product.id, "pro", EntitlementSource.PADDLE, None, None)
    entitlement_service.grant_or_change(db_session, admin, gifted_user, product.id, "pro", EntitlementSource.GIFTED, None, "support gift")
    db_session.commit()

    paid = entitlement_service.get_active_entitlement(db_session, paid_user.id, product.id)
    gifted = entitlement_service.get_active_entitlement(db_session, gifted_user.id, product.id)
    assert paid.status == gifted.status == EntitlementStatus.ACTIVE.value
    assert paid.plan_id == gifted.plan_id
    assert gifted.source == "gifted"
    assert gifted.reason == "support gift"


def test_revoked_access_denied(db_session):
    admin = _make_user(db_session, "admin-ent6@example.com")
    target = _make_user(db_session, "user-ent6@example.com")
    product = _make_product(db_session, "ent-product-g")

    entitlement_service.grant_or_change(db_session, admin, target, product.id, "pro", EntitlementSource.GIFTED, None, None)
    db_session.commit()
    assert entitlement_service.get_active_entitlement(db_session, target.id, product.id) is not None

    entitlement_service.revoke(db_session, admin, target, product.id, "no longer needed")
    db_session.commit()
    assert entitlement_service.get_active_entitlement(db_session, target.id, product.id) is None


def test_change_between_gifted_plans_preserves_single_row(db_session):
    admin = _make_user(db_session, "admin-ent7@example.com")
    target = _make_user(db_session, "user-ent7@example.com")
    product = _make_product(db_session, "ent-product-h")
    entitlement_service.get_or_create_plan(db_session, product.id, "creator", "Creator")

    first = entitlement_service.grant_or_change(db_session, admin, target, product.id, "pro", EntitlementSource.GIFTED, None, None)
    db_session.commit()
    changed = entitlement_service.grant_or_change(db_session, admin, target, product.id, "creator", EntitlementSource.GIFTED, None, "upgrade")
    db_session.commit()

    assert changed.id == first.id
    active = entitlement_service.get_active_entitlement(db_session, target.id, product.id)
    plan = db_session.get(Plan, active.plan_id)
    assert plan.slug == "creator"


def test_invalid_plan_rejected(db_session):
    from app.utils.exceptions import InvalidPlanError

    admin = _make_user(db_session, "admin-ent8@example.com")
    target = _make_user(db_session, "user-ent8@example.com")
    product = _make_product(db_session, "ent-product-i")

    try:
        entitlement_service.grant_or_change(db_session, admin, target, product.id, "nonexistent-plan", EntitlementSource.PADDLE, None, None)
        assert False, "expected InvalidPlanError"
    except InvalidPlanError:
        pass
