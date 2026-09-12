"""SQLAlchemy ORM models for the commercial layer.

Column types are chosen to be portable between SQLite (local dev) and
PostgreSQL (production): primary keys are UUID strings (String(36)) rather
than a DB-specific UUID type, timestamps are timezone-aware, and JSON columns
use SQLAlchemy's generic JSON type (TEXT-backed on SQLite, native on
Postgres).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.commercial_db import Base
from app.database.sa_types import UTCDateTime


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=_now, onupdate=_now, nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="user", nullable=False)

    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="user")
    usage_periods: Mapped[list["UsagePeriod"]] = relationship(back_populates="user")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(30), default="paddle", nullable=False)
    provider_customer_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    provider_subscription_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    plan: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="none", nullable=False)
    current_period_start: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=_now, onupdate=_now, nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="subscriptions")


class UsagePeriod(Base):
    """The user's current billing/usage window: how many credits (or free
    downloads) they have, and how many they've used. One active row per user
    at a time in practice, but kept as a history table (not upserted) so past
    periods remain auditable."""

    __tablename__ = "usage_periods"
    __table_args__ = (UniqueConstraint("user_id", "period_start", name="uq_usage_period_user_start"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True, nullable=False)
    period_start: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    period_end: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    credits_included: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    credits_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    daily_free_downloads_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_free_reset: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    user: Mapped["User"] = relationship(back_populates="usage_periods")


class UsageEvent(Base):
    """Append-only audit log of every credit lifecycle transition (reserve /
    commit / refund / admin grant / reward grant)."""

    __tablename__ = "usage_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True, nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    download_job_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    event_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)


class Entitlement(Base):
    """Ad-hoc feature grants layered on top of the plan (e.g. an admin grant,
    a promo, a future rewarded-ad unlock) - most feature checks go through
    PlanPolicy instead; this is for exceptions to the plan's normal rules."""

    __tablename__ = "entitlements"
    __table_args__ = (UniqueConstraint("user_id", "feature", name="uq_entitlement_user_feature"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True, nullable=False)
    feature: Mapped[str] = mapped_column(String(60), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    source: Mapped[str] = mapped_column(String(60), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class BillingEvent(Base):
    """Every processed (or rejected) Paddle webhook event, keyed by the
    provider's own event id, so duplicate deliveries are a safe no-op."""

    __tablename__ = "billing_events"

    provider_event_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    # Best-effort denormalized reference for admin display only (see
    # paddle_service._resolve_user_id_for_billing_event) - resolved from the
    # webhook's own custom_data/subscription lookup at write time. Nullable:
    # older rows predate this column, and some event shapes never carry a
    # resolvable user. Never used for any authorization or billing decision.
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), index=True, nullable=True)


class AdminActionLog(Base):
    """Append-only accountability trail for administrative actions - who
    (admin_id) did what (action) to whom (target_user_id) and why (details).
    Deliberately separate from UsageEvent, which is the credit-lifecycle
    ledger and has its own unrelated meaning; overloading it with admin
    actions that aren't credit transactions (e.g. account disable) would
    make that table harder to reason about."""

    __tablename__ = "admin_action_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    admin_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True, nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    target_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), index=True, nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, index=True, nullable=False)


class AdPlacement(Base):
    """Central registry of ad placements the frontend can render (see
    components/AdSlot.tsx) and the admin Ads page can configure. Deliberately
    holds only non-secret, display-safe fields - no API keys, no private ad
    network tokens - since this row is readable by any authenticated user
    (AdSlot needs to know whether its placement is currently enabled)."""

    __tablename__ = "ad_placements"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    description: Mapped[str] = mapped_column(String(240), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    public_slot_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=_now, onupdate=_now, nullable=False
    )


class GuestQuota(Base):
    """Server-side counter for the anonymous "2 free downloads, no account
    required" allowance - see guest_service.py. Keyed by an opaque,
    server-minted token (never a client-chosen value), never linked to a
    User row. `downloads_reserved` is incremented atomically at download
    creation and converted to `downloads_completed` on success (or simply
    decremented again on failure/cancellation) - the same reserve/commit/
    refund shape as usage_service, just counting downloads instead of
    credits, and deliberately never touching real credit/UsagePeriod rows."""

    __tablename__ = "guest_quotas"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    downloads_reserved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    downloads_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)
    last_used_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=_now, onupdate=_now, nullable=False
    )


