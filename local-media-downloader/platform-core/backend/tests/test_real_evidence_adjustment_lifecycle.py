"""Mission 14: end-to-end proof, using REAL Paddle-shaped payloads (sanitized -
see test_paddle_provider_normalization.py's fixtures for the sanitization
statement) driven through the actual `PaddleBillingProvider` + signature
verification + `webhook_service.receive_webhook` pipeline, that a refund's
pending_approval -> approved transition applies its financial/entitlement
effect EXACTLY ONCE - never on the pending event, exactly once on approval,
and never again if the approval event is redelivered.

This is the one thing this mission's real Sandbox evidence was specifically
captured to prove (see the task's own instruction: "Confirm that pending ->
approved produces the intended effect exactly once"). Everything here uses
`PaddleBillingProvider`, not `FakeBillingProvider`, specifically so the real
field shapes captured in Sandbox flow through the real normalization code,
not a synthetic shortcut."""
from __future__ import annotations

import hashlib
import hmac
import time
import uuid

from sqlalchemy import select

from app.config.settings import get_settings
from app.database.models import PaymentRecord, Product, Subscription, SubscriptionItem, User
from app.models.enums import EntitlementSource
from app.services import entitlement_service, webhook_service
from app.services.billing.paddle_provider import PaddleBillingProvider
from tests.test_paddle_provider_normalization import _real_shaped_refund_payload

_TEST_WEBHOOK_SECRET = "mission-14-test-secret-not-a-real-paddle-secret"


