from __future__ import annotations

from enum import Enum


class Plan(str, Enum):
    FREE = "free"
    PRO = "pro"
    CREATOR = "creator"


class BillingPeriod(str, Enum):
    MONTHLY = "monthly"
    ANNUAL = "annual"


class UserStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"


class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"


class SubscriptionStatus(str, Enum):
    """Internal, normalized subscription state - mapped from whatever the
    billing provider (Paddle) reports, so the rest of the app never has to
    know provider-specific status strings."""

    NONE = "none"  # never subscribed (Free plan)
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    PAUSED = "paused"
    CANCELED = "canceled"


class UsageEventType(str, Enum):
    RESERVE = "reserve"
    COMMIT = "commit"
    REFUND = "refund"
    ADMIN_GRANT = "admin_grant"
    REWARD_GRANT = "reward_grant"


class ReservationStatus(str, Enum):
    RESERVED = "reserved"
    COMMITTED = "committed"
    REFUNDED = "refunded"


class BillingEventStatus(str, Enum):
    PROCESSED = "processed"
    IGNORED = "ignored"
    FAILED = "failed"
