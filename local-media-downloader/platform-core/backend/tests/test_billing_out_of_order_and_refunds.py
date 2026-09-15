"""Mission 8 (Billing Ownership Transition): out-of-order/delayed webhook
protection and refund/chargeback handling - gaps identified in the audit
of the Mission 6 billing engine (docs/platform/BILLING_OWNERSHIP_TRANSITION.md).
Uses `FakeBillingProvider` exclusively - no real network call."""
from __future__ import annotations

import json
import uuid

from sqlalchemy import select

from app.database.models import PaymentRecord, Product, Subscription, SubscriptionItem, User
from app.models.enums import EntitlementSource
from app.services import entitlement_service, webhook_service
from app.services.billing.fake_provider import FakeBillingProvider


def _product(db_session, product_id: str):
    if db_session.get(Product, product_id) is None:
        db_session.add(Product(id=product_id, name=product_id, domain=f"{product_id}.example", status="live"))
        db_session.flush()
    return db_session.get(Product, product_id)


def _subscription_event(event_id, user_id, product_id, plan_slug, sub_ref, *, status="active", occurred_at):
    payload = {
        "event_id": event_id, "event_type": "subscription.created", "occurred_at": occurred_at,
        "subscription_ref": sub_ref, "customer_ref": f"cust_{user_id}", "status": status,
        "custom_data": {"user_id": user_id, "product_id": product_id, "plan_slug": plan_slug},
    }
    return json.dumps(payload).encode("utf-8")


def _subscription_update_event(event_id, sub_ref, *, status, occurred_at,
                                current_period_start=None, current_period_end=None, cancel_at_period_end=None):
    payload = {
        "event_id": event_id, "event_type": "subscription.updated", "occurred_at": occurred_at,
        "subscription_ref": sub_ref, "status": status,
    }
    if current_period_start is not None:
        payload["current_period_start"] = current_period_start
    if current_period_end is not None:
        payload["current_period_end"] = current_period_end
    if cancel_at_period_end is not None:
        payload["cancel_at_period_end"] = cancel_at_period_end
    return json.dumps(payload).encode("utf-8")


def _transaction_event(event_id, sub_ref, amount_cents, currency, *, transaction_ref, occurred_at="2026-01-02T00:00:00+00:00"):
    payload = {
        "event_id": event_id, "event_type": "transaction.completed", "occurred_at": occurred_at,
        "subscription_ref": sub_ref, "amount_cents": amount_cents, "currency": currency,
        "transaction_ref": transaction_ref,
    }
    return json.dumps(payload).encode("utf-8")


def _adjustment_event(event_id, transaction_ref, action_status, amount_cents=None, *,
                       occurred_at="2026-01-03T00:00:00+00:00", event_type="adjustment.created",
                       adjustment_status=None):
    payload = {
        "event_id": event_id, "event_type": event_type, "occurred_at": occurred_at,
        "transaction_ref": transaction_ref, "status": action_status,
    }
    if amount_cents is not None:
        payload["amount_cents"] = amount_cents
        payload["currency"] = "USD"
    if adjustment_status is not None:
        payload["adjustment_status"] = adjustment_status
    return json.dumps(payload).encode("utf-8")


def _send(db_session, provider, body):
    headers = {"fake-signature": provider.sign(body)}
    return webhook_service.receive_webhook(db_session, provider, body, headers)


