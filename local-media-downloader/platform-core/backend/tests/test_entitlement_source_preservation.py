"""Mission 11/12 (Billing Ownership Transition - entitlement-source
preservation): the general mechanism that lets an independently-sourced
entitlement (gifted/internal/promotion/trial/lifetime/bundle) survive a
Paddle subscription superseding it, and automatically become effective
again once that Paddle subscription is revoked/refunded/charged back -
without ever re-deriving anything from Loady's database at runtime, and
without ever fabricating a payment record.

Architecture under test (see docs/platform/BILLING_OWNERSHIP_TRANSITION.md
§6c): `GiftedAccess` (and `Subscription`/`BundleAccess`/`PromotionAccess`)
are independent source tables `capability_service.resolve_effective_
entitlements` reads and merges every time - nothing here is a one-off
refund patch. `gift_service.materialize_external_gift` is how a gift that
originated outside Platform Core (so far, only via
`loady_migration_service.py`) becomes a durable, independently-authoritative
`GiftedAccess` row. `subscription_service.suspend_for_billing_event` is how
`webhook_service._apply_adjustment_event` stops a specific Paddle
`Subscription` from contributing, without touching any other source.

Uses `FakeBillingProvider` throughout - no real network call, no Paddle
credentials."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.database.models import Entitlement, GiftedAccess, PaymentRecord, Plan, Product, Subscription, User
from app.models.enums import CapabilityValueType
from app.services import capability_service, entitlement_service, gift_service, webhook_service
from app.services.billing.fake_provider import FakeBillingProvider

_NOW = datetime.now(timezone.utc)


def _uid() -> str:
    return uuid.uuid4().hex[:10]


def _user(db_session, label: str) -> User:
    user = User(email=f"{label}-{_uid()}@example.com", password_hash="x", email_verified=True)
    db_session.add(user)
    db_session.flush()
    return user


def _product(db_session, product_id: str) -> Product:
    if db_session.get(Product, product_id) is None:
        db_session.add(Product(id=product_id, name=product_id, domain=f"{product_id}.example", status="live"))
        db_session.flush()
    return db_session.get(Product, product_id)


def _plans_with_resolution_capability(db_session, product_id: str) -> tuple[Plan, Plan]:
    """Pro/Creator plans with a numeric capability where Creator > Pro -
    lets a test prove "the stronger source's value wins" using the
    engine's real max-merge, not an invented ranking system."""
    pro = entitlement_service.get_or_create_plan(db_session, product_id, "pro", "Pro")
    creator = entitlement_service.get_or_create_plan(db_session, product_id, "creator", "Creator")
    capability_service.define_capability(db_session, product_id, "download.max_resolution", CapabilityValueType.INTEGER)
    db_session.flush()
    capability_service.set_plan_entitlement(db_session, pro, "download.max_resolution", 720)
    capability_service.set_plan_entitlement(db_session, creator, "download.max_resolution", 1080)
    db_session.commit()
    return pro, creator


def _gift_pro(db_session, admin: User, target: User, product_id: str, pro: Plan, *, external_suffix: str | None = None) -> GiftedAccess:
    return gift_service.materialize_external_gift(
        db_session, admin, target, pro,
        external_ref=f"loady:gift:{external_suffix or _uid()}",
        reason="beta tester", granted_at=_NOW - timedelta(days=30), expires_at=None,
    )


def _subscription_created_event(event_id, user_id, product_id, plan_slug, sub_ref, *, occurred_at):
    payload = {
        "event_id": event_id, "event_type": "subscription.created", "occurred_at": occurred_at,
        "subscription_ref": sub_ref, "customer_ref": f"cust_{user_id}", "status": "active",
        "custom_data": {"user_id": user_id, "product_id": product_id, "plan_slug": plan_slug},
    }
    return json.dumps(payload).encode("utf-8")


def _subscription_update_event(event_id, sub_ref, *, status, occurred_at):
    payload = {
        "event_id": event_id, "event_type": "subscription.updated", "occurred_at": occurred_at,
        "subscription_ref": sub_ref, "status": status,
    }
    return json.dumps(payload).encode("utf-8")


def _transaction_event(event_id, sub_ref, amount_cents, currency, *, transaction_ref, occurred_at):
    payload = {
        "event_id": event_id, "event_type": "transaction.completed", "occurred_at": occurred_at,
        "subscription_ref": sub_ref, "amount_cents": amount_cents, "currency": currency,
        "transaction_ref": transaction_ref,
    }
    return json.dumps(payload).encode("utf-8")


