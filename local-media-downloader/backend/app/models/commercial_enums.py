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


class AdminActionType(str, Enum):
    """Administrative action types recorded in AdminActionLog - see
    admin_audit_service.py. Keep this list narrow and additive; it's an
    accountability trail, not a general event bus."""

    GRANT_CREDITS = "grant_credits"
    DISABLE_ACCOUNT = "disable_account"
    REACTIVATE_ACCOUNT = "reactivate_account"
    AD_PLACEMENT_ENABLED = "ad_placement_enabled"
    AD_PLACEMENT_DISABLED = "ad_placement_disabled"
    AD_PLACEMENT_UPDATED = "ad_placement_updated"


class AdPlacementId(str, Enum):
    """Stable identifiers for the fixed set of ad placements the frontend
    can render (see components/AdSlot.tsx). Adding a new placement means
    adding a value here plus a migration seeding its row - never a free-form
    string, so the admin Ads page and AdSlot always agree on what exists."""

    LANDING_DOWNLOADER = "LANDING_DOWNLOADER"
    DOWNLOAD_RESULT = "DOWNLOAD_RESULT"
    USER_DASHBOARD = "USER_DASHBOARD"
    DOWNLOAD_HISTORY = "DOWNLOAD_HISTORY"
