"""Billing provider abstraction (mission-brief Phase 9).

Platform Core consumes normalized domain events
(`base.NormalizedEvent`/`NormalizedSubscription`) rather than scattering
provider-specific behavior across the rest of the app - `subscription_service`
and `webhook_service` never import `paddle_provider` directly except through
`get_billing_provider`, so adding a second real provider later is a new
module here, not a rewrite of the callers.
"""
from __future__ import annotations

from app.services.billing.base import BillingProvider
from app.services.billing.fake_provider import FakeBillingProvider
from app.services.billing.paddle_provider import PaddleBillingProvider

_PROVIDERS: dict[str, type[BillingProvider]] = {
    "paddle": PaddleBillingProvider,
    "fake": FakeBillingProvider,
}

_instances: dict[str, BillingProvider] = {}


def get_billing_provider(name: str) -> BillingProvider:
    if name not in _instances:
        provider_cls = _PROVIDERS.get(name)
        if provider_cls is None:
            raise ValueError(f"Unknown billing provider '{name}'. Known: {sorted(_PROVIDERS)}.")
        _instances[name] = provider_cls()
    return _instances[name]


__all__ = ["BillingProvider", "get_billing_provider"]
