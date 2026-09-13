"""SQLAlchemy ORM models for Platform Core.

Column types follow the same portability rules as Loady's
`commercial_models.py`: string primary keys (never a DB-specific UUID
type), timezone-aware timestamps via `UTCDateTime`, JSON columns for
structured-but-bounded data.

Table groups (mission-brief section 26):
- Identity: `users`, `refresh_tokens`, `email_verification_tokens`,
  `password_reset_tokens`.
- Products/SSO: `products`, `product_memberships`, `oauth_clients`,
  `authorization_codes`, `oauth_refresh_tokens`.
- Entitlements/billing boundary: `plans`, `entitlements`, `payment_records`.
- RBAC: `roles`, `role_assignments`.
- Audit: `audit_logs`.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.db import Base
from app.database.sa_types import UTCDateTime


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _global_user_id() -> str:
    """An immutable global identifier, never the user's email (mission-
    brief section 4) — `usr_` + a UUIDv4 hex, so it is visibly distinct
    from any product's own internal ids at a glance."""
    return f"usr_{uuid.uuid4().hex}"


def _id(prefix: str):
    def _factory() -> str:
        return f"{prefix}_{uuid.uuid4().hex}"

    return _factory


class User(Base):
    """The one, permanent, cross-product identity. Email is an attribute
    (unique, but changeable later without breaking any product's stored
    reference — every reference elsewhere in this schema points at `id`,
    never at `email`)."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=_global_user_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, onupdate=_now, nullable=False)


class RefreshToken(Base):
    """A central-session refresh token. Doubles as the "session" record for
    the account portal's future "active sessions" / "sign out all devices"
    UI (mission-brief section 23) — one row per issued session, revocable
    individually. Only its SHA-256 hash is ever stored, never the raw
    token. No raw IP address is stored (mission-brief section 23) — only a
    coarse, non-identifying label if the caller supplies one."""

    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=_id("rtk"))
    user_id: Mapped[str] = mapped_column(String(48), ForeignKey("users.id"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    remember_me: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    device_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)
    last_used_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=_id("evt"))
    user_id: Mapped[str] = mapped_column(String(48), ForeignKey("users.id"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=_id("prt"))
    user_id: Mapped[str] = mapped_column(String(48), ForeignKey("users.id"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)


class Product(Base):
    """The product registry (mission-brief section 7). `id` is the slug
    itself (e.g. "loady") — short, stable, human-legible, and exactly what
    every other table's `product_id` foreign key references, so nothing
    needs a join just to print a product's name in a log line."""

    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="planned", nullable=False)
    icon_ref: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)


class ProductMembership(Base):
    """Explicit record that a global user has actually touched a given
    product — never created just because a global account exists
    (mission-brief section 8)."""

    __tablename__ = "product_memberships"
    __table_args__ = (UniqueConstraint("user_id", "product_id", name="uq_membership_user_product"),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=_id("mem"))
    user_id: Mapped[str] = mapped_column(String(48), ForeignKey("users.id"), index=True, nullable=False)
    product_id: Mapped[str] = mapped_column(String(40), ForeignKey("products.id"), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)