def _sign(body: bytes, secret: str = _TEST_WEBHOOK_SECRET) -> dict[str, str]:
    """Exactly the scheme `PaddleBillingProvider.verify_webhook` and
    Loady's own `paddle_service.verify_webhook_signature` both implement:
    `Paddle-Signature: ts=<unix>;h1=HMAC-SHA256(secret, f"{ts}:{body}")`."""
    ts = str(int(time.time()))
    signed_payload = f"{ts}:{body.decode('utf-8')}"
    h1 = hmac.new(secret.encode("utf-8"), signed_payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return {"Paddle-Signature": f"ts={ts};h1={h1}"}


def _setup_paid_subscription(db_session, monkeypatch) -> tuple[User, str, str, str]:
    """A user with an active Paddle-funded entitlement and a matching
    PaymentRecord for the real transaction_id the captured evidence
    references - the precondition every real refund/dispute assumes."""
    monkeypatch.setattr(get_settings(), "paddle_webhook_secret", _TEST_WEBHOOK_SECRET)

    product_id = f"real-evidence-{uuid.uuid4().hex[:8]}"
    if db_session.get(Product, product_id) is None:
        db_session.add(Product(id=product_id, name=product_id, domain=f"{product_id}.example", status="live"))
        db_session.flush()
    plan = entitlement_service.get_or_create_plan(db_session, product_id, "creator", "Creator")

    user = User(email=f"real-evidence-{uuid.uuid4().hex[:8]}@example.com", password_hash="x", email_verified=True)
    db_session.add(user)
    db_session.flush()

    # Unique per test invocation - the shared test database persists rows
    # across tests in this session (see conftest.py's db_session fixture),
    # and Subscription/PaymentRecord both enforce real uniqueness on these
    # references, exactly as Paddle's own ids are unique in reality.
    unique = uuid.uuid4().hex[:12]
    sub_ref = f"sub_01hxxxxxxxxxxxxxxxxxxxxxx-{unique}"
    txn_ref = f"txn_01hyyyyyyyyyyyyyyyyyyyyyy-{unique}"

    subscription = Subscription(
        user_id=user.id, product_id=product_id, provider="paddle",
        provider_customer_ref="ctm_01hwwwwwwwwwwwwwwwwwwwwww", provider_subscription_ref=sub_ref,
        status="active", current_period_start=None, current_period_end=None, cancel_at_period_end=False,
    )
    db_session.add(subscription)
    db_session.flush()
    db_session.add(SubscriptionItem(subscription_id=subscription.id, plan_id=plan.id, quantity=1))

    payment = PaymentRecord(
        user_id=user.id, product_id=product_id, provider="paddle", provider_reference=txn_ref,
        amount_cents=499, currency="USD", status="completed", subscription_id=subscription.id,
        occurred_at=None,
    )
    db_session.add(payment)

    entitlement_service.grant_or_change(
        db_session, user, user, product_id, "creator", EntitlementSource.PADDLE, None, reason="test setup",
    )
    db_session.commit()
    return user, product_id, sub_ref, txn_ref


def test_pending_approval_then_approved_applies_effect_exactly_once(db_session, monkeypatch):
    user, product_id, sub_ref, txn_ref = _setup_paid_subscription(db_session, monkeypatch)
    provider = PaddleBillingProvider()

    # Real Paddle assigns a distinct event_id to adjustment.created and its
    # later adjustment.updated - two different webhook deliveries for the
    # same underlying adjustment.
    pending_body = _real_shaped_refund_payload(
        status="pending_approval", transaction_id=txn_ref, subscription_id=sub_ref,
        event_id=f"evt_pending_{uuid.uuid4().hex[:12]}",
    )
    journal = webhook_service.receive_webhook(db_session, provider, pending_body, _sign(pending_body))
    db_session.commit()
    assert journal.status == "processed"

    payment = db_session.execute(select(PaymentRecord).where(PaymentRecord.provider_reference == txn_ref)).scalars().first()
    assert payment.status == "completed", "pending_approval must not touch the payment"
    assert payment.refunded_amount_cents is None
    assert entitlement_service.get_active_entitlement(db_session, user.id, product_id) is not None, (
        "pending_approval must not revoke entitlement"
    )

    approved_body = _real_shaped_refund_payload(
        status="approved", event_type="adjustment.updated", transaction_id=txn_ref, subscription_id=sub_ref,
        event_id=f"evt_approved_{uuid.uuid4().hex[:12]}",
    )
    journal = webhook_service.receive_webhook(db_session, provider, approved_body, _sign(approved_body))
    db_session.commit()
    assert journal.status == "processed"

    payment = db_session.execute(select(PaymentRecord).where(PaymentRecord.provider_reference == txn_ref)).scalars().first()
    assert payment.status == "refunded", "approval must apply the refund exactly here"
    assert payment.refunded_amount_cents == 499
    assert entitlement_service.get_active_entitlement(db_session, user.id, product_id) is None, (
        "approval must revoke the Paddle-funded entitlement"
    )


def test_redelivering_the_same_approved_event_never_double_applies(db_session, monkeypatch):
    user, product_id, sub_ref, txn_ref = _setup_paid_subscription(db_session, monkeypatch)
    provider = PaddleBillingProvider()

    pending_body = _real_shaped_refund_payload(
        status="pending_approval", transaction_id=txn_ref, subscription_id=sub_ref,
        event_id=f"evt_pending_{uuid.uuid4().hex[:12]}",
    )
    webhook_service.receive_webhook(db_session, provider, pending_body, _sign(pending_body))
    db_session.commit()

    approved_body = _real_shaped_refund_payload(
        status="approved", event_type="adjustment.updated", transaction_id=txn_ref, subscription_id=sub_ref,
        event_id=f"evt_approved_{uuid.uuid4().hex[:12]}",
    )
    headers = _sign(approved_body)  # same signature/body reused for the "redelivery"
    webhook_service.receive_webhook(db_session, provider, approved_body, headers)
    db_session.commit()
    webhook_service.receive_webhook(db_session, provider, approved_body, headers)  # exact redelivery
    db_session.commit()

    payment = db_session.execute(select(PaymentRecord).where(PaymentRecord.provider_reference == txn_ref)).scalars().first()
    assert payment.refunded_amount_cents == 499, "a redelivered adjustment.updated must never double-refund"
    assert payment.status == "refunded"
