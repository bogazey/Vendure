"""Mission 6 (Phase 13): gifted access v2 - history, paid-precedence
protection, stacked-gift-safe revoke, and expiry sweep."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.database.models import Product, User
from app.models.enums import EntitlementSource
from app.services import entitlement_service, gift_service
from app.utils.exceptions import ForbiddenError


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


def test_grant_creates_history_row_and_syncs_legacy_entitlement(db_session):
    admin = _user(db_session, "admin-gift1@example.com")
    target = _user(db_session, "user-gift1@example.com")
    product = _product(db_session, "gift-product-a")
    plan = entitlement_service.get_or_create_plan(db_session, product.id, "pro", "Pro")
    db_session.commit()

    gift = gift_service.grant_gift(db_session, admin, target, plan, "beta tester", None)
    db_session.commit()

    assert gift.status == "active"
    legacy = entitlement_service.get_active_entitlement(db_session, target.id, product.id)
    assert legacy is not None and legacy.source == EntitlementSource.GIFTED.value


def test_regifting_creates_a_new_history_row_not_an_overwrite(db_session):
    """The V1 limitation this table fixes: Entitlement.grant_or_change
    overwrites its one row in place, losing the prior grant's detail. A
    second gift must show up as a second GiftedAccess row."""
    admin = _user(db_session, "admin-gift2@example.com")
    target = _user(db_session, "user-gift2@example.com")
    product = _product(db_session, "gift-product-b")
    plan = entitlement_service.get_or_create_plan(db_session, product.id, "pro", "Pro")
    db_session.commit()

    gift_service.grant_gift(db_session, admin, target, plan, "first gift", None)
    db_session.commit()
    gift_service.grant_gift(db_session, admin, target, plan, "second gift", None)
    db_session.commit()

    history = gift_service.list_gift_history(db_session, target.id)
    assert len(history) == 2
    assert {g.reason for g in history} == {"first gift", "second gift"}


def test_gift_cannot_silently_replace_active_paid_entitlement(db_session):
    admin = _user(db_session, "admin-gift3@example.com")
    target = _user(db_session, "user-gift3@example.com")
    product = _product(db_session, "gift-product-c")
    plan = entitlement_service.get_or_create_plan(db_session, product.id, "pro", "Pro")
    db_session.commit()

    entitlement_service.grant_or_change(db_session, admin, target, product.id, "pro", EntitlementSource.PADDLE, None, None)
    db_session.commit()

    try:
        gift_service.grant_gift(db_session, admin, target, plan, "free gift", None)
        assert False, "expected ForbiddenError"
    except ForbiddenError:
        pass
    db_session.rollback()


def test_revoking_one_of_two_active_gifts_preserves_the_other(db_session):
    admin = _user(db_session, "admin-gift4@example.com")
    target = _user(db_session, "user-gift4@example.com")
    product = _product(db_session, "gift-product-d")
    plan = entitlement_service.get_or_create_plan(db_session, product.id, "pro", "Pro")
    db_session.commit()

    # Two independent gift grants stacked (e.g. from two different admins).
    # grant_gift's legacy sync updates the same Entitlement row each time,
    # but each call creates its own GiftedAccess history row.
    first = gift_service.grant_gift(db_session, admin, target, plan, "gift one", None)
    db_session.commit()
    gift_service.grant_gift(db_session, admin, target, plan, "gift two", None)
    db_session.commit()

    gift_service.revoke_gift(db_session, admin, first.id, "no longer needed")
    db_session.commit()

    # The second, still-active gift keeps the legacy fast-path cache alive.
    assert entitlement_service.get_active_entitlement(db_session, target.id, product.id) is not None
    active = gift_service.list_active_gifts(db_session, target.id)
    assert len(active) == 1
    assert active[0].reason == "gift two"


def test_revoking_the_only_active_gift_clears_legacy_entitlement(db_session):
    admin = _user(db_session, "admin-gift5@example.com")
    target = _user(db_session, "user-gift5@example.com")
    product = _product(db_session, "gift-product-e")
    plan = entitlement_service.get_or_create_plan(db_session, product.id, "pro", "Pro")
    db_session.commit()

    gift = gift_service.grant_gift(db_session, admin, target, plan, "only gift", None)
    db_session.commit()
    gift_service.revoke_gift(db_session, admin, gift.id, "revoked")
    db_session.commit()

    assert entitlement_service.get_active_entitlement(db_session, target.id, product.id) is None


def test_sync_expired_gifts_marks_status(db_session):
    admin = _user(db_session, "admin-gift6@example.com")
    target = _user(db_session, "user-gift6@example.com")
    product = _product(db_session, "gift-product-f")
    plan = entitlement_service.get_or_create_plan(db_session, product.id, "pro", "Pro")
    db_session.commit()

    past = datetime.now(timezone.utc) - timedelta(days=1)
    gift = gift_service.grant_gift(db_session, admin, target, plan, "time-limited", past)
    db_session.commit()

    swept = gift_service.sync_expired_gifts(db_session)
    db_session.commit()
    assert swept >= 1
    assert gift.status == "expired"