def _adjustment_event(event_id, transaction_ref, action_status, amount_cents=None, *, occurred_at):
    payload = {
        "event_id": event_id, "event_type": "adjustment.created", "occurred_at": occurred_at,
        "transaction_ref": transaction_ref, "status": action_status,
    }
    if amount_cents is not None:
        payload["amount_cents"] = amount_cents
        payload["currency"] = "USD"
    return json.dumps(payload).encode("utf-8")


def _send(db_session, provider, body):
    headers = {"fake-signature": provider.sign(body)}
    return webhook_service.receive_webhook(db_session, provider, body, headers)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


class TestGiftSurvivesPaidSupersessionAndReemergesOnRefund:
    def test_gifted_pro_survives_paddle_creator_and_reemerges_after_refund(self, db_session):
        """The mission's own worked example: Gifted Pro -> Paddle Creator
        -> Paddle revoked -> Gifted Pro automatically effective again."""
        admin = _user(db_session, "admin")
        target = _user(db_session, "user")
        product = _product(db_session, f"prod-{_uid()}")
        pro, creator = _plans_with_resolution_capability(db_session, product.id)
        gift = _gift_pro(db_session, admin, target, product.id, pro)
        db_session.commit()

        # Before any Paddle activity: only the gift contributes.
        result = capability_service.resolve_effective_entitlements(db_session, target.id, product.id)
        assert result.capabilities["download.max_resolution"] == 720
        assert len(result.sources) == 1

        provider = FakeBillingProvider()
        sub_ref = f"sub_{_uid()}"
        txn_ref = f"txn_{_uid()}"
        t0 = _NOW - timedelta(days=1)
        _send(db_session, provider, _subscription_created_event(
            str(uuid.uuid4()), target.id, product.id, "creator", sub_ref, occurred_at=_iso(t0),
        ))
        db_session.commit()
        _send(db_session, provider, _transaction_event(
            str(uuid.uuid4()), sub_ref, 2000, "USD", transaction_ref=txn_ref, occurred_at=_iso(t0),
        ))
        db_session.commit()

        # Paddle Creator now supersedes the gift for the single legacy row,
        # but the gift itself must be untouched underneath.
        assert entitlement_service.get_active_entitlement(db_session, target.id, product.id).source == "paddle"
        gift_row = db_session.get(GiftedAccess, gift.id)
        assert gift_row.status == "active", "a Paddle subscription becoming effective must never destroy the gift"
        result = capability_service.resolve_effective_entitlements(db_session, target.id, product.id)
        assert result.capabilities["download.max_resolution"] == 1080
        assert {s.kind for s in result.sources} == {"gifted", "legacy_entitlement"} or "gifted" in {s.kind for s in result.sources}

        # Full refund - only the Paddle source may be affected.
        _send(db_session, provider, _adjustment_event(
            str(uuid.uuid4()), txn_ref, "refunded", 2000, occurred_at=_iso(t0 + timedelta(hours=1)),
        ))
        db_session.commit()

        subscription = db_session.execute(
            select(Subscription).where(Subscription.provider_subscription_ref == sub_ref)
        ).scalars().first()
        assert subscription.status == "refunded"
        gift_row = db_session.get(GiftedAccess, gift.id)
        assert gift_row.status == "active", "refunding the Paddle subscription must never touch the gift"

        # The gift automatically re-emerges as the effective entitlement -
        # no code needed to "restore" it; it was never gone.
        result = capability_service.resolve_effective_entitlements(db_session, target.id, product.id)
        assert result.capabilities["download.max_resolution"] == 720
        assert [s.kind for s in result.sources] == ["gifted"]

        # Revenue/accounting stays Paddle-only: exactly the one real
        # transaction, nothing fabricated by the gift re-emerging.
        payments = db_session.execute(select(PaymentRecord).where(PaymentRecord.user_id == target.id)).scalars().all()
        assert len(payments) == 1
        assert payments[0].status == "refunded"

    def test_gifted_creator_stronger_than_paddle_pro_stays_effective(self, db_session):
        """Also required: Gifted Creator + Paddle Pro coexisting - the
        engine's own max-merge means Creator's stronger numeric capability
        wins, and both sources remain visible (never silently dropped)."""
        admin = _user(db_session, "admin")
        target = _user(db_session, "user")
        product = _product(db_session, f"prod-{_uid()}")
        pro, creator = _plans_with_resolution_capability(db_session, product.id)
        gift_service.materialize_external_gift(
            db_session, admin, target, creator, external_ref=f"loady:gift:{_uid()}",
            reason="partner account", granted_at=_NOW - timedelta(days=10), expires_at=None,
        )
        db_session.commit()

        provider = FakeBillingProvider()
        sub_ref = f"sub_{_uid()}"
        _send(db_session, provider, _subscription_created_event(
            str(uuid.uuid4()), target.id, product.id, "pro", sub_ref, occurred_at=_iso(_NOW),
        ))
        db_session.commit()

        result = capability_service.resolve_effective_entitlements(db_session, target.id, product.id)
        kinds = {s.kind for s in result.sources}
        assert "gifted" in kinds and "legacy_entitlement" in kinds, "both sources must remain effective/visible"
        assert result.capabilities["download.max_resolution"] == 1080, (
            "the stronger (gifted Creator) capability must win the merge, not be shadowed by the paid Pro subscription"
        )


