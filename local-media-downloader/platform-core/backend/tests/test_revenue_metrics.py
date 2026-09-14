"""Mission 6 continuation (Phase 12): revenue metrics computed only from
real PaymentRecord/Subscription/Price rows - never fabricated."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.database.models import PaymentRecord, Price, Product, Subscription, SubscriptionItem, User
from app.services import catalog_service, revenue_service


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


def test_no_data_reports_unavailable_not_zero(db_session):
    product = _product(db_session, "rev-product-empty")
    metrics = revenue_service.compute_metrics(db_session, product_id=product.id)
    assert metrics.revenue_cents == 0
    assert metrics.paid_subscribers == 0
    assert metrics.mrr_cents is None  # unavailable, not fabricated as 0
    assert metrics.arpu_cents is None
    assert any("unavailable" in note.lower() for note in metrics.notes)


def test_gifted_and_free_never_count_as_revenue(db_session):
    from app.services import entitlement_service, gift_service
    from app.models.enums import EntitlementSource

    admin = _admin(db_session, "admin-rev1@example.com")
    target = _admin(db_session, "target-rev1@example.com")
    product = _product(db_session, "rev-product-gift")
    plan = catalog_service.create_plan(db_session, admin, product.id, "pro", "Pro")
    gift_service.grant_gift(db_session, admin, target, plan, "gift", None)
    db_session.commit()

    metrics = revenue_service.compute_metrics(db_session, product_id=product.id)
    assert metrics.revenue_cents == 0
    assert metrics.paid_subscribers == 0


def test_real_payment_counts_as_revenue(db_session):
    admin = _admin(db_session, "admin-rev2@example.com")
    product = _product(db_session, "rev-product-paid")
    db_session.add(PaymentRecord(
        user_id=admin.id, product_id=product.id, provider="paddle", provider_reference="ref-rev2",
        amount_cents=1999, currency="USD", status="completed", occurred_at=datetime.now(timezone.utc),
    ))
    db_session.commit()

    metrics = revenue_service.compute_metrics(db_session, product_id=product.id)
    assert metrics.revenue_cents == 1999
    assert metrics.net_revenue_cents == 1999


def test_refund_reduces_net_revenue(db_session):
    admin = _admin(db_session, "admin-rev3@example.com")
    product = _product(db_session, "rev-product-refund")
    db_session.add(PaymentRecord(
        user_id=admin.id, product_id=product.id, provider="paddle", provider_reference="ref-rev3",
        amount_cents=1999, currency="USD", status="refunded", refunded_amount_cents=1999,
        occurred_at=datetime.now(timezone.utc),
    ))
    db_session.commit()

    metrics = revenue_service.compute_metrics(db_session, product_id=product.id)
    assert metrics.revenue_cents == 1999
    assert metrics.refunded_cents == 1999
    assert metrics.net_revenue_cents == 0


def test_mrr_computed_from_real_monthly_and_annual_prices(db_session):
    admin = _admin(db_session, "admin-rev4@example.com")
    monthly_user = _admin(db_session, "monthly-rev4@example.com")
    annual_user = _admin(db_session, "annual-rev4@example.com")
    product = _product(db_session, "rev-product-mrr")
    plan = catalog_service.create_plan(db_session, admin, product.id, "pro", "Pro")

    monthly_price = catalog_service.create_price(db_session, admin, plan, provider="paddle", currency="usd", amount_cents=1000, interval="month")
    annual_price = catalog_service.create_price(db_session, admin, plan, provider="paddle", currency="usd", amount_cents=12000, interval="year")
    db_session.commit()

    for user, price in [(monthly_user, monthly_price), (annual_user, annual_price)]:
        sub = Subscription(
            user_id=user.id, product_id=product.id, provider="paddle", provider_customer_ref=f"cust_{user.id}",
            provider_subscription_ref=f"sub_{user.id}", status="active", price_id=price.id,
        )
        db_session.add(sub)
        db_session.flush()
        db_session.add(SubscriptionItem(subscription_id=sub.id, plan_id=plan.id))
    db_session.commit()

    metrics = revenue_service.compute_metrics(db_session, product_id=product.id)
    # $10/mo + ($120/yr -> $10/mo equivalent) = $20/mo = 2000 cents
    assert metrics.mrr_cents == 2000
    assert metrics.arr_cents == 24000
    assert metrics.paid_subscribers == 2
    assert metrics.arpu_cents is not None  # net_revenue may be 0 (no PaymentRecord), but subscriber count > 0


def test_subscription_without_resolvable_price_excluded_from_mrr_not_estimated(db_session):
    admin = _admin(db_session, "admin-rev5@example.com")
    target = _admin(db_session, "target-rev5@example.com")
    product = _product(db_session, "rev-product-nopricemrr")
    plan = catalog_service.create_plan(db_session, admin, product.id, "pro", "Pro")

    sub = Subscription(
        user_id=target.id, product_id=product.id, provider="paddle", provider_customer_ref="cust_x",
        provider_subscription_ref="sub_x", status="active", price_id=None,
    )
    db_session.add(sub)
    db_session.flush()
    db_session.add(SubscriptionItem(subscription_id=sub.id, plan_id=plan.id))
    db_session.commit()

    metrics = revenue_service.compute_metrics(db_session, product_id=product.id)
    assert metrics.mrr_cents == 0  # no resolvable price contributed
    assert any("no resolvable Price" in note for note in metrics.notes)


def test_metrics_scoped_by_product_never_leak_across_products(db_session):
    admin = _admin(db_session, "admin-rev6@example.com")
    product_a = _product(db_session, "rev-product-a")
    product_b = _product(db_session, "rev-product-b")
    db_session.add(PaymentRecord(user_id=admin.id, product_id=product_a.id, provider="paddle", provider_reference="ref-a", amount_cents=500, currency="USD", status="completed"))
    db_session.add(PaymentRecord(user_id=admin.id, product_id=product_b.id, provider="paddle", provider_reference="ref-b", amount_cents=9999, currency="USD", status="completed"))
    db_session.commit()

    metrics_a = revenue_service.compute_metrics(db_session, product_id=product_a.id)
    assert metrics_a.revenue_cents == 500


def test_date_range_filters_payments(db_session):
    admin = _admin(db_session, "admin-rev7@example.com")
    product = _product(db_session, "rev-product-daterange")
    now = datetime.now(timezone.utc)
    db_session.add(PaymentRecord(user_id=admin.id, product_id=product.id, provider="paddle", provider_reference="ref-old", amount_cents=100, currency="USD", status="completed", occurred_at=now - timedelta(days=60)))
    db_session.add(PaymentRecord(user_id=admin.id, product_id=product.id, provider="paddle", provider_reference="ref-new", amount_cents=200, currency="USD", status="completed", occurred_at=now - timedelta(days=1)))
    db_session.commit()

    metrics = revenue_service.compute_metrics(db_session, product_id=product.id, start=now - timedelta(days=10), end=now)
    assert metrics.revenue_cents == 200
