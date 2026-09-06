import uuid
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api import routes_billing as routes
from app.api.deps import get_current_user, get_db
from app.database.commercial_models import Subscription
from app.models.commercial_enums import Plan, BillingPeriod
from app.models.commercial_schemas import CheckoutRequest
from app.services.auth_service import auth_service
from app.services import paddle_service


@pytest.fixture
def billing(db_session, monkeypatch):
    user = auth_service.signup(db_session, f"bill-{uuid.uuid4().hex}@example.com", "password123!").user
    sub = Subscription(user_id=user.id, provider="paddle", provider_subscription_id="sub_" + uuid.uuid4().hex[:26],
                       provider_customer_id="ctm_owned", plan="pro", status="active")
    db_session.add(sub); db_session.flush()
    live = {"id": sub.provider_subscription_id, "customer_id": "ctm_owned", "status": "active",
            "collection_mode": "automatic", "items": [{"price": {"id": "pri_pro"}, "quantity": 1}]}
    client = Mock()
    client.get_subscription.return_value = {"data": live}
    monkeypatch.setattr(routes, "paddle_client", client)
    monkeypatch.setattr(paddle_service, "_price_id_for", lambda *args: "pri_creator")
    monkeypatch.setattr(paddle_service, "_plan_and_period_for_price_id", lambda price: (Plan.PRO, BillingPeriod.MONTHLY))
    return user, sub, live, client


@pytest.mark.parametrize("action", ["cancel", "resume", "change-plan"])
def test_actions_wait_for_webhook(billing, db_session, action):
    user, sub, live, client = billing
    if action == "resume": live["scheduled_change"] = {"action": "cancel"}
    result = routes.manage_subscription(action, CheckoutRequest(plan="creator", billing_period="monthly"), user, db_session)
    assert result == {"status": "pending"}
    assert sub.plan == "pro" and not sub.cancel_at_period_end
    if action == "cancel": client.cancel_subscription.assert_called_once_with(sub.provider_subscription_id)
    elif action == "resume": client.update_subscription.assert_called_once_with(sub.provider_subscription_id, {"scheduled_change": None})
    else:
        sent = client.update_subscription.call_args.args[1]
        assert sent["items"] == [{"price_id": "pri_creator", "quantity": 1}]
        assert sent["on_payment_failure"] == "prevent_change"


def test_resume_rejects_pause(billing, db_session):
    user, sub, live, client = billing
    live["scheduled_change"] = {"action": "pause"}
    with pytest.raises(routes.HTTPException): routes.manage_subscription("resume", None, user, db_session)
    client.update_subscription.assert_not_called()


def test_cancel_is_idempotent(billing, db_session):
    user, sub, live, client = billing
    live["scheduled_change"] = {"action": "cancel"}
    routes.manage_subscription("cancel", None, user, db_session)
    client.cancel_subscription.assert_not_called()


def test_payment_returns_only_public_checkout(billing, db_session, monkeypatch):
    user, sub, live, client = billing
    monkeypatch.setattr(routes, "get_commercial_settings", lambda: type("S", (), {"paddle_client_token": "test_public", "paddle_env": "sandbox"})())
    client.payment_transaction.return_value = {"data": {"id": "txn_owned", "secret": "not-for-browser"}}
    assert routes.update_payment_method(user, db_session) == {"transaction_id": "txn_owned", "client_token": "test_public", "environment": "sandbox"}
    client.create_customer_portal_session.assert_not_called()


def test_invoice_cannot_access_other_subscription(billing, db_session):
    user, sub, live, client = billing
    client.get_transaction.return_value = {"data": {"subscription_id": "sub_someone_else"}}
    with pytest.raises(routes.HTTPException) as error: routes.transaction_invoice("txn_" + "a" * 26, user, db_session)
    assert error.value.status_code == 404
    client.invoice.assert_not_called()


def test_invoice_is_direct_pdf(billing, db_session):
    user, sub, live, client = billing
    client.get_transaction.return_value = {"data": {"subscription_id": sub.provider_subscription_id}}
    client.invoice.return_value = {"data": {"url": "https://example.com/invoice.pdf"}}
    assert routes.transaction_invoice("txn_" + "a" * 26, user, db_session)["url"].endswith(".pdf")
    client.create_customer_portal_session.assert_not_called()


def test_history_scopes_and_filters(billing, db_session):
    user, sub, live, client = billing
    client.list_transactions.return_value = {"data": [{"id": "txn_other", "subscription_id": "sub_other"}]}
    assert routes.payment_history(None, user, db_session) == {"items": [], "next": None}
    client.list_transactions.assert_called_once_with(sub.provider_subscription_id, None)


@pytest.mark.parametrize("path", ["subscription/cancel", "subscription/resume", "subscription/change-plan", "payment-method"])
def test_routes_require_login(path, db_session):
    app = FastAPI(); app.include_router(routes.router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: (_ for _ in ()).throw(routes.HTTPException(401))
    with TestClient(app) as client: assert client.post("/api/billing/" + path).status_code == 401


@pytest.mark.asyncio
async def test_existing_subscription_cannot_start_checkout(billing, db_session):
    user, *_ = billing
    with pytest.raises(routes.HTTPException) as error:
        await routes.create_checkout(CheckoutRequest(plan="creator", billing_period="annual"), user, db_session)
    assert error.value.status_code == 409


@pytest.mark.parametrize("action,expected", [("cancel", True), ("pause", False), ("resume", False), (None, False)])
def test_webhook_only_cancel_sets_flag(billing, db_session, action, expected):
    user, sub, live, client = billing
    live["scheduled_change"] = {"action": action} if action else None
    paddle_service._upsert_subscription_from_event(db_session, live)
    assert sub.cancel_at_period_end is expected
