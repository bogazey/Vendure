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


class PaymentStatus(str, Enum):
    """A PaymentRecord is the ONLY thing that may ever be counted as
    revenue (mission-brief section 36) — an Entitlement, however granted,
    is never itself proof of payment."""

    COMPLETED = "completed"
    REFUNDED = "refunded"
    FAILED = "failed"
