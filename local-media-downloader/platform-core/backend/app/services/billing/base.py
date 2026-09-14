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
    # Mission 8 (Billing Ownership Transition): the payment PROCESSOR's own
    # transaction id - for a `transaction.*` event, the transaction itself;
    # for an `adjustment.*` event (refund/chargeback), the ORIGINAL
    # transaction being adjusted. Deliberately distinct from
    # `provider_event_id` (the webhook envelope's own id) - a refund event
    # naturally references the processor's transaction id, never the id of
    # the webhook that first reported that transaction, so correlating a
    # refund back to its `PaymentRecord` requires this field to exist
    # separately. `None` if the provider payload carried none (never
    # guessed from `provider_event_id`).
    provider_transaction_ref: str | None = None
    # Mission 8: a subscription.* event's own billing-period/cancellation
    # fields. Before this, NOTHING in this module ever threaded these
    # through past subscription creation - `subscription_service.
    # upsert_subscription` always re-used whatever was already on the row,
    # so an update event could never actually advance the renewal date or
    # record a scheduled cancellation. `None` means "this event carried no
    # value for this field," in which case the existing subscription's own
    # value is preserved unchanged - never reset to empty just because one
    # event happened not to mention it.
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    cancel_at_period_end: bool | None = None


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
