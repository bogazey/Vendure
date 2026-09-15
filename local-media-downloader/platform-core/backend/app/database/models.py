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
    # Mission 6 (Phase 22): bumped by auth_service.sign_out_all_sessions -
    # any still-valid central session_access JWT minted before the bump
    # carries the OLD epoch and is rejected on its very next use
    # (api/deps.py::get_optional_user), rather than living out its full
    # access_token_ttl_minutes after a "sign out everywhere."
    security_epoch: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Mission 6 continuation (Phase 19): the target of an in-progress,
    # not-yet-confirmed email change - `email` itself never changes until
    # the NEW address is verified (EmailChangeToken below). NULL means no
    # change is pending.
    pending_new_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
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


class EmailChangeToken(Base):
    """Mission 6 continuation (Phase 19): a verified email-change flow -
    `new_email` is only ever written to `User.email` once this specific
    token is redeemed (`auth_service.confirm_email_change`), never
    immediately at request time. Single-use, short-lived, hashed exactly
    like every other token in this schema."""

    __tablename__ = "email_change_tokens"

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=_id("ect"))
    user_id: Mapped[str] = mapped_column(String(48), ForeignKey("users.id"), index=True, nullable=False)
    new_email: Mapped[str] = mapped_column(String(320), nullable=False)
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
    # Mission 6 continuation (Grand Admin product onboarding): free-text
    # blurb shown in Grand Admin/Account Portal, and whether this product
    # should appear in a user-facing "discover more products" listing
    # before it's necessarily `status == "live"` (a product can be
    # discoverable while still "building", e.g. a public beta waitlist).
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_discoverable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
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

    # --- Mission 6 (Phase 41): where/how to deliver outbound product
    # webhooks for this client's product. `webhook_signing_secret_
    # encrypted` holds the AES-256-GCM envelope from
    # `app/security/secret_encryption.py` (mirrors Loady's
    # `token_encryption_service.py` pattern exactly) - never plaintext.
    # `None` means this client has not opted into outbound webhooks;
    # events destined for it simply are not delivered.
    webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    webhook_signing_secret_encrypted: Mapped[str | None] = mapped_column(String(400), nullable=True)


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
    e.g. `loady`/`free` and `demo-a`/`free` are two distinct rows.

    Mission 6 continuation (Product Subscription Manager): every field
    below is admin-configurable per product, independently - Loady having
    3 plans and Gamey having 3 differently-named, differently-capable
    plans requires zero code branching anywhere, only different rows.
    `current_version_id` is a soft reference (no DB-level FK) to
    `plan_versions.id` - kept soft specifically to avoid a circular FK
    between `plans`/`plan_versions` at the schema level; application code
    (`catalog_service.py`) is the only writer of this column and always
    validates the target version belongs to this same plan first."""

    __tablename__ = "plans"
    __table_args__ = (UniqueConstraint("product_id", "slug", name="uq_plan_product_slug"),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=_id("plan"))
    product_id: Mapped[str] = mapped_column(String(40), ForeignKey("products.id"), index=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Total-order rank for upgrade/downgrade comparison WITHIN a product
    # (higher = more capable) - "downgrade" is simply a transition to a
    # lower rank, so no separate PlanTransitionRule table is needed for
    # V1's linear-tier commerce model (mission-brief: "do not
    # over-engineer unsupported commerce models").
    upgrade_rank: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    gifted_eligible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    trial_eligible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    current_version_id: Mapped[str | None] = mapped_column(String(48), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, onupdate=_now, nullable=False)


class PlanVersion(Base):
    """An immutable, published snapshot of a plan's capability set
    (mission-brief continuation: "existing users must retain the exact
    entitlement/version... agreement they are currently assigned to until
    explicitly changed"). `capability_snapshot` is a frozen `{key:
    value}` copy taken from live `PlanEntitlement` rows at publish time -
    once `status` is `published`, a version's `capability_snapshot` is
    never mutated again; a capability change publishes a NEW version
    instead. `Subscription`/`GiftedAccess`/`PromotionAccess` rows pin the
    version they were granted against (`plan_version_id`) so a later
    catalog edit cannot silently change what an existing subscriber is
    contractually entitled to."""

    __tablename__ = "plan_versions"
    __table_args__ = (UniqueConstraint("plan_id", "version_number", name="uq_plan_version_number"),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=_id("plver"))
    plan_id: Mapped[str] = mapped_column(String(48), ForeignKey("plans.id"), index=True, nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    capability_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(48), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class Price(Base):
    """One purchasable (or historical) price point for a plan
    (mission-brief continuation: "a plan must NOT simply contain one
    price"). Prices are append-only with respect to `amount_cents`/
    `currency`/`interval` - "editing a price" in the admin API always
    means retiring this row (`is_active=False`, `retired_at` set) and
    creating a new one, never mutating the amount in place, which is what
    makes "changing the public price must not silently mutate... the
    historical price of existing users" true structurally: a
    `Subscription` pins `price_id` at creation and that row's amount
    never changes underneath it."""

    __tablename__ = "prices"

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=_id("price"))
    product_id: Mapped[str] = mapped_column(String(40), ForeignKey("products.id"), index=True, nullable=False)
    plan_id: Mapped[str] = mapped_column(String(48), ForeignKey("plans.id"), index=True, nullable=False)
    # Soft reference, same reasoning as Plan.current_version_id - a price
    # may be pinned to the specific plan version it was published
    # alongside, but this is optional (many products won't need it).
    plan_version_id: Mapped[str | None] = mapped_column(String(48), nullable=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_price_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    interval: Mapped[str] = mapped_column(String(20), nullable=False)
    interval_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)
    retired_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


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
    # Pinned at grant time (nullable soft reference) - a NULL here means
    # "predates plan versioning," resolved via live PlanEntitlement rows
    # exactly like before (see capability_service's version-aware path).
    plan_version_id: Mapped[str | None] = mapped_column(String(48), nullable=True)
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

    # --- Mission 6 (Phase 11): ledger detail, all additive/nullable so no
    # existing V1 row or caller is affected. `None` means "not provided by
    # the processor" (mission-brief: "do NOT fabricate unavailable
    # values") - never defaulted to 0.
    subscription_id: Mapped[str | None] = mapped_column(String(48), ForeignKey("subscriptions.id"), nullable=True)
    tax_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fee_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    net_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    refunded_amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    occurred_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


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


# =============================================================================
# Mission 6: capability / entitlement-definition registry (Phases 5-6)
# =============================================================================


class EntitlementDefinition(Base):
    """A single, typed, product-scoped capability, e.g.
    `loady` / `download.max_resolution` / integer. Data-driven so a new
    capability never requires a Python conditional change (mission-brief
    Phase 6) - only a new row here plus a `PlanEntitlement` value per plan
    that grants it."""

    __tablename__ = "entitlement_definitions"
    __table_args__ = (UniqueConstraint("product_id", "key", name="uq_entitlement_definition_product_key"),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=_id("capdef"))
    product_id: Mapped[str] = mapped_column(String(40), ForeignKey("products.id"), index=True, nullable=False)
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    value_type: Mapped[str] = mapped_column(String(10), nullable=False)
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # Only meaningful (and only ever read) when value_type == "enum" - the
    # closed set of legal `value_string` values, e.g. ["480p","720p","4k"].
    allowed_values: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)


class PlanEntitlement(Base):
    """The typed value a specific `Plan` grants for one
    `EntitlementDefinition`. Exactly one of `value_boolean` /
    `value_integer` / `value_string` is populated, matching
    `EntitlementDefinition.value_type` - enforced in
    `capability_service.set_plan_entitlement`, not by a DB CHECK
    constraint (SQLite/Postgres portability - see mission-brief Phase 44
    discussion in V2_ARCHITECTURE_AUDIT.md).

    `value_integer = -1` is the reserved sentinel for "unlimited" (used by
    the effective-entitlement engine's max-wins merge rule for integer
    capabilities - see ENTITLEMENT_ENGINE.md)."""

    __tablename__ = "plan_entitlements"
    __table_args__ = (UniqueConstraint("plan_id", "entitlement_definition_id", name="uq_plan_entitlement"),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=_id("plent"))
    plan_id: Mapped[str] = mapped_column(String(48), ForeignKey("plans.id"), index=True, nullable=False)
    entitlement_definition_id: Mapped[str] = mapped_column(
        String(48), ForeignKey("entitlement_definitions.id"), index=True, nullable=False
    )
    value_boolean: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    value_integer: Mapped[int | None] = mapped_column(Integer, nullable=True)
    value_string: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, onupdate=_now, nullable=False)


# =============================================================================
# Mission 6: subscriptions / billing abstraction (Phases 8-11)
# =============================================================================


class Subscription(Base):
    """A provider-neutral recurring subscription. Platform Core understands
    period/status/cancellation shape without being locked to Paddle
    (mission-brief Phase 8) - `provider` is free-text, exactly like
    `PaymentRecord.provider` (see BILLING.md). One row per real provider
    subscription; `SubscriptionItem` (below) allows more than one plan per
    subscription later without a schema change."""

    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint("provider", "provider_subscription_ref", name="uq_subscription_provider_ref"),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=_id("sub"))
    user_id: Mapped[str] = mapped_column(String(48), ForeignKey("users.id"), index=True, nullable=False)
    product_id: Mapped[str] = mapped_column(String(40), ForeignKey("products.id"), index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_customer_ref: Mapped[str] = mapped_column(String(200), nullable=False)
    provider_subscription_ref: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    # Pinned at creation - the historical-price-preservation guarantee
    # (see `Price`'s own docstring) depends on this never being
    # repointed at a different Price row after the fact.
    price_id: Mapped[str | None] = mapped_column(String(48), ForeignKey("prices.id"), nullable=True)
    plan_version_id: Mapped[str | None] = mapped_column(String(48), nullable=True)
    current_period_start: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    canceled_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    # Mission 8 (Billing Ownership Transition): the `occurred_at` of the
    # most recent webhook event actually APPLIED to this row's
    # status/period fields - never advanced by an event whose own
    # `occurred_at` is older than this (see subscription_service.
    # upsert_subscription's out-of-order guard). `None` until the first
    # event is applied, which always wins regardless of timestamp.
    last_event_occurred_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, onupdate=_now, nullable=False)


class SubscriptionItem(Base):
    """One plan line within a subscription. V1 billing only ever creates a
    single item per subscription; the table exists so a future
    multi-plan-per-subscription provider event does not require a schema
    migration (mission-brief Phase 8)."""

    __tablename__ = "subscription_items"

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=_id("subit"))
    subscription_id: Mapped[str] = mapped_column(String(48), ForeignKey("subscriptions.id"), index=True, nullable=False)
    plan_id: Mapped[str] = mapped_column(String(48), ForeignKey("plans.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class BillingWebhookEvent(Base):
    """Idempotent journal of every inbound billing-provider webhook
    (mission-brief Phase 10). `(provider, provider_event_id)` is unique -
    receiving the same event twice is a silent no-op at the DB level, not
    just an application-level check, closing the race where two
    concurrent deliveries of the same event both pass an application-level
    "have I seen this?" query before either commits."""

    __tablename__ = "billing_webhook_events"
    __table_args__ = (
        UniqueConstraint("provider", "provider_event_id", name="uq_billing_webhook_event"),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=_id("whe"))
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(200), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


# =============================================================================
# Mission 6: gifted access v2 (Phase 13)
# =============================================================================


class GiftedAccess(Base):
    """The historical/detail record for a gift, separate from the single
    mutable `Entitlement` row (see V2_ARCHITECTURE_AUDIT.md §4 - a
    re-gift previously overwrote the prior grant's detail with no
    first-class record). A new grant is always a new row here; only
    `entitlement_service`'s single-row-per-product cache is updated in
    place. This table never contacts, references, or implies a
    `PaymentRecord` (mission-brief Phase 13: "gift must never contact
    billing provider").

    Mission 11: this is also Platform Core's persisted shadow/source
    record for a gift that ORIGINATED in an external system (so far, only
    Loady's own `Subscription(provider="gifted")` rows) - `external_ref`
    (see below) is what makes materializing one idempotent, and once
    created this row is independently authoritative: nothing reads back
    from the external system afterward (see docs/platform/
    BILLING_OWNERSHIP_TRANSITION.md §6c and `gift_service.
    materialize_external_gift`). `external_ref` is `NULL` for every
    ordinary admin-granted gift (`grant_gift`), exactly as before this
    mission."""

    __tablename__ = "gifted_access"

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=_id("gift"))
    user_id: Mapped[str] = mapped_column(String(48), ForeignKey("users.id"), index=True, nullable=False)
    product_id: Mapped[str] = mapped_column(String(40), ForeignKey("products.id"), index=True, nullable=False)
    plan_id: Mapped[str] = mapped_column(String(48), ForeignKey("plans.id"), nullable=False)
    plan_version_id: Mapped[str | None] = mapped_column(String(48), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    granted_by: Mapped[str] = mapped_column(String(48), ForeignKey("users.id"), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    revoked_by: Mapped[str | None] = mapped_column(String(48), ForeignKey("users.id"), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)
    # Mission 11: a stable identifier for the external record this gift was
    # materialized from (e.g. "loady:gift:<loady_subscription_id>") - the
    # idempotency key for `gift_service.materialize_external_gift`, so
    # repeated migration/backfill runs never create a duplicate. `NULL` for
    # every gift granted directly in Platform Core.
    external_ref: Mapped[str | None] = mapped_column(String(200), unique=True, nullable=True)


# =============================================================================
# Mission 6: bundles (Phases 15-16)
# =============================================================================


class Bundle(Base):
    """An ecosystem bundle, e.g. a future "Creator Suite" (mission-brief
    Phase 15). No real commercial pricing is created unless explicitly
    configured - this is architecture, not a live offer."""

    __tablename__ = "bundles"

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=_id("bundle"))
    slug: Mapped[str] = mapped_column(String(60), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)


class BundleProductPlan(Base):
    """One (product, plan) a bundle grants. A bundle grants at most one
    plan per product (V1 simplification, documented in BUNDLES.md)."""

    __tablename__ = "bundle_product_plans"
    __table_args__ = (UniqueConstraint("bundle_id", "product_id", name="uq_bundle_product"),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=_id("bpp"))
    bundle_id: Mapped[str] = mapped_column(String(48), ForeignKey("bundles.id"), index=True, nullable=False)
    product_id: Mapped[str] = mapped_column(String(40), ForeignKey("products.id"), nullable=False)
    plan_id: Mapped[str] = mapped_column(String(48), ForeignKey("plans.id"), nullable=False)


class BundleAccess(Base):
    """A user's ownership of a bundle (mission-brief Phase 16 lifecycle:
    activate / upgrade / expire). Independent of any per-product
    `Subscription`/`GiftedAccess` row - expiring a bundle never deletes or
    modifies an independent per-product grant the user separately holds
    (checked explicitly in `bundle_service` and its tests)."""

    __tablename__ = "bundle_access"

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=_id("bacc"))
    user_id: Mapped[str] = mapped_column(String(48), ForeignKey("users.id"), index=True, nullable=False)
    bundle_id: Mapped[str] = mapped_column(String(48), ForeignKey("bundles.id"), index=True, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    subscription_id: Mapped[str | None] = mapped_column(String(48), ForeignKey("subscriptions.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, onupdate=_now, nullable=False)


# =============================================================================
# Mission 6: outbox / product webhooks (Phases 41-43)
# =============================================================================


class OutboxEvent(Base):
    """Database-backed transactional outbox (mission-brief Phase 42) - a
    state mutation and its outbox row are written in the same DB
    transaction/session, so an event is never lost if the process crashes
    between mutating state and enqueuing the event, and never delivered
    for a mutation that itself rolled back. Delivery is a separate,
    idempotent step (`outbox_service.deliver_pending`) that products
    verify via HMAC signature, exactly like the billing-webhook direction
    but outbound."""

    __tablename__ = "outbox_events"

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=_id("obx"))
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    product_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("products.id"), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, index=True, nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)


# =============================================================================
# Mission 6: service-to-service authentication (Phases 36-37)
# =============================================================================


class ServiceGrant(Base):
    """A service-scoped (client-credentials) capability grant for an
    existing `OAuthClient` acting as itself, not on behalf of any user
    (mission-brief Phase 36). Deliberately a separate table rather than a
    new column bag on `OAuthClient`, so a client with no `ServiceGrant`
    rows simply cannot use the client-credentials grant at all (fails
    closed). `scope` is a single service-scope string, e.g.
    `"service:entitlements:read"` - one row per scope, so revoking one
    capability never requires parsing/rewriting a packed string."""

    __tablename__ = "service_grants"
    __table_args__ = (UniqueConstraint("client_id", "scope", name="uq_service_grant"),)

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=_id("svcgrant"))
    client_id: Mapped[str] = mapped_column(String(60), ForeignKey("oauth_clients.client_id"), index=True, nullable=False)
    scope: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)


# =============================================================================
# Mission 6 continuation: promotions / trials (distinct from gifted/paid)
# =============================================================================


class PromotionAccess(Base):
    """A time-boxed, non-payment access grant that is explicitly NOT a
    gift (mission brief: "promotion and trial must remain distinct from
    gifted/paid/bundle/internal"). `kind` distinguishes a marketing
    promotion (often tied to a `source_code`) from a product trial - both
    share the same lifecycle shape, so one table with a `kind` column,
    not two near-identical tables. Like `GiftedAccess`, this NEVER
    creates or references a `PaymentRecord` - a promotion/trial cannot
    generate revenue any more than a gift can."""

    __tablename__ = "promotion_access"

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=_id("promo"))
    user_id: Mapped[str] = mapped_column(String(48), ForeignKey("users.id"), index=True, nullable=False)
    product_id: Mapped[str] = mapped_column(String(40), ForeignKey("products.id"), index=True, nullable=False)
    plan_id: Mapped[str] = mapped_column(String(48), ForeignKey("plans.id"), nullable=False)
    plan_version_id: Mapped[str | None] = mapped_column(String(48), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # "promotion" | "trial"
    source_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    granted_by: Mapped[str | None] = mapped_column(String(48), ForeignKey("users.id"), nullable=True)
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)


# =============================================================================
# Mission 6 continuation: account closure (Phase 39 minimum)
# =============================================================================


class AccountClosureRequest(Base):
    """The safe minimum lifecycle (mission brief: "do not implement
    irreversible deletion casually"). No code path anywhere reachable
    from this table performs physical row deletion or PII anonymization -
    that remains explicitly unsupported/future work (see
    ACCOUNT_DELETION.md)."""

    __tablename__ = "account_closure_requests"

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=_id("close"))
    user_id: Mapped[str] = mapped_column(String(48), ForeignKey("users.id"), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="requested", nullable=False)  # requested|confirmed|closing|closed|canceled
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    canceled_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