class TestExpiredOrRevokedGiftsNeverResurrect:
    def test_revoked_gift_does_not_reemerge_after_paddle_refund(self, db_session):
        admin = _user(db_session, "admin")
        target = _user(db_session, "user")
        product = _product(db_session, f"prod-{_uid()}")
        pro, creator = _plans_with_resolution_capability(db_session, product.id)
        gift = _gift_pro(db_session, admin, target, product.id, pro)
        gift.status = "revoked"
        db_session.commit()

        provider = FakeBillingProvider()
        sub_ref = f"sub_{_uid()}"
        txn_ref = f"txn_{_uid()}"
        _send(db_session, provider, _subscription_created_event(
            str(uuid.uuid4()), target.id, product.id, "creator", sub_ref, occurred_at=_iso(_NOW),
        ))
        db_session.commit()
        _send(db_session, provider, _transaction_event(
            str(uuid.uuid4()), sub_ref, 2000, "USD", transaction_ref=txn_ref, occurred_at=_iso(_NOW),
        ))
        db_session.commit()
        _send(db_session, provider, _adjustment_event(
            str(uuid.uuid4()), txn_ref, "refunded", 2000, occurred_at=_iso(_NOW + timedelta(hours=1)),
        ))
        db_session.commit()

        result = capability_service.resolve_effective_entitlements(db_session, target.id, product.id)
        assert result.sources == [], "a revoked gift must never resurrect just because the Paddle source went away"

    def test_expired_gift_does_not_reemerge_after_paddle_refund(self, db_session):
        admin = _user(db_session, "admin")
        target = _user(db_session, "user")
        product = _product(db_session, f"prod-{_uid()}")
        pro, creator = _plans_with_resolution_capability(db_session, product.id)
        gift = gift_service.materialize_external_gift(
            db_session, admin, target, pro, external_ref=f"loady:gift:{_uid()}",
            reason="beta", granted_at=_NOW - timedelta(days=60), expires_at=_NOW - timedelta(days=1),
        )
        db_session.commit()

        provider = FakeBillingProvider()
        sub_ref = f"sub_{_uid()}"
        txn_ref = f"txn_{_uid()}"
        _send(db_session, provider, _subscription_created_event(
            str(uuid.uuid4()), target.id, product.id, "creator", sub_ref, occurred_at=_iso(_NOW),
        ))
        db_session.commit()
        _send(db_session, provider, _transaction_event(
            str(uuid.uuid4()), sub_ref, 2000, "USD", transaction_ref=txn_ref, occurred_at=_iso(_NOW),
        ))
        db_session.commit()
        _send(db_session, provider, _adjustment_event(
            str(uuid.uuid4()), txn_ref, "refunded", 2000, occurred_at=_iso(_NOW + timedelta(hours=1)),
        ))
        db_session.commit()

        result = capability_service.resolve_effective_entitlements(db_session, target.id, product.id)
        assert result.sources == [], "an expired gift must never resurrect just because the Paddle source went away"


