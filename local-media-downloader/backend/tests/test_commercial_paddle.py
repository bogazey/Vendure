"""Paddle webhook signature verification and idempotent event processing -
the backend must trust the webhook as the sole source of subscription truth,
never a frontend checkout redirect."""
import hashlib
import hmac
import time
import uuid

from sqlalchemy import select

from app.database.commercial_models import BillingEvent, Subscription
from app.models.commercial_enums import BillingEventStatus, Plan, SubscriptionStatus
from app.services import paddle_service
from app.services.auth_service import auth_service

SECRET = "whsec_test_secret"


def _sign(body: bytes, secret: str = SECRET, ts: int | None = None) -> str:
    ts = ts or int(time.time())
    signed_payload = f"{ts}:{body.decode()}"
    h1 = hmac.new(secret.encode(), signed_payload.encode(), hashlib.sha256).hexdigest()
    return f"ts={ts};h1={h1}"


class TestSignatureVerification:
    def test_valid_signature_accepted(self):
        body = b'{"hello":"world"}'
        header = _sign(body)
        assert paddle_service.verify_webhook_signature(body, header, SECRET) is True

    def test_wrong_secret_rejected(self):
        body = b'{"hello":"world"}'
        header = _sign(body, secret="whsec_other")
        assert paddle_service.verify_webhook_signature(body, header, SECRET) is False

    def test_tampered_body_rejected(self):
        body = b'{"hello":"world"}'
        header = _sign(body)
        assert paddle_service.verify_webhook_signature(b'{"hello":"tampered"}', header, SECRET) is False

    def test_missing_header_rejected(self):
        assert paddle_service.verify_webhook_signature(b"{}", None, SECRET) is False

    def test_malformed_header_rejected(self):
        assert paddle_service.verify_webhook_signature(b"{}", "not-a-valid-header", SECRET) is False

    def test_empty_secret_rejected(self):
        body = b"{}"
        header = _sign(body, secret="")
        assert paddle_service.verify_webhook_signature(body, header, "") is False


class TestWebhookIdempotency:
    def test_duplicate_event_id_is_a_no_op(self, db_session, monkeypatch):
        monkeypatch.setattr(
            "app.services.paddle_service.get_commercial_settings",
            lambda: type(
                "S",
                (),
                {
                    "paddle_pro_monthly_price_id": "pri_pro_monthly",
                    "paddle_pro_annual_price_id": "pri_pro_annual",
                    "paddle_creator_monthly_price_id": "pri_creator_monthly",
                    "paddle_creator_annual_price_id": "pri_creator_annual",
                },
            )(),
        )
        result = auth_service.signup(db_session, f"paddle-{uuid.uuid4().hex[:10]}@example.com", "correcthorse9!")
        db_session.flush()

        event_id = f"evt_{uuid.uuid4().hex}"
        data = {
            "id": "sub_test123",
            "custom_data": {"user_id": result.user.id},
            "items": [{"price": {"id": "pri_pro_monthly"}}],
            "status": "active",
        }

        status1 = paddle_service.process_webhook_event(db_session, event_id, "subscription.activated", data, "hash1")
        db_session.commit()
        assert status1 == BillingEventStatus.PROCESSED.value

        sub = db_session.execute(
            select(Subscription).where(Subscription.provider_subscription_id == "sub_test123")
        ).scalars().first()
        assert sub is not None
        assert sub.plan == Plan.PRO.value
        assert sub.status == SubscriptionStatus.ACTIVE.value

        # Replay the exact same event id - must not error, must not double-apply.
        status2 = paddle_service.process_webhook_event(
            db_session, event_id, "subscription.activated", {**data, "status": "canceled"}, "hash1"
        )
        db_session.commit()
        assert status2 == status1  # returns the stored result, doesn't reprocess

        sub_after = db_session.execute(
            select(Subscription).where(Subscription.provider_subscription_id == "sub_test123")
        ).scalars().first()
        assert sub_after.status == SubscriptionStatus.ACTIVE.value  # unchanged by the replay

        events = db_session.execute(
            select(BillingEvent).where(BillingEvent.provider_event_id == event_id)
        ).scalars().all()
        assert len(events) == 1  # exactly one billing_events row, not two

    def test_unknown_event_type_is_ignored_but_recorded(self, db_session):
        event_id = f"evt_{uuid.uuid4().hex}"
        status = paddle_service.process_webhook_event(db_session, event_id, "some.future.event", {}, "hash2")
        db_session.commit()
        assert status == BillingEventStatus.IGNORED.value
        assert db_session.get(BillingEvent, event_id) is not None

    def test_webhook_for_unknown_user_id_does_not_crash(self, db_session):
        event_id = f"evt_{uuid.uuid4().hex}"
        data = {"id": "sub_orphan", "custom_data": {"user_id": "does-not-exist"}, "status": "active"}
        status = paddle_service.process_webhook_event(db_session, event_id, "subscription.created", data, "hash3")
        db_session.commit()
        # Doesn't crash, doesn't fabricate a subscription with no owner.
        assert status == BillingEventStatus.PROCESSED.value
        sub = db_session.execute(
            select(Subscription).where(Subscription.provider_subscription_id == "sub_orphan")
        ).scalars().first()
        assert sub is None