class OAuthClient(Base):
    """A registered product/service client for the SSO flow (mission-brief
    section 25: no single shared API key — each product is a separately
    identifiable, separately revocable client). `client_secret_hash` is
    null for a public client (none in V1 — both demo products are
    confidential, server-side clients); `redirect_uris` is an exact-match
    allowlist, never a prefix/wildcard match, closing the open-redirect
    class of OAuth vulnerability."""

    __tablename__ = "oauth_clients"

    client_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    product_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("products.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    client_secret_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    redirect_uris: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)


class AuthorizationCode(Base):
    """A single-use, short-lived authorization code (RFC 6749 §4.1 +
    RFC 7636 PKCE). Only the code's SHA-256 hash is stored, exactly like
    Loady's refresh/reset/verification tokens — a stolen DB row alone
    cannot be replayed as a code. `used_at` enforces single-use;
    `expires_at` is checked on top of that (mission-brief section 24)."""

    __tablename__ = "authorization_codes"

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=_id("code"))
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    client_id: Mapped[str] = mapped_column(String(60), ForeignKey("oauth_clients.client_id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(48), ForeignKey("users.id"), nullable=False)
    redirect_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    code_challenge: Mapped[str] = mapped_column(String(255), nullable=False)
    code_challenge_method: Mapped[str] = mapped_column(String(10), nullable=False)
    scope: Mapped[str] = mapped_column(String(255), default="openid profile", nullable=False)
    state: Mapped[str | None] = mapped_column(String(500), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)


class OAuthRefreshToken(Base):
    """A product-scoped refresh token, separate from the central-session
    RefreshToken above — this one is minted to a *client* at the end of
    the code exchange so a product can silently renew its own access token
    without bouncing the user back through /oauth/authorize on every
    expiry, without ever being able to impersonate another client (each
    row is bound to exactly one `client_id`)."""

    __tablename__ = "oauth_refresh_tokens"

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=_id("ortk"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    client_id: Mapped[str] = mapped_column(String(60), ForeignKey("oauth_clients.client_id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(48), ForeignKey("users.id"), nullable=False)
    scope: Mapped[str] = mapped_column(String(255), default="openid profile", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)


class Plan(Base):
    """Product-scoped plans (mission-brief section 9: "do not assume every
    product has the same plans"). `slug` is only unique within a product,
    e.g. `loady`/`free` and `demo-a`/`free` are two distinct rows."""

    __tablename__ = "plans"
    __table_args__ = (UniqueConstraint("product_id", "slug", name="uq_plan_product_slug"),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=_id("plan"))
    product_id: Mapped[str] = mapped_column(String(40), ForeignKey("products.id"), index=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)


class Entitlement(Base):
    """A generic grant of a product-scoped plan to a global user. This is
    the single representation for every access path — paid, gifted,
    trial, promo, lifetime, bundle-derived — distinguished only by
    `source`, never by which table it lives in or which code path wrote
    it (mission-brief section 9). `source` alone decides whether this
    entitlement may ever be counted as revenue (only `paddle`, and only
    when backed by a real `PaymentRecord` — see docs/platform/BILLING.md);
    an Entitlement row by itself is never proof of payment."""

    __tablename__ = "entitlements"

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=_id("ent"))
    user_id: Mapped[str] = mapped_column(String(48), ForeignKey("users.id"), index=True, nullable=False)
    product_id: Mapped[str] = mapped_column(String(40), ForeignKey("products.id"), index=True, nullable=False)
    plan_id: Mapped[str] = mapped_column(String(48), ForeignKey("plans.id"), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    granted_by: Mapped[str | None] = mapped_column(String(48), ForeignKey("users.id"), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, onupdate=_now, nullable=False)


class PaymentRecord(Base):
    """The ONLY table that may ever be summed into a revenue figure
    (mission-brief section 36). A payment may fund one or several
    Entitlement rows (mission-brief section 12, bundles) — this table
    never itself grants access; `entitlement_service` is what does that,
    separately, after a payment is confirmed. Deliberately generic
    (`provider` is a free-text processor name, e.g. "paddle") rather than
    Paddle-specific, since a future product might use a different
    processor — see docs/platform/BILLING.md."""

    __tablename__ = "payment_records"

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=_id("pay"))
    user_id: Mapped[str] = mapped_column(String(48), ForeignKey("users.id"), index=True, nullable=False)
    product_id: Mapped[str] = mapped_column(String(40), ForeignKey("products.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_reference: Mapped[str] = mapped_column(String(200), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)


class Role(Base):
    __tablename__ = "roles"

    slug: Mapped[str] = mapped_column(String(30), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)


class RoleAssignment(Base):
    """`scope` is either the literal string "global" or "product:<slug>"
    (mission-brief section 17) — a generic role+scope pair rather than a
    hard-coded per-product role column, so a new product never requires a
    schema change here."""

    __tablename__ = "role_assignments"
    __table_args__ = (UniqueConstraint("user_id", "role_slug", "scope", name="uq_role_assignment"),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=_id("ra"))
    user_id: Mapped[str] = mapped_column(String(48), ForeignKey("users.id"), index=True, nullable=False)
    role_slug: Mapped[str] = mapped_column(String(30), ForeignKey("roles.slug"), nullable=False)
    scope: Mapped[str] = mapped_column(String(60), nullable=False)
    granted_by: Mapped[str | None] = mapped_column(String(48), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)


class AuditLog(Base):
    """Append-only accountability trail for every privileged Platform Core
    action (mission-brief section 18). `before_state`/`after_state` are
    small, specific JSON snapshots of just the changed fields — never a
    dump of secrets, tokens, password hashes, raw payment data, or
    unnecessary PII (enforced by only ever passing pre-scrubbed dicts from
    the calling service, never a raw model `__dict__`)."""

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=_id("aud"))
    actor_user_id: Mapped[str | None] = mapped_column(String(48), ForeignKey("users.id"), index=True, nullable=True)
    action: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    target_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(48), index=True, nullable=True)
    product_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("products.id"), nullable=True)
    before_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, index=True, nullable=False)


def generate_client_secret() -> str:
    return secrets.token_urlsafe(32)