class TestOutOfOrderAndDelayedWebhooks:
    def test_out_of_order_event_never_overwrites_a_newer_status(self, db_session):
        user = User(email=f"ooo-{uuid.uuid4().hex[:8]}@example.com", password_hash="x", email_verified=True)
        db_session.add(user)
        product = _product(db_session, "ooo-product")
        entitlement_service.get_or_create_plan(db_session, product.id, "pro", "Pro")
        db_session.commit()

        provider = FakeBillingProvider()
        sub_ref = f"sub_{uuid.uuid4().hex}"

        # created at t=1 (active), then a NEWER "canceled" event at t=3
        # arrives BEFORE a genuinely OLDER "past_due" event at t=2 - the
        # out-of-order one must never win.
        _send(db_session, provider, _subscription_event(
            str(uuid.uuid4()), user.id, product.id, "pro", sub_ref,
            status="active", occurred_at="2026-02-01T00:00:00+00:00",
        ))
        db_session.commit()

        _send(db_session, provider, _subscription_update_event(
            str(uuid.uuid4()), sub_ref, status="canceled", occurred_at="2026-02-03T00:00:00+00:00",
        ))
        db_session.commit()

        _send(db_session, provider, _subscription_update_event(
            str(uuid.uuid4()), sub_ref, status="past_due", occurred_at="2026-02-02T00:00:00+00:00",
        ))
        db_session.commit()

        subscription = db_session.execute(
            select(Subscription).where(Subscription.provider_subscription_ref == sub_ref)
        ).scalars().first()
        assert subscription.status == "canceled", "an older, out-of-order event must never overwrite a newer one"

    def test_delayed_event_with_no_prior_timestamp_still_applies(self, db_session):
        """The very first event for a subscription always applies,
        regardless of how "delayed" it might look in isolation - there is
        nothing yet to be older than."""
        user = User(email=f"delayed-{uuid.uuid4().hex[:8]}@example.com", password_hash="x", email_verified=True)
        db_session.add(user)
        product = _product(db_session, "delayed-product")
        entitlement_service.get_or_create_plan(db_session, product.id, "pro", "Pro")
        db_session.commit()

        provider = FakeBillingProvider()
        sub_ref = f"sub_{uuid.uuid4().hex}"
        _send(db_session, provider, _subscription_event(
            str(uuid.uuid4()), user.id, product.id, "pro", sub_ref,
            status="active", occurred_at="2020-01-01T00:00:00+00:00",
        ))
        db_session.commit()

        subscription = db_session.execute(
            select(Subscription).where(Subscription.provider_subscription_ref == sub_ref)
        ).scalars().first()
        assert subscription.status == "active"
        assert subscription.last_event_occurred_at is not None

    def test_in_order_events_both_apply_and_advance_the_watermark(self, db_session):
        user = User(email=f"order-{uuid.uuid4().hex[:8]}@example.com", password_hash="x", email_verified=True)
        db_session.add(user)
        product = _product(db_session, "order-product")
        entitlement_service.get_or_create_plan(db_session, product.id, "pro", "Pro")
        db_session.commit()

        provider = FakeBillingProvider()
        sub_ref = f"sub_{uuid.uuid4().hex}"
        _send(db_session, provider, _subscription_event(
            str(uuid.uuid4()), user.id, product.id, "pro", sub_ref,
            status="active", occurred_at="2026-03-01T00:00:00+00:00",
        ))
        db_session.commit()
        _send(db_session, provider, _subscription_update_event(
            str(uuid.uuid4()), sub_ref, status="past_due", occurred_at="2026-03-02T00:00:00+00:00",
        ))
        db_session.commit()

        subscription = db_session.execute(
            select(Subscription).where(Subscription.provider_subscription_ref == sub_ref)
        ).scalars().first()
        assert subscription.status == "past_due"


class TestBillingPeriodPreservation:
    def test_subscription_update_advances_renewal_date_and_records_scheduled_cancellation(self, db_session):
        """Before mission 8, `upsert_subscription` always re-used the
        EXISTING row's period/cancellation fields no matter what a
        `subscription.updated` event said - a real renewal or a
        cancel-at-period-end request could never actually be recorded.
        This is the regression test for that fix."""
        user = User(email=f"period-{uuid.uuid4().hex[:8]}@example.com", password_hash="x", email_verified=True)
        db_session.add(user)
        product = _product(db_session, "period-product")
        entitlement_service.get_or_create_plan(db_session, product.id, "pro", "Pro")
        db_session.commit()

        provider = FakeBillingProvider()
        sub_ref = f"sub_{uuid.uuid4().hex}"
        _send(db_session, provider, _subscription_event(
            str(uuid.uuid4()), user.id, product.id, "pro", sub_ref, occurred_at="2026-01-01T00:00:00+00:00",
        ))
        db_session.commit()

        subscription = db_session.execute(
            select(Subscription).where(Subscription.provider_subscription_ref == sub_ref)
        ).scalars().first()
        assert subscription.current_period_end is None, "no period was ever supplied yet"

        # A renewal: the period rolls forward a month, cancel_at_period_end
        # is still false.
        _send(db_session, provider, _subscription_update_event(
            str(uuid.uuid4()), sub_ref, status="active", occurred_at="2026-02-01T00:00:00+00:00",
            current_period_start="2026-02-01T00:00:00+00:00", current_period_end="2026-03-01T00:00:00+00:00",
        ))
        db_session.commit()
        db_session.refresh(subscription)
        assert subscription.current_period_end.isoformat().startswith("2026-03-01")
        assert subscription.cancel_at_period_end is False

        # The customer cancels: Paddle reports a scheduled cancellation
        # without changing the current period end yet.
        _send(db_session, provider, _subscription_update_event(
            str(uuid.uuid4()), sub_ref, status="active", occurred_at="2026-02-15T00:00:00+00:00",
            cancel_at_period_end=True,
        ))
        db_session.commit()
        db_session.refresh(subscription)
        assert subscription.cancel_at_period_end is True
        assert subscription.current_period_end.isoformat().startswith("2026-03-01"), (
            "an event that doesn't mention the period end must never reset it"
        )


