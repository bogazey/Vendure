"""Validated enum values shared across Platform Core — mirrors Loady's
`commercial_enums.py` pattern (plain `str, Enum` so values serialize
naturally in JSON and Pydantic models validate against them directly).
"""
from __future__ import annotations

from enum import Enum


class UserStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"


class ProductStatus(str, Enum):
    LIVE = "live"
    BUILDING = "building"
    PLANNED = "planned"


class MembershipStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class EntitlementSource(str, Enum):
    """How an entitlement came to exist. Only PADDLE (and, in a future
    real integration, another real payment processor) is ever revenue —
    see docs/platform/BILLING.md. Every other source is explicitly
    non-revenue, including GIFTED/INTERNAL, which must never be counted
    as a paid conversion (mission-brief sections 10/36)."""

    FREE = "free"
    PADDLE = "paddle"
    GIFTED = "gifted"
    PROMOTION = "promotion"
    TRIAL = "trial"
    INTERNAL = "internal"
    LIFETIME = "lifetime"
    BUNDLE = "bundle"


class EntitlementStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class RoleSlug(str, Enum):
    """Generic role + scope, not one hard-coded role per product (mission-
    brief section 17). `scope` on RoleAssignment is either the literal
    string "global" or "product:<slug>"."""

    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    SUPPORT = "support"
    FINANCE = "finance"
    USER = "user"


GLOBAL_SCOPE = "global"


def product_scope(product_slug: str) -> str:
    return f"product:{product_slug}"


class AuditAction(str, Enum):
    USER_SIGNUP = "user_signup"
    USER_LOGIN = "user_login"
    USER_STATUS_CHANGED = "user_status_changed"
    ENTITLEMENT_GRANTED = "entitlement_granted"
    ENTITLEMENT_CHANGED = "entitlement_changed"
    ENTITLEMENT_REVOKED = "entitlement_revoked"
    GIFTED_ACCESS_GRANTED = "gifted_access_granted"
    GIFTED_ACCESS_CHANGED = "gifted_access_changed"
    GIFTED_ACCESS_REVOKED = "gifted_access_revoked"
    ROLE_ASSIGNED = "role_assigned"
    ROLE_REVOKED = "role_revoked"
    CLIENT_REGISTERED = "client_registered"
    PRODUCT_CREATED = "product_created"
    LOADY_MIGRATION_IMPORT = "loady_migration_import"

    # Mission 6
    CAPABILITY_DEFINED = "capability_defined"
    PLAN_ENTITLEMENT_SET = "plan_entitlement_set"
    SUBSCRIPTION_CREATED = "subscription_created"
    SUBSCRIPTION_CHANGED = "subscription_changed"
    SUBSCRIPTION_CANCELED = "subscription_canceled"
    WEBHOOK_RECEIVED = "webhook_received"
    WEBHOOK_PROCESSED = "webhook_processed"
    WEBHOOK_REPLAYED = "webhook_replayed"
    GIFT_V2_GRANTED = "gift_v2_granted"
    GIFT_V2_REVOKED = "gift_v2_revoked"
    BUNDLE_CREATED = "bundle_created"
    BUNDLE_ACCESS_GRANTED = "bundle_access_granted"
    BUNDLE_ACCESS_REVOKED = "bundle_access_revoked"
    SERVICE_CLIENT_REGISTERED = "service_client_registered"
    SERVICE_CLIENT_SECRET_ROTATED = "service_client_secret_rotated"
    OUTBOX_EVENT_DELIVERED = "outbox_event_delivered"
    OUTBOX_EVENT_FAILED = "outbox_event_failed"
    PASSWORD_CHANGED = "password_changed"
    SESSION_REVOKED = "session_revoked"
    ALL_SESSIONS_REVOKED = "all_sessions_revoked"


class PaymentStatus(str, Enum):
    """A PaymentRecord is the ONLY thing that may ever be counted as
    revenue (mission-brief section 36) — an Entitlement, however granted,
    is never itself proof of payment."""

    COMPLETED = "completed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"
    FAILED = "failed"


# --- Mission 6: capability / entitlement-definition registry ---------------


class CapabilityValueType(str, Enum):
    """How a `PlanEntitlement.value_*` column should be read. Deliberately
    a closed, small set (mission-brief Phase 6: "avoid arbitrary
    unvalidated JSON whenever a typed model is practical") rather than a
    generic JSON blob."""

    BOOLEAN = "boolean"
    INTEGER = "integer"
    STRING = "string"
    ENUM = "enum"


# --- Mission 6: subscriptions / billing -------------------------------------


class SubscriptionStatus(str, Enum):
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    PAUSED = "paused"
    CANCELED = "canceled"
    EXPIRED = "expired"


class WebhookProcessingStatus(str, Enum):
    PENDING = "pending"
    PROCESSED = "processed"
    FAILED = "failed"


# --- Mission 6: gifted access v2 --------------------------------------------


class GiftStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


# --- Mission 6: bundles ------------------------------------------------------


class BundleStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class BundleAccessStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


# --- Mission 6: outbox (product webhooks) -----------------------------------


class OutboxStatus(str, Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


class EffectiveSourceKind(str, Enum):
    """What kind of row contributed to an effective-entitlement resolution
    (mission-brief Phase 7) — used only in the read-side result object,
    never persisted."""

    LEGACY_ENTITLEMENT = "legacy_entitlement"
    SUBSCRIPTION = "subscription"
    GIFTED = "gifted"
    BUNDLE = "bundle"