class RefreshToken(Base):
    """Server-side record of issued refresh tokens, so a single session can
    be revoked (logout, password reset) without invalidating every session."""

    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    # Whether this session was created with "Keep me logged in" checked - read
    # back on every /api/auth/refresh rotation (see auth_service.refresh) so
    # the ORIGINAL login-time choice keeps applying to every reissued token
    # pair for this session's whole lifetime, not just the first one.
    remember_me: Mapped[bool] = mapped_column(Boolean(), default=False, server_default="false", nullable=False)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class UserDownloadPreferences(Base):
    """Per-user download behavior overrides - container_mode and cookie
    handling MUST live here rather than in the personal app's global
    `settings` table, which is a single shared row: reading it for a
    plan-gating decision (see download_gate_service.py) meant one user's
    choice could silently block or unblock every other user. `user_id` is
    itself the primary key (one row per user, created lazily on first
    access with sensible defaults - see user_preferences_service.py)."""

    __tablename__ = "user_download_preferences"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), primary_key=True)
    container_mode: Mapped[str] = mapped_column(String(20), default="compatibility", nullable=False)
    cookie_source: Mapped[str] = mapped_column(String(20), default="none", nullable=False)
    cookie_file_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=_now, onupdate=_now, nullable=False
    )


class AnalyticsEvent(Base):
    """First-party, privacy-conscious analytics: one row per tracked event.

    Deliberately holds NO free-form metadata JSON and NO raw media URLs/IP
    addresses - every field is a specific, whitelisted, aggregate-safe
    attribute (see app/services/analytics_service.py, which is the only
    writer). `visitor_id` is an opaque, unauthenticated random token minted
    into a first-party cookie (see ensure_visitor) - it grants no privilege,
    so unlike GuestQuota's token it is never checked against a server-side
    row; a forged value can only skew someone's own analytics, never another
    user's data or any entitlement. `job_id` lets a download's `started` and
    `completed`/`failed` events be joined for processing-time stats without
    ever repeating the submitted URL. Raw rows are retained for
    ANALYTICS_RETENTION_DAYS (see media_cleanup_service / commercial_settings)
    then purged - see docs/ANALYTICS.md for the full retention policy."""

    __tablename__ = "analytics_events"
    __table_args__ = (Index("ix_analytics_events_type_ts", "event_type", "timestamp"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    event_type: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    visitor_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), index=True, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, index=True, nullable=False)

    # page_view only
    path: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    locale: Mapped[str | None] = mapped_column(String(5), nullable=True)
    referrer_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    utm_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    utm_medium: Mapped[str | None] = mapped_column(String(100), nullable=True)
    utm_campaign: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # analyze/download events
    job_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    source_platform: Mapped[str | None] = mapped_column(String(20), nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    format: Mapped[str | None] = mapped_column(String(30), nullable=True)
    failure_category: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # plan_upgraded / plan_downgraded / subscription_cancelled: `plan` is the
    # resulting plan, `from_plan` the plan immediately before the change -
    # together they let admin reporting show real movements (e.g.
    # "pro -> creator") without guessing direction from a single value.
    plan: Mapped[str | None] = mapped_column(String(20), nullable=True)
    from_plan: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # request/client context, derived server-side only - never trusted from
    # the browser payload (see analytics_service.record_event)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    device_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    browser_family: Mapped[str | None] = mapped_column(String(30), nullable=True)
    os_family: Mapped[str | None] = mapped_column(String(30), nullable=True)
    client: Mapped[str] = mapped_column(String(20), default="web", nullable=False)


class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