class TestMidCyclePlanChange:
    def test_subscription_updated_with_a_new_plan_slug_actually_changes_the_plan(self, db_session):
        """Before mission 8, the existing-subscription branch always
        re-derived the plan from the subscription's OWN current item and
        compared it to itself - an upgrade/downgrade event could never
        actually change anything. This is the regression test for that
        fix."""
        user = User(email=f"planchange-{uuid.uuid4().hex[:8]}@example.com", password_hash="x", email_verified=True)
        db_session.add(user)
        product = _product(db_session, "planchange-product")
        entitlement_service.get_or_create_plan(db_session, product.id, "pro", "Pro")
        entitlement_service.get_or_create_plan(db_session, product.id, "creator", "Creator")
        db_session.commit()

        provider = FakeBillingProvider()
        sub_ref = f"sub_{uuid.uuid4().hex}"
        _send(db_session, provider, _subscription_event(
            str(uuid.uuid4()), user.id, product.id, "pro", sub_ref, occurred_at="2026-01-01T00:00:00+00:00",
        ))
        db_session.commit()

        legacy = entitlement_service.get_active_entitlement(db_session, user.id, product.id)
        assert legacy.plan_id == entitlement_service.get_plan(db_session, product.id, "pro").id

        # Upgraded mid-cycle to Creator.
        upgrade_body = json.dumps({
            "event_id": str(uuid.uuid4()), "event_type": "subscription.updated",
            "occurred_at": "2026-01-15T00:00:00+00:00", "subscription_ref": sub_ref, "status": "active",
            "custom_data": {"plan_slug": "creator"},
        }).encode("utf-8")
        _send(db_session, provider, upgrade_body)
        db_session.commit()

        subscription = db_session.execute(
            select(Subscription).where(Subscription.provider_subscription_ref == sub_ref)
        ).scalars().first()
        item = db_session.execute(
            select(SubscriptionItem).where(SubscriptionItem.subscription_id == subscription.id)
        ).scalars().first()
        assert item.plan_id == entitlement_service.get_plan(db_session, product.id, "creator").id

        legacy = entitlement_service.get_active_entitlement(db_session, user.id, product.id)
        assert legacy.plan_id == entitlement_service.get_plan(db_session, product.id, "creator").id

        # Downgraded back to Pro.
        downgrade_body = json.dumps({
            "event_id": str(uuid.uuid4()), "event_type": "subscription.updated",
            "occurred_at": "2026-01-20T00:00:00+00:00", "subscription_ref": sub_ref, "status": "active",
            "custom_data": {"plan_slug": "pro"},
        }).encode("utf-8")
        _send(db_session, provider, downgrade_body)
        db_session.commit()

        db_session.refresh(item)
        assert item.plan_id == entitlement_service.get_plan(db_session, product.id, "pro").id


