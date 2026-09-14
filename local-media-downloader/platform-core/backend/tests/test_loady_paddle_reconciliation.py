"""Mission 8 (Billing Ownership Transition): the full synthetic Paddle
dataset required by the mission, reconciled through the real
`loady_paddle_reconciliation_service.run_reconciliation` against a
temporary SQLite database mirroring Loady's real `users`/`subscriptions`
schema (see LOADY_MIGRATION_AUDIT.md) - no production data, no real
Paddle credentials, no network call. `FakeBillingProvider` throughout.
"""
from __future__ import annotations

import json
import tempfile
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select, text

from app.database.models import Entitlement, PaymentRecord, Product, Subscription, User
from app.models.enums import EntitlementSource
from app.security.passwords import hash_password
from app.services import entitlement_service
from app.services.billing.fake_provider import FakeBillingProvider
from app.services.loady_paddle_reconciliation_service import run_reconciliation

_NOW = datetime.now(timezone.utc)


def _uid() -> str:
    return str(uuid.uuid4())


def _iso(dt: datetime) -> str:
    return dt.isoformat()


@pytest.fixture()
def loady_engine():
    path = tempfile.mktemp(suffix=".db")
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE users (
                id VARCHAR(36) PRIMARY KEY,
                email VARCHAR(320) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                email_verified BOOLEAN NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'active',
                role VARCHAR(20) NOT NULL DEFAULT 'user',
                global_user_id VARCHAR(48)
            )
        """))
        conn.execute(text("""
            CREATE TABLE subscriptions (
                id VARCHAR(36) PRIMARY KEY,
                user_id VARCHAR(36) NOT NULL,
                provider VARCHAR(30) NOT NULL DEFAULT 'paddle',
                provider_customer_id VARCHAR(120),
                provider_subscription_id VARCHAR(120),
                plan VARCHAR(20) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'none',
                current_period_start TEXT,
                current_period_end TEXT,
                cancel_at_period_end BOOLEAN NOT NULL DEFAULT 0,
                granted_by_admin_id VARCHAR(36),
                granted_reason VARCHAR(500),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """))
    yield engine
    engine.dispose()


def _insert_loady_user(engine, *, email, global_user_id=None) -> str:
    user_id = _uid()
    with engine.begin() as conn:
        conn.execute(
            text("""INSERT INTO users (id, email, password_hash, email_verified, created_at, updated_at, status, role, global_user_id)
                    VALUES (:id, :email, :ph, 1, :now, :now, 'active', 'user', :gid)"""),
            {"id": user_id, "email": email, "ph": hash_password("synthetic-password-1"), "now": _iso(_NOW), "gid": global_user_id},
        )
    return user_id


def _insert_loady_subscription(engine, *, user_id, provider="paddle", provider_customer_id=None,
                                provider_subscription_id=None, plan="pro", status="active",
                                current_period_start=None, current_period_end=None,
                                cancel_at_period_end=False, updated_at=None):
    with engine.begin() as conn:
        conn.execute(
            text("""INSERT INTO subscriptions
                    (id, user_id, provider, provider_customer_id, provider_subscription_id, plan, status,
                     current_period_start, current_period_end, cancel_at_period_end, created_at, updated_at)
                    VALUES (:id, :uid, :provider, :pcid, :psid, :plan, :status, :cps, :cpe, :cape, :now, :updated_at)"""),
            {"id": _uid(), "uid": user_id, "provider": provider, "pcid": provider_customer_id,
             "psid": provider_subscription_id, "plan": plan, "status": status,
             "cps": current_period_start, "cpe": current_period_end, "cape": cancel_at_period_end,
             "now": _iso(_NOW), "updated_at": _iso(updated_at or _NOW)},
        )


@pytest.fixture()
def platform_product(db_session):
    if db_session.get(Product, "loady") is None:
        db_session.add(Product(id="loady", name="Loady", domain="loady.cc", status="live"))
        db_session.flush()
    entitlement_service.get_or_create_plan(db_session, "loady", "free", "Free")
    entitlement_service.get_or_create_plan(db_session, "loady", "pro", "Pro")
    entitlement_service.get_or_create_plan(db_session, "loady", "creator", "Creator")
    db_session.commit()
    return db_session.get(Product, "loady")


@pytest.fixture()
def reconciliation_actor(db_session) -> User:
    actor = User(email=f"recon-actor-{_uid()}@example.com", password_hash="x", email_verified=True)
    db_session.add(actor)
    db_session.flush()
    return actor


def _linked_platform_user(db_session, email) -> User:
    """A Platform Core user already linked via Mission 3's identity
    migration - the reconciliation engine's hard prerequisite."""
    user = User(email=email, password_hash=hash_password("x"), email_verified=True)
    db_session.add(user)
    db_session.flush()
    return user


class TestCoreSubscriptionStates:
    """Cases 1-8: active Pro/Creator monthly/annual, cancel-at-period-end,
    already-canceled-but-valid-until-period-end, past due, payment failed."""

    def _reconcile_one(self, db_session, loady_engine, reconciliation_actor, platform_product, **sub_kwargs):
        platform_user = _linked_platform_user(db_session, f"case-{_uid()}@example.com")
        db_session.commit()
        loady_user_id = _insert_loady_user(loady_engine, email=platform_user.email, global_user_id=platform_user.id)
        sub_ref = f"sub_{_uid()}"
        _insert_loady_subscription(loady_engine, user_id=loady_user_id, provider_subscription_id=sub_ref,
                                    provider_customer_id=f"cust_{loady_user_id}", **sub_kwargs)
        report = run_reconciliation(db_session, loady_engine, FakeBillingProvider(), actor=reconciliation_actor, dry_run=False)
        db_session.commit()
        return platform_user, sub_ref, report

    def test_active_pro_monthly(self, db_session, loady_engine, reconciliation_actor, platform_product):
        start, end = _NOW, _NOW + timedelta(days=30)
        user, sub_ref, report = self._reconcile_one(
            db_session, loady_engine, reconciliation_actor, platform_product,
            plan="pro", status="active", current_period_start=_iso(start), current_period_end=_iso(end),
        )
        assert report.summary()["created"] == 1
        sub = db_session.execute(select(Subscription).where(Subscription.provider_subscription_ref == sub_ref)).scalars().first()
        assert sub.status == "active"
        assert sub.current_period_end.date() == end.date()
        ent = entitlement_service.get_active_entitlement(db_session, user.id, "loady")
        assert ent is not None and ent.source == EntitlementSource.PADDLE.value

    def test_active_pro_annual(self, db_session, loady_engine, reconciliation_actor, platform_product):
        start, end = _NOW, _NOW + timedelta(days=365)
        user, sub_ref, report = self._reconcile_one(
            db_session, loady_engine, reconciliation_actor, platform_product,
            plan="pro", status="active", current_period_start=_iso(start), current_period_end=_iso(end),
        )
        sub = db_session.execute(select(Subscription).where(Subscription.provider_subscription_ref == sub_ref)).scalars().first()
        assert (sub.current_period_end - sub.current_period_start).days > 300, "annual period must be preserved distinctly from monthly"

    def test_active_creator_monthly(self, db_session, loady_engine, reconciliation_actor, platform_product):
        user, sub_ref, report = self._reconcile_one(
            db_session, loady_engine, reconciliation_actor, platform_product,
            plan="creator", status="active", current_period_start=_iso(_NOW), current_period_end=_iso(_NOW + timedelta(days=30)),
        )
        ent = entitlement_service.get_active_entitlement(db_session, user.id, "loady")
        assert ent.plan_id == entitlement_service.get_plan(db_session, "loady", "creator").id

    def test_active_creator_annual(self, db_session, loady_engine, reconciliation_actor, platform_product):
        user, sub_ref, report = self._reconcile_one(
            db_session, loady_engine, reconciliation_actor, platform_product,
            plan="creator", status="active", current_period_start=_iso(_NOW), current_period_end=_iso(_NOW + timedelta(days=365)),
        )
        assert report.summary()["created"] == 1

    def test_cancellation_at_period_end_keeps_entitlement_active(self, db_session, loady_engine, reconciliation_actor, platform_product):
        user, sub_ref, report = self._reconcile_one(
            db_session, loady_engine, reconciliation_actor, platform_product,
            plan="pro", status="active", cancel_at_period_end=True,
            current_period_start=_iso(_NOW), current_period_end=_iso(_NOW + timedelta(days=10)),
        )
        sub = db_session.execute(select(Subscription).where(Subscription.provider_subscription_ref == sub_ref)).scalars().first()
        assert sub.cancel_at_period_end is True
        ent = entitlement_service.get_active_entitlement(db_session, user.id, "loady")
        assert ent is not None, "a scheduled cancellation must never revoke access before the period actually ends"

    def test_already_canceled_but_entitlement_valid_until_period_end(self, db_session, loady_engine, reconciliation_actor, platform_product):
        """The LEGACY `Entitlement` cache is deliberately never auto-
        granted here (see `subscription_service._sync_legacy_entitlement`'s
        own docstring: "the legacy cache is only cleared once truly over" -
        it mirrors an existing grant, it does not itself decide access for
        a subscription reconciled directly into this state). The modern,
        authoritative check is `capability_service.resolve_effective_
        entitlements`, which reads the `Subscription` row directly at
        query time and DOES correctly treat "canceled, current_period_end
        still in the future" as entitled."""
        from app.services import capability_service

        user, sub_ref, report = self._reconcile_one(
            db_session, loady_engine, reconciliation_actor, platform_product,
            plan="pro", status="canceled",
            current_period_start=_iso(_NOW - timedelta(days=20)), current_period_end=_iso(_NOW + timedelta(days=10)),
        )
        result = capability_service.resolve_effective_entitlements(db_session, user.id, "loady")
        assert result.sources, "already-canceled but still within the paid period must remain entitled"
        assert result.sources[0].plan_slug == "pro"

    def test_past_due(self, db_session, loady_engine, reconciliation_actor, platform_product):
        user, sub_ref, report = self._reconcile_one(
            db_session, loady_engine, reconciliation_actor, platform_product,
            plan="pro", status="past_due",
            current_period_start=_iso(_NOW - timedelta(days=5)), current_period_end=_iso(_NOW + timedelta(days=25)),
        )
        ent = entitlement_service.get_active_entitlement(db_session, user.id, "loady")
        assert ent is not None, "past_due is still entitled while payment is retried (matches Loady's own ACTIVE_SUBSCRIPTION_STATUSES)"

    def test_payment_failed_transitions_an_active_subscription_to_past_due(self, db_session, loady_engine, reconciliation_actor, platform_product):
        """Paddle Billing communicates a failed renewal payment via the
        SUBSCRIPTION's own status moving to `past_due` (a
        `subscription.updated` event), not a distinct entitlement-affecting
        event of its own - see PADDLE_RECONCILIATION_STRATEGY.md. This
        proves the transition, not just the static state (see
        `test_past_due` above for that)."""
        platform_user = _linked_platform_user(db_session, f"payfail-{_uid()}@example.com")
        db_session.commit()
        loady_user_id = _insert_loady_user(loady_engine, email=platform_user.email, global_user_id=platform_user.id)
        sub_ref = f"sub_{_uid()}"
        _insert_loady_subscription(loady_engine, user_id=loady_user_id, provider_subscription_id=sub_ref,
                                    plan="pro", status="active",
                                    current_period_start=_iso(_NOW), current_period_end=_iso(_NOW + timedelta(days=30)))

        failed_payment_event = json.dumps({
            "event_id": str(uuid.uuid4()), "event_type": "subscription.updated",
            "occurred_at": _iso(_NOW + timedelta(hours=1)), "subscription_ref": sub_ref, "status": "past_due",
        }).encode("utf-8")

        report = run_reconciliation(
            db_session, loady_engine, FakeBillingProvider(), actor=reconciliation_actor,
            additional_events=[failed_payment_event], dry_run=False,
        )
        db_session.commit()
        sub = db_session.execute(select(Subscription).where(Subscription.provider_subscription_ref == sub_ref)).scalars().first()
        assert sub.status == "past_due"
        assert len(report.reconciled_with_change) == 1


class TestPlanChanges:
    def test_subscription_upgraded_mid_cycle(self, db_session, loady_engine, reconciliation_actor, platform_product):
        platform_user = _linked_platform_user(db_session, f"upgrade-{_uid()}@example.com")
        db_session.commit()
        loady_user_id = _insert_loady_user(loady_engine, email=platform_user.email, global_user_id=platform_user.id)
        sub_ref = f"sub_{_uid()}"
        _insert_loady_subscription(loady_engine, user_id=loady_user_id, provider_subscription_id=sub_ref, plan="pro", status="active")

        upgrade_event = json.dumps({
            "event_id": str(uuid.uuid4()), "event_type": "subscription.updated",
            "occurred_at": _iso(_NOW + timedelta(hours=1)), "subscription_ref": sub_ref, "status": "active",
            "custom_data": {"plan_slug": "creator"},
        }).encode("utf-8")
        run_reconciliation(db_session, loady_engine, FakeBillingProvider(), actor=reconciliation_actor,
                            additional_events=[upgrade_event], dry_run=False)
        db_session.commit()
        ent = entitlement_service.get_active_entitlement(db_session, platform_user.id, "loady")
        assert ent.plan_id == entitlement_service.get_plan(db_session, "loady", "creator").id

    def test_subscription_downgraded_mid_cycle(self, db_session, loady_engine, reconciliation_actor, platform_product):
        platform_user = _linked_platform_user(db_session, f"downgrade-{_uid()}@example.com")
        db_session.commit()
        loady_user_id = _insert_loady_user(loady_engine, email=platform_user.email, global_user_id=platform_user.id)
        sub_ref = f"sub_{_uid()}"
        _insert_loady_subscription(loady_engine, user_id=loady_user_id, provider_subscription_id=sub_ref, plan="creator", status="active")

        downgrade_event = json.dumps({
            "event_id": str(uuid.uuid4()), "event_type": "subscription.updated",
            "occurred_at": _iso(_NOW + timedelta(hours=1)), "subscription_ref": sub_ref, "status": "active",
            "custom_data": {"plan_slug": "pro"},
        }).encode("utf-8")
        run_reconciliation(db_session, loady_engine, FakeBillingProvider(), actor=reconciliation_actor,
                            additional_events=[downgrade_event], dry_run=False)
        db_session.commit()
        ent = entitlement_service.get_active_entitlement(db_session, platform_user.id, "loady")
        assert ent.plan_id == entitlement_service.get_plan(db_session, "loady", "pro").id

    def test_plan_changed_mid_cycle_billing_period_switch(self, db_session, loady_engine, reconciliation_actor, platform_product):
        """Same plan tier, cadence changes (monthly -> annual) mid-cycle -
        the renewal date itself is what carries this, since Platform
        Core's Subscription has no separate billing-period flag (period
        LENGTH is what distinguishes monthly from annual - see
        BILLING_OWNERSHIP_TRANSITION.md's "monthly vs annual" section)."""
        platform_user = _linked_platform_user(db_session, f"cadence-{_uid()}@example.com")
        db_session.commit()
        loady_user_id = _insert_loady_user(loady_engine, email=platform_user.email, global_user_id=platform_user.id)
        sub_ref = f"sub_{_uid()}"
        _insert_loady_subscription(loady_engine, user_id=loady_user_id, provider_subscription_id=sub_ref, plan="pro", status="active",
                                    current_period_start=_iso(_NOW), current_period_end=_iso(_NOW + timedelta(days=30)))

        switch_to_annual = json.dumps({
            "event_id": str(uuid.uuid4()), "event_type": "subscription.updated",
            "occurred_at": _iso(_NOW + timedelta(hours=1)), "subscription_ref": sub_ref, "status": "active",
            "current_period_start": _iso(_NOW), "current_period_end": _iso(_NOW + timedelta(days=365)),
        }).encode("utf-8")
        run_reconciliation(db_session, loady_engine, FakeBillingProvider(), actor=reconciliation_actor,
                            additional_events=[switch_to_annual], dry_run=False)
        db_session.commit()
        sub = db_session.execute(select(Subscription).where(Subscription.provider_subscription_ref == sub_ref)).scalars().first()
        assert (sub.current_period_end - sub.current_period_start).days > 300


class TestWebhookDeliveryEdgeCases:
    def _bootstrap_and_replay(self, db_session, loady_engine, reconciliation_actor, extra_events):
        platform_user = _linked_platform_user(db_session, f"webhook-{_uid()}@example.com")
        db_session.commit()
        loady_user_id = _insert_loady_user(loady_engine, email=platform_user.email, global_user_id=platform_user.id)
        sub_ref = f"sub_{_uid()}"
        _insert_loady_subscription(loady_engine, user_id=loady_user_id, provider_subscription_id=sub_ref, plan="pro", status="active",
                                    updated_at=_NOW)
        report = run_reconciliation(db_session, loady_engine, FakeBillingProvider(), actor=reconciliation_actor,
                                     additional_events=extra_events, dry_run=False)
        db_session.commit()
        sub = db_session.execute(select(Subscription).where(Subscription.provider_subscription_ref == sub_ref)).scalars().first()
        return sub, report

    def test_duplicate_webhook_delivery(self, db_session, loady_engine, reconciliation_actor, platform_product):
        event_id = str(uuid.uuid4())
        body = json.dumps({
            "event_id": event_id, "event_type": "subscription.updated",
            "occurred_at": _iso(_NOW + timedelta(hours=1)), "subscription_ref": "PLACEHOLDER", "status": "past_due",
        })
        # subscription_ref filled after bootstrap creates the sub_ref - use a helper that reuses the same ref twice.
        platform_user = _linked_platform_user(db_session, f"dupwh-{_uid()}@example.com")
        db_session.commit()
        loady_user_id = _insert_loady_user(loady_engine, email=platform_user.email, global_user_id=platform_user.id)
        sub_ref = f"sub_{_uid()}"
        _insert_loady_subscription(loady_engine, user_id=loady_user_id, provider_subscription_id=sub_ref, plan="pro", status="active")
        real_body = json.dumps({
            "event_id": event_id, "event_type": "subscription.updated",
            "occurred_at": _iso(_NOW + timedelta(hours=1)), "subscription_ref": sub_ref, "status": "past_due",
        }).encode("utf-8")

        report = run_reconciliation(db_session, loady_engine, FakeBillingProvider(), actor=reconciliation_actor,
                                     additional_events=[real_body, real_body], dry_run=False)
        db_session.commit()
        sub = db_session.execute(select(Subscription).where(Subscription.provider_subscription_ref == sub_ref)).scalars().first()
        assert sub.status == "past_due"
        # Both deliveries are "processed" in the report (the pipeline
        # itself returns the same journal both times), but only the FIRST
        # actually changed anything.
        changed = [r for r in report.reconciled_with_change if r["provider_subscription_id"] == sub_ref]
        assert len(changed) == 1, "a duplicate delivery must never be counted as a second real change"

    def test_delayed_webhook_still_applies_when_genuinely_newer(self, db_session, loady_engine, reconciliation_actor, platform_product):
        platform_user = _linked_platform_user(db_session, f"delayed-{_uid()}@example.com")
        db_session.commit()
        loady_user_id = _insert_loady_user(loady_engine, email=platform_user.email, global_user_id=platform_user.id)
        sub_ref = f"sub_{_uid()}"
        _insert_loady_subscription(loady_engine, user_id=loady_user_id, provider_subscription_id=sub_ref, plan="pro", status="active",
                                    updated_at=_NOW)
        # Arrives late (well after the bootstrap event's own delivery) but
        # its OWN occurred_at is still after the bootstrap's - a delayed,
        # but still in-order, delivery.
        delayed = json.dumps({
            "event_id": str(uuid.uuid4()), "event_type": "subscription.updated",
            "occurred_at": _iso(_NOW + timedelta(days=1)), "subscription_ref": sub_ref, "status": "canceled",
        }).encode("utf-8")
        run_reconciliation(db_session, loady_engine, FakeBillingProvider(), actor=reconciliation_actor,
                            additional_events=[delayed], dry_run=False)
        db_session.commit()
        sub = db_session.execute(select(Subscription).where(Subscription.provider_subscription_ref == sub_ref)).scalars().first()
        assert sub.status == "canceled"

    def test_out_of_order_webhook_is_ignored(self, db_session, loady_engine, reconciliation_actor, platform_product):
        platform_user = _linked_platform_user(db_session, f"outoforder-{_uid()}@example.com")
        db_session.commit()
        loady_user_id = _insert_loady_user(loady_engine, email=platform_user.email, global_user_id=platform_user.id)
        sub_ref = f"sub_{_uid()}"
        # Loady's own snapshot is already fairly recent (updated_at = now + 2 days).
        _insert_loady_subscription(loady_engine, user_id=loady_user_id, provider_subscription_id=sub_ref, plan="pro", status="active",
                                    updated_at=_NOW + timedelta(days=2))
        # An event claiming to have happened BEFORE that snapshot's own
        # timestamp arrives during replay - it must not undo the newer
        # bootstrapped state.
        stale = json.dumps({
            "event_id": str(uuid.uuid4()), "event_type": "subscription.updated",
            "occurred_at": _iso(_NOW - timedelta(days=1)), "subscription_ref": sub_ref, "status": "canceled",
        }).encode("utf-8")
        run_reconciliation(db_session, loady_engine, FakeBillingProvider(), actor=reconciliation_actor,
                            additional_events=[stale], dry_run=False)
        db_session.commit()
        sub = db_session.execute(select(Subscription).where(Subscription.provider_subscription_ref == sub_ref)).scalars().first()
        assert sub.status == "active", "an out-of-order event older than the bootstrapped snapshot must never win"


class TestRefundsChargebacksAndDisputes:
    def _bootstrap_with_payment(self, db_session, loady_engine, reconciliation_actor):
        platform_user = _linked_platform_user(db_session, f"payref-{_uid()}@example.com")
        db_session.commit()
        loady_user_id = _insert_loady_user(loady_engine, email=platform_user.email, global_user_id=platform_user.id)
        sub_ref = f"sub_{_uid()}"
        txn_ref = f"txn_{_uid()}"
        _insert_loady_subscription(loady_engine, user_id=loady_user_id, provider_subscription_id=sub_ref, plan="pro", status="active")
        transaction_event = json.dumps({
            "event_id": str(uuid.uuid4()), "event_type": "transaction.completed",
            "occurred_at": _iso(_NOW + timedelta(hours=1)), "subscription_ref": sub_ref,
            "transaction_ref": txn_ref, "amount_cents": 2000, "currency": "USD",
        }).encode("utf-8")
        run_reconciliation(db_session, loady_engine, FakeBillingProvider(), actor=reconciliation_actor,
                            additional_events=[transaction_event], dry_run=False)
        db_session.commit()
        return platform_user, sub_ref, txn_ref

    def test_full_refund(self, db_session, loady_engine, reconciliation_actor, platform_product):
        user, sub_ref, txn_ref = self._bootstrap_with_payment(db_session, loady_engine, reconciliation_actor)
        refund = json.dumps({
            "event_id": str(uuid.uuid4()), "event_type": "adjustment.created",
            "occurred_at": _iso(_NOW + timedelta(hours=2)), "transaction_ref": txn_ref, "status": "refunded", "amount_cents": 2000,
        }).encode("utf-8")
        run_reconciliation(db_session, loady_engine, FakeBillingProvider(), actor=reconciliation_actor,
                            additional_events=[refund], dry_run=False)
        db_session.commit()
        payment = db_session.execute(select(PaymentRecord).where(PaymentRecord.provider_reference == txn_ref)).scalars().first()
        assert payment.status == "refunded"
        assert entitlement_service.get_active_entitlement(db_session, user.id, "loady") is None

    def test_partial_refund(self, db_session, loady_engine, reconciliation_actor, platform_product):
        user, sub_ref, txn_ref = self._bootstrap_with_payment(db_session, loady_engine, reconciliation_actor)
        refund = json.dumps({
            "event_id": str(uuid.uuid4()), "event_type": "adjustment.created",
            "occurred_at": _iso(_NOW + timedelta(hours=2)), "transaction_ref": txn_ref, "status": "refunded", "amount_cents": 500,
        }).encode("utf-8")
        run_reconciliation(db_session, loady_engine, FakeBillingProvider(), actor=reconciliation_actor,
                            additional_events=[refund], dry_run=False)
        db_session.commit()
        payment = db_session.execute(select(PaymentRecord).where(PaymentRecord.provider_reference == txn_ref)).scalars().first()
        assert payment.status == "partially_refunded"
        assert entitlement_service.get_active_entitlement(db_session, user.id, "loady") is not None

    def test_chargeback_dispute(self, db_session, loady_engine, reconciliation_actor, platform_product):
        user, sub_ref, txn_ref = self._bootstrap_with_payment(db_session, loady_engine, reconciliation_actor)
        dispute = json.dumps({
            "event_id": str(uuid.uuid4()), "event_type": "adjustment.created",
            "occurred_at": _iso(_NOW + timedelta(hours=2)), "transaction_ref": txn_ref, "status": "disputed",
        }).encode("utf-8")
        run_reconciliation(db_session, loady_engine, FakeBillingProvider(), actor=reconciliation_actor,
                            additional_events=[dispute], dry_run=False)
        db_session.commit()
        payment = db_session.execute(select(PaymentRecord).where(PaymentRecord.provider_reference == txn_ref)).scalars().first()
        assert payment.status == "disputed"
        assert entitlement_service.get_active_entitlement(db_session, user.id, "loady") is None


class TestGiftedFinancialSeparationAndDataAnomalies:
    def test_user_with_both_paid_and_gifted_entitlement(self, db_session, loady_engine, reconciliation_actor, platform_product):
        platform_user = _linked_platform_user(db_session, f"both-{_uid()}@example.com")
        db_session.commit()
        loady_user_id = _insert_loady_user(loady_engine, email=platform_user.email, global_user_id=platform_user.id)
        sub_ref = f"sub_{_uid()}"
        _insert_loady_subscription(loady_engine, user_id=loady_user_id, provider="gifted", provider_subscription_id=None,
                                    provider_customer_id=None, plan="creator", status="active")
        _insert_loady_subscription(loady_engine, user_id=loady_user_id, provider="paddle", provider_subscription_id=sub_ref,
                                    plan="pro", status="active")

        # Simulate Mission 3 already having imported the gifted grant.
        entitlement_service.grant_or_change(
            db_session, platform_user, platform_user, "loady", "creator", EntitlementSource.GIFTED, None, reason="pre-existing gift",
        )
        db_session.commit()

        report = run_reconciliation(db_session, loady_engine, FakeBillingProvider(), actor=reconciliation_actor, dry_run=False)
        db_session.commit()

        gifted_entries = [g for g in report.gifted_preserved if g["loady_user_id"] == loady_user_id]
        assert len(gifted_entries) == 1
        assert gifted_entries[0]["also_has_paid_subscription"] is True

        # Paid subscription reconciliation must win: exactly ONE
        # entitlement row, now sourced from Paddle, never two.
        entitlements = db_session.execute(
            select(Entitlement).where(Entitlement.user_id == platform_user.id, Entitlement.product_id == "loady")
        ).scalars().all()
        assert len(entitlements) == 1, "paid and gifted must never coexist as two separate entitlement rows"
        assert entitlements[0].source == EntitlementSource.PADDLE.value
        assert entitlements[0].plan_id == entitlement_service.get_plan(db_session, "loady", "pro").id

    def test_orphaned_paddle_customer_reference(self, db_session, loady_engine, reconciliation_actor, platform_product):
        platform_user = _linked_platform_user(db_session, f"orphancust-{_uid()}@example.com")
        db_session.commit()
        loady_user_id = _insert_loady_user(loady_engine, email=platform_user.email, global_user_id=platform_user.id)
        _insert_loady_subscription(loady_engine, user_id=loady_user_id, provider_customer_id="cust_orphan_123",
                                    provider_subscription_id=None, plan="pro", status="none")

        report = run_reconciliation(db_session, loady_engine, FakeBillingProvider(), actor=reconciliation_actor, dry_run=False)
        db_session.commit()
        assert len(report.orphaned_customer) == 1
        assert report.orphaned_customer[0]["provider_customer_id"] == "cust_orphan_123"
        assert report.summary()["created"] == 0

    def test_orphaned_subscription_reference_without_identity_migration(self, db_session, loady_engine, reconciliation_actor, platform_product):
        # No global_user_id at all - Mission 3's identity migration has
        # not run for this user yet.
        loady_user_id = _insert_loady_user(loady_engine, email=f"unmigrated-{_uid()}@example.com", global_user_id=None)
        sub_ref = f"sub_{_uid()}"
        _insert_loady_subscription(loady_engine, user_id=loady_user_id, provider_subscription_id=sub_ref, plan="pro", status="active")

        report = run_reconciliation(db_session, loady_engine, FakeBillingProvider(), actor=reconciliation_actor, dry_run=False)
        db_session.commit()
        assert len(report.orphaned_subscription) == 1
        assert report.orphaned_subscription[0]["provider_subscription_id"] == sub_ref
        assert db_session.execute(select(Subscription).where(Subscription.provider_subscription_ref == sub_ref)).scalars().first() is None

    def test_local_record_disagrees_with_simulated_paddle_state(self, db_session, loady_engine, reconciliation_actor, platform_product):
        """Loady's own local snapshot says active; a synthetic, chronologically
        NEWER Paddle-shaped event says canceled - the newer event wins and
        the disagreement is surfaced in the report, never silently
        resolved."""
        platform_user = _linked_platform_user(db_session, f"disagree-{_uid()}@example.com")
        db_session.commit()
        loady_user_id = _insert_loady_user(loady_engine, email=platform_user.email, global_user_id=platform_user.id)
        sub_ref = f"sub_{_uid()}"
        _insert_loady_subscription(loady_engine, user_id=loady_user_id, provider_subscription_id=sub_ref, plan="pro", status="active",
                                    updated_at=_NOW)
        newer_paddle_truth = json.dumps({
            "event_id": str(uuid.uuid4()), "event_type": "subscription.updated",
            "occurred_at": _iso(_NOW + timedelta(hours=6)), "subscription_ref": sub_ref, "status": "canceled",
        }).encode("utf-8")

        report = run_reconciliation(db_session, loady_engine, FakeBillingProvider(), actor=reconciliation_actor,
                                     additional_events=[newer_paddle_truth], dry_run=False)
        db_session.commit()

        disagreements = [r for r in report.reconciled_with_change if r["provider_subscription_id"] == sub_ref]
        assert len(disagreements) == 1
        assert disagreements[0]["before"]["status"] == "active"
        assert disagreements[0]["after"]["status"] == "canceled"

    def test_duplicate_local_references(self, db_session, loady_engine, reconciliation_actor, platform_product):
        platform_user = _linked_platform_user(db_session, f"duplocal-{_uid()}@example.com")
        db_session.commit()
        loady_user_id = _insert_loady_user(loady_engine, email=platform_user.email, global_user_id=platform_user.id)
        shared_ref = f"sub_{_uid()}"
        _insert_loady_subscription(loady_engine, user_id=loady_user_id, provider_subscription_id=shared_ref, plan="pro", status="active")
        _insert_loady_subscription(loady_engine, user_id=loady_user_id, provider_subscription_id=shared_ref, plan="creator", status="active")

        report = run_reconciliation(db_session, loady_engine, FakeBillingProvider(), actor=reconciliation_actor, dry_run=False)
        db_session.commit()
        assert len(report.duplicate_local_reference) == 1
        assert shared_ref in report.duplicate_local_reference[0]["duplicate_refs"]
        # Refused to guess - nothing written for this user's paid subscription at all.
        assert db_session.execute(select(Subscription).where(Subscription.provider_subscription_ref == shared_ref)).scalars().first() is None


class TestDryRunAndIdempotency:
    def test_dry_run_performs_zero_writes(self, db_session, loady_engine, reconciliation_actor, platform_product):
        platform_user = _linked_platform_user(db_session, f"dryrun-{_uid()}@example.com")
        db_session.commit()
        loady_user_id = _insert_loady_user(loady_engine, email=platform_user.email, global_user_id=platform_user.id)
        sub_ref = f"sub_{_uid()}"
        _insert_loady_subscription(loady_engine, user_id=loady_user_id, provider_subscription_id=sub_ref, plan="pro", status="active")

        report = run_reconciliation(db_session, loady_engine, FakeBillingProvider(), actor=reconciliation_actor, dry_run=True)
        assert report.summary()["created"] == 1  # the report reflects what WOULD happen
        assert db_session.execute(select(Subscription).where(Subscription.provider_subscription_ref == sub_ref)).scalars().first() is None, (
            "a dry run must perform zero writes"
        )
        assert entitlement_service.get_active_entitlement(db_session, platform_user.id, "loady") is None

    def test_running_reconciliation_twice_is_idempotent(self, db_session, loady_engine, reconciliation_actor, platform_product):
        platform_user = _linked_platform_user(db_session, f"idempotent-{_uid()}@example.com")
        db_session.commit()
        loady_user_id = _insert_loady_user(loady_engine, email=platform_user.email, global_user_id=platform_user.id)
        sub_ref = f"sub_{_uid()}"
        _insert_loady_subscription(loady_engine, user_id=loady_user_id, provider_subscription_id=sub_ref, plan="pro", status="active",
                                    current_period_start=_iso(_NOW), current_period_end=_iso(_NOW + timedelta(days=30)))

        report1 = run_reconciliation(db_session, loady_engine, FakeBillingProvider(), actor=reconciliation_actor, dry_run=False)
        db_session.commit()
        assert report1.summary()["created"] == 1

        report2 = run_reconciliation(db_session, loady_engine, FakeBillingProvider(), actor=reconciliation_actor, dry_run=False)
        db_session.commit()
        assert report2.summary()["created"] == 0
        assert report2.summary()["unchanged"] == 1

        subs = db_session.execute(select(Subscription).where(Subscription.provider_subscription_ref == sub_ref)).scalars().all()
        assert len(subs) == 1, "re-running reconciliation must never duplicate a subscription"
        payments = db_session.execute(select(PaymentRecord).where(PaymentRecord.user_id == platform_user.id)).scalars().all()
        assert len(payments) == 0, "no PaymentRecord is ever fabricated from a bootstrap event alone"
        entitlements = db_session.execute(
            select(Entitlement).where(Entitlement.user_id == platform_user.id, Entitlement.product_id == "loady")
        ).scalars().all()
        assert len(entitlements) == 1, "re-running reconciliation must never duplicate an entitlement"

    def test_no_payment_record_is_fabricated_for_bootstrap_only_reconciliation(self, db_session, loady_engine, reconciliation_actor, platform_product):
        """Loady's own DB has no historical transaction ledger to backfill
        from (see PADDLE_LIVE_INPUTS_REQUIRED.md) - reconciliation must
        never invent one."""
        platform_user = _linked_platform_user(db_session, f"nopayment-{_uid()}@example.com")
        db_session.commit()
        loady_user_id = _insert_loady_user(loady_engine, email=platform_user.email, global_user_id=platform_user.id)
        sub_ref = f"sub_{_uid()}"
        _insert_loady_subscription(loady_engine, user_id=loady_user_id, provider_subscription_id=sub_ref, plan="pro", status="active")

        run_reconciliation(db_session, loady_engine, FakeBillingProvider(), actor=reconciliation_actor, dry_run=False)
        db_session.commit()
        payments = db_session.execute(select(PaymentRecord).where(PaymentRecord.user_id == platform_user.id)).scalars().all()
        assert payments == []