class TestIsolation:
    def test_product_isolation_a_refund_in_one_product_never_touches_another(self, db_session):
        admin = _user(db_session, "admin")
        target = _user(db_session, "user")
        product_a = _product(db_session, f"prod-a-{_uid()}")
        product_b = _product(db_session, f"prod-b-{_uid()}")
        pro_a, creator_a = _plans_with_resolution_capability(db_session, product_a.id)
        pro_b, _creator_b = _plans_with_resolution_capability(db_session, product_b.id)

        provider = FakeBillingProvider()
        # Product B: an independent Paddle Pro subscription for the SAME user.
        sub_ref_b = f"sub_{_uid()}"
        _send(db_session, provider, _subscription_created_event(
            str(uuid.uuid4()), target.id, product_b.id, "pro", sub_ref_b, occurred_at=_iso(_NOW),
        ))
        db_session.commit()

        # Product A: gift + paddle + refund.
        gift = _gift_pro(db_session, admin, target, product_a.id, pro_a)
        db_session.commit()
        sub_ref_a = f"sub_{_uid()}"
        txn_ref_a = f"txn_{_uid()}"
        _send(db_session, provider, _subscription_created_event(
            str(uuid.uuid4()), target.id, product_a.id, "creator", sub_ref_a, occurred_at=_iso(_NOW),
        ))
        db_session.commit()
        _send(db_session, provider, _transaction_event(
            str(uuid.uuid4()), sub_ref_a, 2000, "USD", transaction_ref=txn_ref_a, occurred_at=_iso(_NOW),
        ))
        db_session.commit()
        _send(db_session, provider, _adjustment_event(
            str(uuid.uuid4()), txn_ref_a, "refunded", 2000, occurred_at=_iso(_NOW + timedelta(hours=1)),
        ))
        db_session.commit()

        # Product B's Paddle Pro subscription must be completely unaffected.
        sub_b = db_session.execute(select(Subscription).where(Subscription.provider_subscription_ref == sub_ref_b)).scalars().first()
        assert sub_b.status == "active"
        result_b = capability_service.resolve_effective_entitlements(db_session, target.id, product_b.id)
        assert result_b.capabilities["download.max_resolution"] == 720

    def test_user_isolation_a_refund_for_one_user_never_touches_another(self, db_session):
        admin = _user(db_session, "admin")
        user1 = _user(db_session, "user1")
        user2 = _user(db_session, "user2")
        product = _product(db_session, f"prod-{_uid()}")
        pro, creator = _plans_with_resolution_capability(db_session, product.id)

        provider = FakeBillingProvider()
        # user2: independent Paddle Pro subscription, never refunded.
        sub_ref_2 = f"sub_{_uid()}"
        _send(db_session, provider, _subscription_created_event(
            str(uuid.uuid4()), user2.id, product.id, "pro", sub_ref_2, occurred_at=_iso(_NOW),
        ))
        db_session.commit()

        # user1: gift + paddle + refund.
        _gift_pro(db_session, admin, user1, product.id, pro)
        db_session.commit()
        sub_ref_1 = f"sub_{_uid()}"
        txn_ref_1 = f"txn_{_uid()}"
        _send(db_session, provider, _subscription_created_event(
            str(uuid.uuid4()), user1.id, product.id, "creator", sub_ref_1, occurred_at=_iso(_NOW),
        ))
        db_session.commit()
        _send(db_session, provider, _transaction_event(
            str(uuid.uuid4()), sub_ref_1, 2000, "USD", transaction_ref=txn_ref_1, occurred_at=_iso(_NOW),
        ))
        db_session.commit()
        _send(db_session, provider, _adjustment_event(
            str(uuid.uuid4()), txn_ref_1, "refunded", 2000, occurred_at=_iso(_NOW + timedelta(hours=1)),
        ))
        db_session.commit()

        sub2 = db_session.execute(select(Subscription).where(Subscription.provider_subscription_ref == sub_ref_2)).scalars().first()
        assert sub2.status == "active"
        result2 = capability_service.resolve_effective_entitlements(db_session, user2.id, product.id)
        assert result2.capabilities["download.max_resolution"] == 720