class TestRefundsAndChargebacks:
    def _paid_subscription(self, db_session, product_id: str):
        user = User(email=f"refund-{uuid.uuid4().hex[:8]}@example.com", password_hash="x", email_verified=True)
        db_session.add(user)
        product = _product(db_session, product_id)
        entitlement_service.get_or_create_plan(db_session, product.id, "pro", "Pro")
        db_session.commit()

        provider = FakeBillingProvider()
        sub_ref = f"sub_{uuid.uuid4().hex}"
        txn_ref = f"txn_{uuid.uuid4().hex}"
        _send(db_session, provider, _subscription_event(str(uuid.uuid4()), user.id, product.id, "pro", sub_ref, occurred_at="2026-01-01T00:00:00+00:00"))
        db_session.commit()
        _send(db_session, provider, _transaction_event(str(uuid.uuid4()), sub_ref, 2000, "USD", transaction_ref=txn_ref))
        db_session.commit()
        return provider, user, product, sub_ref, txn_ref

    def test_full_refund_marks_payment_refunded_and_revokes_entitlement(self, db_session):
        provider, user, product, sub_ref, txn_ref = self._paid_subscription(db_session, "refund-full-product")
        assert entitlement_service.get_active_entitlement(db_session, user.id, product.id) is not None

        _send(db_session, provider, _adjustment_event(str(uuid.uuid4()), txn_ref, "refunded", 2000))
        db_session.commit()

        payment = db_session.execute(
            select(PaymentRecord).where(PaymentRecord.provider_reference == txn_ref)
        ).scalars().first()
        assert payment.status == "refunded"
        assert payment.refunded_amount_cents == 2000
        assert entitlement_service.get_active_entitlement(db_session, user.id, product.id) is None

    def test_partial_refund_does_not_revoke_entitlement(self, db_session):
        provider, user, product, sub_ref, txn_ref = self._paid_subscription(db_session, "refund-partial-product")

        _send(db_session, provider, _adjustment_event(str(uuid.uuid4()), txn_ref, "refunded", 500))
        db_session.commit()

        payment = db_session.execute(
            select(PaymentRecord).where(PaymentRecord.provider_reference == txn_ref)
        ).scalars().first()
        assert payment.status == "partially_refunded"
        assert payment.refunded_amount_cents == 500
        assert entitlement_service.get_active_entitlement(db_session, user.id, product.id) is not None, (
            "a partial refund must never remove access the customer is still paying for"
        )

    def test_two_partial_refunds_accumulate_to_a_full_refund(self, db_session):
        provider, user, product, sub_ref, txn_ref = self._paid_subscription(db_session, "refund-accum-product")

        _send(db_session, provider, _adjustment_event(str(uuid.uuid4()), txn_ref, "refunded", 1000))
        db_session.commit()
        _send(db_session, provider, _adjustment_event(str(uuid.uuid4()), txn_ref, "refunded", 1000))
        db_session.commit()

        payment = db_session.execute(
            select(PaymentRecord).where(PaymentRecord.provider_reference == txn_ref)
        ).scalars().first()
        assert payment.refunded_amount_cents == 2000
        assert payment.status == "refunded"
        assert entitlement_service.get_active_entitlement(db_session, user.id, product.id) is None

    def test_chargeback_marks_disputed_and_revokes_entitlement(self, db_session):
        provider, user, product, sub_ref, txn_ref = self._paid_subscription(db_session, "chargeback-product")

        _send(db_session, provider, _adjustment_event(str(uuid.uuid4()), txn_ref, "disputed"))
        db_session.commit()

        payment = db_session.execute(
            select(PaymentRecord).where(PaymentRecord.provider_reference == txn_ref)
        ).scalars().first()
        assert payment.status == "disputed"
        assert entitlement_service.get_active_entitlement(db_session, user.id, product.id) is None

    def test_duplicate_refund_webhook_delivery_does_not_double_refund(self, db_session):
        provider, user, product, sub_ref, txn_ref = self._paid_subscription(db_session, "refund-dup-product")

        event_id = str(uuid.uuid4())
        body = _adjustment_event(event_id, txn_ref, "refunded", 500)
        _send(db_session, provider, body)
        db_session.commit()
        _send(db_session, provider, body)  # exact same webhook delivered twice
        db_session.commit()

        payment = db_session.execute(
            select(PaymentRecord).where(PaymentRecord.provider_reference == txn_ref)
        ).scalars().first()
        assert payment.refunded_amount_cents == 500, "a duplicate webhook delivery must never double-apply a refund"

    def test_unrecognized_adjustment_action_is_ignored_not_guessed(self, db_session):
        provider, user, product, sub_ref, txn_ref = self._paid_subscription(db_session, "adj-unknown-product")

        # "credit" (a goodwill balance credit) has no entitlement effect
        # and is deliberately unhandled - see paddle_provider's docstring.
        _send(db_session, provider, _adjustment_event(str(uuid.uuid4()), txn_ref, None))
        db_session.commit()

        payment = db_session.execute(
            select(PaymentRecord).where(PaymentRecord.provider_reference == txn_ref)
        ).scalars().first()
        assert payment.status == "completed"
        assert entitlement_service.get_active_entitlement(db_session, user.id, product.id) is not None

    def test_pending_approval_refund_does_not_yet_apply(self, db_session):
        """Mission 9: a real captured Paddle Sandbox refund reported
        `status: "pending_approval"` on `adjustment.created` - proof that
        `adjustment.created` is not itself confirmation the refund happened.
        Until a later event reports approval, the payment/entitlement must
        be untouched."""
        provider, user, product, sub_ref, txn_ref = self._paid_subscription(db_session, "refund-pending-product")

        _send(db_session, provider, _adjustment_event(
            str(uuid.uuid4()), txn_ref, "refunded", 2000, adjustment_status="pending_approval",
        ))
        db_session.commit()

        payment = db_session.execute(
            select(PaymentRecord).where(PaymentRecord.provider_reference == txn_ref)
        ).scalars().first()
        assert payment.status == "completed", "a pending_approval adjustment must not mark the payment refunded"
        assert payment.refunded_amount_cents is None
        assert entitlement_service.get_active_entitlement(db_session, user.id, product.id) is not None, (
            "a pending_approval adjustment must not revoke entitlement before Paddle approves it"
        )

    def test_approved_refund_after_pending_applies_effect(self, db_session):
        """The natural follow-up to the pending case above: once Paddle
        reports the adjustment as approved (via `adjustment.updated` in
        real Paddle), the refund/revocation applies exactly then."""
        provider, user, product, sub_ref, txn_ref = self._paid_subscription(db_session, "refund-approved-product")

        _send(db_session, provider, _adjustment_event(
            str(uuid.uuid4()), txn_ref, "refunded", 2000, adjustment_status="pending_approval",
        ))
        db_session.commit()
        _send(db_session, provider, _adjustment_event(
            str(uuid.uuid4()), txn_ref, "refunded", 2000,
            event_type="adjustment.updated", adjustment_status="approved",
        ))
        db_session.commit()

        payment = db_session.execute(
            select(PaymentRecord).where(PaymentRecord.provider_reference == txn_ref)
        ).scalars().first()
        assert payment.status == "refunded"
        assert payment.refunded_amount_cents == 2000
        assert entitlement_service.get_active_entitlement(db_session, user.id, product.id) is None

    def test_rejected_adjustment_never_applies(self, db_session):
        provider, user, product, sub_ref, txn_ref = self._paid_subscription(db_session, "refund-rejected-product")

        _send(db_session, provider, _adjustment_event(
            str(uuid.uuid4()), txn_ref, "refunded", 2000, adjustment_status="rejected",
        ))
        db_session.commit()

        payment = db_session.execute(
            select(PaymentRecord).where(PaymentRecord.provider_reference == txn_ref)
        ).scalars().first()
        assert payment.status == "completed"
        assert entitlement_service.get_active_entitlement(db_session, user.id, product.id) is not None

    def test_chargeback_with_unverified_status_still_revokes_immediately(self, db_session):
        """Mission 10 audit: there is no real captured Paddle chargeback
        event, so the refund-verified `pending_approval`/`rejected`
        vocabulary must NOT be applied to chargebacks - that would be
        inventing an unproven lifecycle transition, and in the wrong
        (customer-favoring, revenue-risking) direction. A chargeback must
        keep revoking immediately regardless of any `adjustment_status`
        value a real payload might one day carry."""
        provider, user, product, sub_ref, txn_ref = self._paid_subscription(db_session, "chargeback-pending-product")

        _send(db_session, provider, _adjustment_event(
            str(uuid.uuid4()), txn_ref, "disputed", adjustment_status="pending_approval",
        ))
        db_session.commit()

        payment = db_session.execute(
            select(PaymentRecord).where(PaymentRecord.provider_reference == txn_ref)
        ).scalars().first()
        assert payment.status == "disputed", (
            "a chargeback must not be held back by a status vocabulary only ever proven for refunds"
        )
        assert entitlement_service.get_active_entitlement(db_session, user.id, product.id) is None

    def test_refund_referencing_unknown_transaction_fails_safely(self, db_session):
        provider = FakeBillingProvider()
        journal = _send(db_session, provider, _adjustment_event(str(uuid.uuid4()), "txn_never_existed", "refunded", 100))
        db_session.commit()
        assert journal.status == "failed"
        assert "txn_never_existed" in (journal.failure_reason or "")
