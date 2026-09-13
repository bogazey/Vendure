"""The provider-neutral billing interface (mission-brief Phase 9)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class CheckoutSession:
    url: str
    provider_reference: str


@dataclass
class NormalizedSubscription:
    provider_subscription_ref: str
    provider_customer_ref: str
    status: str
    current_period_start: datetime | None
    current_period_end: datetime | None
    cancel_at_period_end: bool


@dataclass
class NormalizedEvent:
    """The shape every provider's raw webhook payload is translated into
    before touching any Platform Core table - `subscription_service`/
    `webhook_service` only ever see this, never a raw Paddle (or future
    provider) payload shape."""

    provider_event_id: str
    event_type: str
    provider_subscription_ref: str | None
    provider_customer_ref: str | None
    occurred_at: datetime
    amount_cents: int | None
    currency: str | None
    status: str | None
    raw: dict
    # Whatever the checkout call originally attached (mission-brief Phase
    # 10 needs a way to resolve "which user/product/plan does this
    # subscription belong to" on the very first webhook for it, before any
    # Subscription row exists yet) - e.g. `{"user_id": ..., "product_id":
    # ..., "plan_id": ...}`. `None` if the provider payload carried none.
    custom_data: dict | None = None


class BillingProvider(ABC):
    """One implementation per real (or fake, for tests) payment processor.
    No method here may be called against a live/production processor
    during this mission (mission-brief Phase 9/56) - `PaddleBillingProvider`
    only implements the pieces that require no live network call
    (webhook verification + event normalization); everything else raises
    `BillingProviderNotConfiguredError` until real sandbox credentials are
    wired in and exercised outside this mission."""

    name: str

    @abstractmethod
    def create_checkout(self, *, user_id: str, product_id: str, plan_id: str, success_url: str) -> CheckoutSession:
        ...

    @abstractmethod
    def get_subscription(self, provider_subscription_ref: str) -> NormalizedSubscription | None:
        ...

    @abstractmethod
    def cancel_subscription(self, provider_subscription_ref: str) -> None:
        ...

    @abstractmethod
    def resume_subscription(self, provider_subscription_ref: str) -> None:
        ...

    @abstractmethod
    def change_plan(self, provider_subscription_ref: str, new_price_ref: str) -> None:
        ...

    @abstractmethod
    def open_customer_portal(self, provider_customer_ref: str) -> str:
        ...

    @abstractmethod
    def verify_webhook(self, raw_body: bytes, headers: dict[str, str]) -> bool:
        ...

    @abstractmethod
    def normalize_event(self, raw_body: bytes) -> NormalizedEvent:
        ...


class BillingProviderNotConfiguredError(RuntimeError):
    """Raised by a real provider's live-network methods when no real
    credentials are configured - deliberately loud rather than silently
    returning a fake success, so nothing in this mission can accidentally
    look like a working live integration when it isn't (mission-brief:
    "clearly mark the real integration as untested")."""