class TestIdempotencyAndOrdering:
    def test_replayed_refund_webhook_does_not_double_suspend_or_duplicate_sources(self, db_session):
        admin = _user(db_session, "admin")
        target = _user(db_session, "user")
        product = _product(db_session, f"prod-{_uid()}")
        pro, creator = _plans_with_resolution_capability(db_session, product.id)
        _gift_pro(db_session, admin, target, product.id, pro)
        db_session.commit()

        provider = FakeBillingProvider()
        sub_ref = f"sub_{_uid()}"
        txn_ref = f"txn_{_uid()}"
        _send(db_session, provider, _subscription_created_event(
            str(uuid.uuid4()), target.id, product.id, "creator", sub_ref, occurred_at=_iso(_NOW),
        ))
        db_session.commit()
        _send(db_session, provider, _transaction_event(
            str(uuid.uuid4()), sub_ref, 2000, "USD", transaction_ref=txn_ref, occurred_at=_iso(_NOW),
        ))
        db_session.commit()

        refund_body = _adjustment_event(
            str(uuid.uuid4()), txn_ref, "refunded", 2000, occurred_at=_iso(_NOW + timedelta(hours=1)),
        )
        _send(db_session, provider, refund_body)
        db_session.commit()
        _send(db_session, provider, refund_body)  # exact same webhook, delivered twice
        db_session.commit()

        payment = db_session.execute(select(PaymentRecord).where(PaymentRecord.provider_reference == txn_ref)).scalars().first()
        assert payment.refunded_amount_cents == 2000, "a duplicate delivery must never double-apply a refund"
        gifts = db_session.execute(select(GiftedAccess).where(GiftedAccess.user_id == target.id)).scalars().all()
        assert len(gifts) == 1, "a replayed webhook must never duplicate a source record"

    def test_out_of_order_reactivation_never_resurrects_a_refunded_subscription(self, db_session):
        admin = _user(db_session, "admin")
        target = _user(db_session, "user")
        product = _product(db_session, f"prod-{_uid()}")
        pro, creator = _plans_with_resolution_capability(db_session, product.id)
        _gift_pro(db_session, admin, target, product.id, pro)
        db_session.commit()

        provider = FakeBillingProvider()
        sub_ref = f"sub_{_uid()}"
        txn_ref = f"txn_{_uid()}"
        t0 = _NOW
        _send(db_session, provider, _subscription_created_event(
            str(uuid.uuid4()), target.id, product.id, "creator", sub_ref, occurred_at=_iso(t0),
        ))
        db_session.commit()
        _send(db_session, provider, _transaction_event(
            str(uuid.uuid4()), sub_ref, 2000, "USD", transaction_ref=txn_ref, occurred_at=_iso(t0),
        ))
        db_session.commit()

        # The refund's own occurred_at is the LATEST timestamp in this
        # sequence - a stale "still active" update from BEFORE it must
        # never resurrect the subscription once delivered afterward.
        t_refund = t0 + timedelta(hours=2)
        _send(db_session, provider, _adjustment_event(
            str(uuid.uuid4()), txn_ref, "refunded", 2000, occurred_at=_iso(t_refund),
        ))
        db_session.commit()

        stale_reactivation = _subscription_update_event(
            str(uuid.uuid4()), sub_ref, status="active", occurred_at=_iso(t0 + timedelta(hours=1)),
        )
        _send(db_session, provider, stale_reactivation)
        db_session.commit()

        subscription = db_session.execute(
            select(Subscription).where(Subscription.provider_subscription_ref == sub_ref)
        ).scalars().first()
        assert subscription.status == "refunded", "an out-of-order event must never resurrect a refunded subscription"
        result = capability_service.resolve_effective_entitlements(db_session, target.id, product.id)
        assert [s.kind for s in result.sources] == ["gifted"]


def test_materializing_and_reemerging_a_gift_never_creates_a_payment_record(db_session):
    admin = _user(db_session, "admin")
    target = _user(db_session, "user")
    product = _product(db_session, f"prod-{_uid()}")
    pro, creator = _plans_with_resolution_capability(db_session, product.id)
    _gift_pro(db_session, admin, target, product.id, pro)
    db_session.commit()
    assert db_session.execute(select(PaymentRecord).where(PaymentRecord.user_id == target.id)).scalars().first() is None

    provider = FakeBillingProvider()
    sub_ref = f"sub_{_uid()}"
    txn_ref = f"txn_{_uid()}"
    _send(db_session, provider, _subscription_created_event(
        str(uuid.uuid4()), target.id, product.id, "creator", sub_ref, occurred_at=_iso(_NOW),
    ))
    db_session.commit()
    _send(db_session, provider, _transaction_event(
        str(uuid.uuid4()), sub_ref, 2000, "USD", transaction_ref=txn_ref, occurred_at=_iso(_NOW),
    ))
    db_session.commit()
    _send(db_session, provider, _adjustment_event(
        str(uuid.uuid4()), txn_ref, "refunded", 2000, occurred_at=_iso(_NOW + timedelta(hours=1)),
    ))
    db_session.commit()

    # The gift re-emerging as the effective entitlement must never itself
    # fabricate revenue - exactly the one real Paddle transaction exists.
    payments = db_session.execute(select(PaymentRecord).where(PaymentRecord.user_id == target.id)).scalars().all()
    assert len(payments) == 1
