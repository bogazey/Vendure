"""Pydantic request/response schemas for auth, account, billing, and admin."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.commercial_enums import AdminActionType, BillingPeriod, Plan, SubscriptionStatus, UserRole
from app.models.enums import ContainerMode, CookieSource


# ---------- Auth ----------

class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if v.isdigit() or v.isalpha():
            raise ValueError("Password must contain a mix of letters and numbers/symbols.")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)
    # "Keep me logged in" - default False (unchecked) means the session
    # cookie is cleared once the browser itself closes; True means it
    # persists across browser restarts. See auth_service.login /
    # routes_auth._set_session_cookies.
    remember_me: bool = False


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=200)


class VerifyEmailRequest(BaseModel):
    token: str


class UserOut(BaseModel):
    id: str
    email: str
    email_verified: bool
    role: UserRole
    status: str
    created_at: datetime


# ---------- Plans / entitlements ----------

class PlanFeaturesOut(BaseModel):
    plan: Plan
    max_resolution_height: Optional[int]
    can_use_4k: bool
    can_use_batch: bool
    can_use_advanced_formats: bool
    can_use_clip_range: bool
    can_use_browser_cookies: bool
    can_use_original_container: bool
    can_use_creator_tools: bool
    ads_enabled: bool
    queue_priority: int
    monthly_credits: Optional[int]
    daily_free_downloads: Optional[int]


class UsageOut(BaseModel):
    plan: Plan
    period_start: datetime
    period_end: datetime
    credits_included: Optional[int]
    credits_used: int
    credits_remaining: Optional[int]
    daily_free_downloads_used: Optional[int]
    daily_free_downloads_remaining: Optional[int]


class SubscriptionOut(BaseModel):
    plan: Plan
    status: SubscriptionStatus
    billing_period: Optional[BillingPeriod]
    current_period_start: Optional[datetime]
    current_period_end: Optional[datetime]
    cancel_at_period_end: bool
    # "paddle" | "gifted" | "none" (no subscription row at all, e.g. a
    # never-upgraded Free account) - lets the billing UI hide Paddle-only
    # actions (change plan, cancel, update payment method) for a gifted
    # subscription, which has no real Paddle subscription behind it.
    provider: str = "none"


class AccountOut(BaseModel):
    user: UserOut
    subscription: SubscriptionOut
    usage: UsageOut
    features: PlanFeaturesOut


# ---------- Guest downloads ----------
# Deliberately NOT modeled as a fake AccountOut - a guest has no user,
# subscription, or credit-based usage at all, just a small download count.

class GuestQuotaOut(BaseModel):
    remaining: int
    limit: int


# ---------- Per-user download preferences ----------
# container_mode / cookie_source / cookie_file_path are per-user (never the
# personal app's global AppSettings) so one account's choice here can never
# change what another account's downloads are gated against or run with.

class DownloadPreferencesOut(BaseModel):
    container_mode: ContainerMode
    cookie_source: CookieSource
    cookie_file_path: Optional[str] = None


class UpdateDownloadPreferencesRequest(BaseModel):
    container_mode: Optional[ContainerMode] = None
    cookie_source: Optional[CookieSource] = None
    cookie_file_path: Optional[str] = None


# ---------- Billing / checkout ----------

class CheckoutRequest(BaseModel):
    plan: Plan
    billing_period: BillingPeriod

    @field_validator("plan")
    @classmethod
    def plan_must_be_paid(cls, v: Plan) -> Plan:
        if v == Plan.FREE:
            raise ValueError("The Free plan does not require checkout.")
        return v


class CheckoutResponse(BaseModel):
    price_id: str
    client_token: str
    # "sandbox" | "production" - the frontend calls Paddle.Environment.set()
    # with this rather than hardcoding it, so PADDLE_ENV stays the single
    # source of truth. This build only ever sets PADDLE_ENV=sandbox.
    environment: str
    plan: Plan
    billing_period: BillingPeriod
    # Passed to Paddle.js as `customData` so the webhook can be correlated
    # back to this user without a separate customer-lookup round trip.
    custom_data: dict


class BillingPortalResponse(BaseModel):
    url: Optional[str]


# ---------- Admin ----------

class AdminUserOut(BaseModel):
    id: str
    email: str
    status: str
    role: UserRole
    plan: Plan
    subscription_status: SubscriptionStatus
    credits_used: int
    credits_included: Optional[int]
    # Portion of credits_included beyond the plan's own base allocation -
    # i.e. cumulative admin grants this period. Derived, not stored
    # separately (see routes_admin._to_admin_user_out): None wherever
    # credits_included itself is None (Free plan, which doesn't use credits).
    credits_bonus: Optional[int]
    created_at: datetime
    # "paddle" | "gifted" | "none" - see SubscriptionOut.provider. Lets the
    # admin panel show "Paid / Paddle" vs "Gifted Subscription" vs "Free"
    # and decide whether gifting controls are safe to offer at all.
    subscription_provider: str
    # Populated only while provider == "gifted" (the row's *current* grant -
    # see AdminActionLog via /api/admin/audit-log for the full history).
    gifted_granted_at: Optional[datetime] = None
    gifted_granted_by_email: Optional[str] = None
    gifted_reason: Optional[str] = None


class AdminUserListOut(BaseModel):
    users: list[AdminUserOut]
    total: int


class AdminGrantCreditsRequest(BaseModel):
    credits: int = Field(gt=0, le=100000)
    reason: str = Field(min_length=1, max_length=500)


class AdminSetAccountStatusRequest(BaseModel):
    status: str = Field(pattern="^(active|disabled)$")


class AdminUpdateSubscriptionRequest(BaseModel):
    """Admin-managed Gifted Subscription: grant, change (Pro<->Creator), or
    revoke (plan=free) - never a Paddle call, see gift_subscription_service.py.
    `source` is deliberately NOT part of this request: it is always
    "gifted" server-side for this endpoint (see routes_admin.py) - a client
    can never claim/forge a subscription source."""

    plan: Plan
    reason: Optional[str] = Field(default=None, max_length=500)


class AdminBillingEventOut(BaseModel):
    provider_event_id: str
    event_type: str
    processed_at: datetime
    status: str
    # Best-effort - see BillingEvent.user_id. Both None for events that
    # predate the column or never carried a resolvable user reference.
    user_id: Optional[str] = None
    user_email: Optional[str] = None


class AdminActionLogOut(BaseModel):
    id: str
    admin_id: str
    admin_email: Optional[str] = None
    action: AdminActionType
    target_user_id: Optional[str] = None
    target_email: Optional[str] = None
    details: dict
    created_at: datetime


class AdminOverviewOut(BaseModel):
    total_users: int
    active_users: int
    disabled_users: int
    # Authoritative paid-only count (provider="paddle") - see
    # routes_admin.get_overview. Never includes gifted subscriptions.
    paid_subscribers: int
    free_count: int
    pro_count: int
    creator_count: int
    # Counted and surfaced separately from paid_subscribers - never summed
    # together (see docs/ANALYTICS.md "Gifted subscriptions are not revenue").
    gifted_subscribers: int
    credits_consumed_current_period: int
    recent_billing_failures: list[AdminBillingEventOut]
    recent_admin_actions: list[AdminActionLogOut]


class AdPlacementOut(BaseModel):
    """Public, non-secret placement config - what AdSlot needs at runtime to
    decide whether to render anything. Never carries API keys or private ad
    network tokens; those must never be stored in this table at all."""

    id: str
    enabled: bool
    provider: Optional[str] = None
    public_slot_id: Optional[str] = None


class AdminAdPlacementOut(AdPlacementOut):
    description: str
    updated_at: datetime


class AdminUpdateAdPlacementRequest(BaseModel):
    """Partial update - only fields the admin actually changed are sent."""

    enabled: Optional[bool] = None
    provider: Optional[str] = Field(default=None, max_length=80)
    public_slot_id: Optional[str] = Field(default=None, max_length=120)

    @field_validator("provider", "public_slot_id")
    @classmethod
    def _blank_to_none(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() or None if value is not None else None


class AdminHealthOut(BaseModel):
    """Operational health for the admin System page - deliberately excludes
    ffmpeg_path/download_dir (see HealthResponse): the admin panel should
    never display absolute server filesystem paths."""

    status: str
    database_ok: bool
    ffmpeg_available: bool
    ytdlp_version: Optional[str] = None
    download_dir_writable: bool
