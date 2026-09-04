"""Pydantic request/response schemas for auth, account, billing, and admin."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.commercial_enums import BillingPeriod, Plan, SubscriptionStatus, UserRole
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


class AccountOut(BaseModel):
    user: UserOut
    subscription: SubscriptionOut
    usage: UsageOut
    features: PlanFeaturesOut


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
    created_at: datetime


class AdminUserListOut(BaseModel):
    users: list[AdminUserOut]
    total: int


class AdminGrantCreditsRequest(BaseModel):
    credits: int = Field(gt=0, le=100000)
    reason: str = Field(min_length=1, max_length=500)


class AdminSetAccountStatusRequest(BaseModel):
    status: str = Field(pattern="^(active|disabled)$")
