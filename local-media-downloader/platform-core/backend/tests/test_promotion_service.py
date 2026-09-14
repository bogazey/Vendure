"""Mission 6 continuation: promotions and trials, distinct from gifted/
paid/bundle/internal, with expiry and entitlement-precedence tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.database.models import PaymentRecord, Product, User
from app.models.enums import EntitlementSource
from app.services import catalog_service, entitlement_service, promotion_service
from app.utils.exceptions import ForbiddenError


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


def test_trial_and_promotion_are_stored_distinctly(db_session):
    admin = _admin(db_session, "admin-promo1@example.com")
    trial_user = _admin(db_session, "trial-promo1@example.com")
    promo_user = _admin(db_session, "promo-promo1@example.com")
    product = _product(db_session, "promo-product-a")
    plan = catalog_service.create_plan(db_session, admin, product.id, "pro", "Pro")

    future = datetime.now(timezone.utc) + timedelta(days=14)
    trial = promotion_service.grant_promotion_or_trial(db_session, admin, trial_user, plan, "trial", future)
    promo = promotion_service.grant_promotion_or_trial(
        db_session, admin, promo_user, plan, "promotion", future, source_code="LAUNCH2026"
    )
    db_session.commit()

    assert trial.kind == "trial"
    assert promo.kind == "promotion"
    assert promo.source_code == "LAUNCH2026"
    assert trial.id != promo.id


def test_trial_ineligible_plan_rejected(db_session):
    admin = _admin(db_session, "admin-promo2@example.com")
    target = _admin(db_session, "target-promo2@example.com")
    product = _product(db_session, "promo-product-b")
    plan = catalog_service.create_plan(db_session, admin, product.id, "enterprise", "Enterprise", trial_eligible=False)
    future = datetime.now(timezone.utc) + timedelta(days=7)
    try:
        promotion_service.grant_promotion_or_trial(db_session, admin, target, plan, "trial", future)
        assert False, "expected ForbiddenError"
    except ForbiddenError:
        pass


def test_promotion_never_creates_a_payment_record(db_session):
    from sqlalchemy import select

    admin = _admin(db_session, "admin-promo3@example.com")
    target = _admin(db_session, "target-promo3@example.com")
    product = _product(db_session, "promo-product-c")
    plan = catalog_service.create_plan(db_session, admin, product.id, "pro", "Pro")
    future = datetime.now(timezone.utc) + timedelta(days=30)

    before = len(db_session.execute(select(PaymentRecord)).scalars().all())
    promotion_service.grant_promotion_or_trial(db_session, admin, target, plan, "promotion", future)
    db_session.commit()
    after = len(db_session.execute(select(PaymentRecord)).scalars().all())
    assert before == after


def test_expired_trial_falls_away_and_does_not_contribute(db_session):
    from app.services import capability_service
    from app.models.enums import CapabilityValueType

    admin = _admin(db_session, "admin-promo4@example.com")
    target = _admin(db_session, "target-promo4@example.com")
    product = _product(db_session, "promo-product-d")
    plan = catalog_service.create_plan(db_session, admin, product.id, "pro", "Pro")
    capability_service.define_capability(db_session, product.id, "trial.flag", CapabilityValueType.BOOLEAN)
    capability_service.set_plan_entitlement(db_session, plan, "trial.flag", True)

    # Grant an already-expired trial directly (simulating time passing)
    # rather than sleeping in a test.
    past = datetime.now(timezone.utc) - timedelta(days=1)
    grant = promotion_service.grant_promotion_or_trial(db_session, admin, target, plan, "trial", past + timedelta(seconds=1))
    db_session.commit()

    # Force it into the past for the resolution check (grant validation
    # itself doesn't reject a near-past expiry, mirroring gift_service).
    grant.expires_at = past
    db_session.commit()

    result = capability_service.resolve_effective_entitlements(db_session, target.id, product.id)
    assert "trial.flag" not in result.capabilities or result.capabilities.get("trial.flag") is not True


def test_sync_expired_marks_status(db_session):
    admin = _admin(db_session, "admin-promo5@example.com")
    target = _admin(db_session, "target-promo5@example.com")
    product = _product(db_session, "promo-product-e")
    plan = catalog_service.create_plan(db_session, admin, product.id, "pro", "Pro")
    past = datetime.now(timezone.utc) - timedelta(days=1)

    grant = promotion_service.grant_promotion_or_trial(db_session, admin, target, plan, "trial", past + timedelta(hours=1))
    grant.expires_at = past
    db_session.commit()

    swept = promotion_service.sync_expired(db_session)
    db_session.commit()
    assert swept >= 1
    assert grant.status == "expired"


def test_promotion_cannot_silently_replace_active_paid_entitlement(db_session):
    admin = _admin(db_session, "admin-promo6@example.com")
    target = _admin(db_session, "target-promo6@example.com")
    product = _product(db_session, "promo-product-f")
    plan = catalog_service.create_plan(db_session, admin, product.id, "pro", "Pro")
    entitlement_service.grant_or_change(db_session, admin, target, product.id, "pro", EntitlementSource.PADDLE, None, None)
    db_session.commit()

    future = datetime.now(timezone.utc) + timedelta(days=7)
    try:
        promotion_service.grant_promotion_or_trial(db_session, admin, target, plan, "promotion", future)
        assert False, "expected ForbiddenError"
    except ForbiddenError:
        pass


def test_revoke_promotion(db_session):
    admin = _admin(db_session, "admin-promo7@example.com")
    target = _admin(db_session, "target-promo7@example.com")
    product = _product(db_session, "promo-product-g")
    plan = catalog_service.create_plan(db_session, admin, product.id, "pro", "Pro")
    future = datetime.now(timezone.utc) + timedelta(days=7)

    grant = promotion_service.grant_promotion_or_trial(db_session, admin, target, plan, "trial", future)
    db_session.commit()
    promotion_service.revoke(db_session, admin, grant.id, "abuse")
    db_session.commit()
    assert grant.status == "revoked"
    assert promotion_service.list_active(db_session, target.id) == []
