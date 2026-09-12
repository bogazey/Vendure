from __future__ import annotations

from enum import Enum


class Plan(str, Enum):
    FREE = "free"
    PRO = "pro"
    CREATOR = "creator"


class SubscriptionProvider(str, Enum):
    """Explicit, canonical distinction between real paid income and internal
    promotional access - see Subscription.provider in commercial_models.py.
    Never inferred from the presence/absence of a Paddle subscription id;
    always set explicitly at write time (webhook processing for PADDLE,
    gift_subscription_service for GIFTED) so revenue/analytics queries can
    filter on it directly instead of guessing."""

    PADDLE = "paddle"
    GIFTED = "gifted"


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
    GIFT_SUBSCRIPTION_GRANTED = "gift_subscription_granted"
    GIFT_SUBSCRIPTION_CHANGED = "gift_subscription_changed"
    GIFT_SUBSCRIPTION_REVOKED = "gift_subscription_revoked"


class AnalyticsEventType(str, Enum):
    """The full, closed set of analytics events Loady records. Anything not
    in this list is rejected outright - see analytics_service.py and
    docs/ANALYTICS.md for which of these are browser- vs server-generated."""

    PAGE_VIEW = "page_view"
    ANALYZE_STARTED = "analyze_started"
    ANALYZE_COMPLETED = "analyze_completed"
    ANALYZE_FAILED = "analyze_failed"
    DOWNLOAD_STARTED = "download_started"
    DOWNLOAD_COMPLETED = "download_completed"
    DOWNLOAD_FAILED = "download_failed"
    SIGNUP_COMPLETED = "signup_completed"
    PLAN_UPGRADED = "plan_upgraded"
    PLAN_DOWNGRADED = "plan_downgraded"
    SUBSCRIPTION_CANCELLED = "subscription_cancelled"
    # Admin-granted gifted subscriptions - deliberately separate event types
    # from PLAN_UPGRADED/PLAN_DOWNGRADED/SUBSCRIPTION_CANCELLED (which are
    # only ever recorded from real Paddle webhook processing - see
    # paddle_service.py) so gifted activity can never be mixed into paid
    # plan-movement/revenue reporting (see analytics_service.get_revenue).
    GIFTED_SUBSCRIPTION_GRANTED = "gifted_subscription_granted"
    GIFTED_SUBSCRIPTION_CHANGED = "gifted_subscription_changed"
    GIFTED_SUBSCRIPTION_REVOKED = "gifted_subscription_revoked"


class AnalyticsFailureCategory(str, Enum):
    """Sanitized, admin-safe failure buckets - never a raw exception message,
    stack trace, or yt-dlp output (those stay in server logs only)."""

    UNSUPPORTED_SOURCE = "unsupported_source"
    METADATA_FAILURE = "metadata_failure"
    FORMAT_UNAVAILABLE = "format_unavailable"
    DOWNLOAD_FAILURE = "download_failure"
    PROCESSING_FAILURE = "processing_failure"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    OTHER = "other"


class AdPlacementId(str, Enum):
    """Stable identifiers for the fixed set of ad placements the frontend
    can render (see components/AdSlot.tsx). Adding a new placement means
    adding a value here plus a migration seeding its row - never a free-form
    string, so the admin Ads page and AdSlot always agree on what exists."""

    LANDING_DOWNLOADER = "LANDING_DOWNLOADER"
    DOWNLOAD_RESULT = "DOWNLOAD_RESULT"
    USER_DASHBOARD = "USER_DASHBOARD"
    DOWNLOAD_HISTORY = "DOWNLOAD_HISTORY"
