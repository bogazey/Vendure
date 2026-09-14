"""Pydantic request/response models."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import EntitlementSource, EntitlementStatus, ProductStatus


# --- Identity -----------------------------------------------------------

class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    remember_me: bool = False


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=200)


class VerifyEmailRequest(BaseModel):
    token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=200)
    # Mission 6 (Phase 20): "define whether other sessions revoke ...
    # recommended: offer/recommend revoking other sessions" - opt-in
    # rather than automatic, since forcing every other device to re-
    # authenticate on every password change is a UX call the caller
    # (account portal UI) should make explicit, not one this API decides
    # silently.
    revoke_other_sessions: bool = False


class UserOut(BaseModel):
    id: str
    email: str
    email_verified: bool
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class SessionOut(BaseModel):
    id: str
    device_label: Optional[str]
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime
    is_current: bool

    class Config:
        from_attributes = True


# --- Products / membership ----------------------------------------------

class ProductOut(BaseModel):
    id: str
    name: str
    domain: str
    status: str
    icon_ref: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class ProductMembershipOut(BaseModel):
    product_id: str
    status: str
    first_seen_at: datetime
    last_seen_at: datetime

    class Config:
        from_attributes = True


# --- Entitlements ---------------------------------------------------------

class PlanOut(BaseModel):
    id: str
    product_id: str
    slug: str
    name: str

    class Config:
        from_attributes = True


class EntitlementOut(BaseModel):
    id: str
    user_id: str
    product_id: str
    plan_id: str
    plan_slug: str
    source: str
    status: str
    starts_at: datetime
    expires_at: Optional[datetime]
    granted_by_email: Optional[str] = None
    reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class GrantEntitlementRequest(BaseModel):
    product_id: str
    plan_slug: str
    source: EntitlementSource
    expires_at: Optional[datetime] = None
    reason: Optional[str] = Field(default=None, max_length=500)


class RevokeEntitlementRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500)


# --- RBAC -----------------------------------------------------------------

class RoleAssignmentOut(BaseModel):
    role_slug: str
    scope: str
    granted_by: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class AssignRoleRequest(BaseModel):
    role_slug: str
    scope: str = Field(default="global", max_length=60)


# --- Grand Admin ------------------------------------------------------------

class AdminUserOut(BaseModel):
    id: str
    email: str
    email_verified: bool
    status: str
    created_at: datetime
    roles: list[RoleAssignmentOut] = []
    entitlement_count: int = 0
    gifted_entitlement_count: int = 0


class AdminOverviewOut(BaseModel):
    total_users: int
    active_users: int
    total_products: int
    paid_entitlements: int
    gifted_entitlements: int
    revenue_available: bool = False
    revenue_note: str = "No real payment processor is wired into Platform Core in V1 - revenue is intentionally not fabricated."


class AuditLogOut(BaseModel):
    id: str
    actor_user_id: Optional[str]
    actor_email: Optional[str] = None
    action: str
    target_type: str
    target_id: Optional[str]
    product_id: Optional[str]
    before_state: Optional[dict]
    after_state: Optional[dict]
    reason: Optional[str]
    created_at: datetime


class AdminSetStatusRequest(BaseModel):
    status: str


class AdminCreateProductRequest(BaseModel):
    id: str = Field(min_length=2, max_length=40, pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=1, max_length=80)
    domain: str = Field(min_length=3, max_length=255)
    status: ProductStatus = ProductStatus.PLANNED
    icon_ref: Optional[str] = Field(default=None, max_length=80)


# --- OAuth client registration (service-to-service; Grand Admin only) ----

class RegisterClientRequest(BaseModel):
    client_id: str = Field(min_length=2, max_length=60, pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=1, max_length=120)
    product_id: Optional[str] = None
    redirect_uris: list[str] = Field(min_length=1, max_length=10)


class RegisterClientResponse(BaseModel):
    client_id: str
    client_secret: str
