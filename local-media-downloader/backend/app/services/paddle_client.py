"""Thin server-side client for the Paddle Billing REST API.

Only ever called with the server-side API key (PADDLE_API_KEY) - never
exposed to the frontend. The frontend only ever sees the public client-side
token (PADDLE_CLIENT_TOKEN) for Paddle.js.

This is intentionally minimal: Paddle Billing checkout itself runs
client-side via Paddle.js against a price ID (see routes_billing.py's
/checkout endpoint, which just returns the price id + client token), so the
backend's job is verifying/processing webhooks (paddle_service.py) plus a
couple of optional management calls (subscription lookup, customer portal).

Management endpoints follow Paddle Billing API v1. Provider calls are mocked
in regression tests; real Sandbox account testing is still required.
"""
from __future__ import annotations

import httpx

from app.config.commercial_settings import get_commercial_settings
from app.config.logging_config import get_logger
from app.utils.exceptions import BillingError

logger = get_logger("paddle_client")


class PaddleClient:
    @staticmethod
    def _base_url() -> str:
        settings = get_commercial_settings()
        return "https://sandbox-api.paddle.com" if settings.paddle_env == "sandbox" else "https://api.paddle.com"

    def _headers(self) -> dict[str, str]:
        api_key = get_commercial_settings().paddle_api_key
        return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    def _request(self, method: str, path: str, **kwargs) -> dict:
        if not get_commercial_settings().paddle_api_key:
            raise BillingError(
                "Billing isn't configured on this server yet (PADDLE_API_KEY missing).",
            )
        try:
            with httpx.Client(base_url=self._base_url(), timeout=15.0) as client:
                response = client.request(method, path, headers=self._headers(), **kwargs)
        except httpx.HTTPError as exc:
            logger.error("Paddle API request failed: %s %s - %s", method, path, exc)
            raise BillingError("Could not reach the billing provider. Please try again.", technical=str(exc)) from exc

        if response.status_code >= 400:
            logger.error("Paddle API error %s on %s %s: %s", response.status_code, method, path, response.text[:500])
            raise BillingError(
                "The billing provider rejected this request.", technical=f"Provider status: {response.status_code}"
            )
        return response.json()

    def get_subscription(self, subscription_id: str) -> dict:
        return self._request("GET", f"/subscriptions/{subscription_id}")

    def cancel_subscription(self, subscription_id: str, effective_from: str = "next_billing_period") -> dict:
        return self._request(
            "POST", f"/subscriptions/{subscription_id}/cancel", json={"effective_from": effective_from}
        )

    def update_subscription(self, subscription_id: str, payload: dict) -> dict:
        return self._request("PATCH", f"/subscriptions/{subscription_id}", json=payload)

    def payment_transaction(self, subscription_id: str) -> dict:
        return self._request("GET", f"/subscriptions/{subscription_id}/update-payment-method-transaction")

    def list_transactions(self, subscription_id: str, after: str | None = None) -> dict:
        params = {"subscription_id": subscription_id, "per_page": 30, "order_by": "id[DESC]"}
        if after:
            params["after"] = after
        return self._request("GET", "/transactions", params=params)

    def get_transaction(self, transaction_id: str) -> dict:
        return self._request("GET", f"/transactions/{transaction_id}")

    def invoice(self, transaction_id: str) -> dict:
        return self._request("GET", f"/transactions/{transaction_id}/invoice", params={"disposition": "inline"})

    def create_customer_portal_session(self, customer_id: str) -> dict:
        return self._request("POST", f"/customers/{customer_id}/portal-sessions", json={})


paddle_client = PaddleClient()
