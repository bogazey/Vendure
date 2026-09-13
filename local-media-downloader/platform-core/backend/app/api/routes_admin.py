"""Grand Admin API — every route requires at least `require_global_admin`
(role `admin` or `super_admin` at global scope); role/client management
additionally requires `require_super_admin`. A normal user, or a user with
only a product-scoped role, gets 401/403 from every route here — there is
no path by which a product-scoped admin can escalate to global admin
(mission-brief sections 17/32/46).
"""
from __future__ import annotations

from sqlalchemy import func, select
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_global_admin, require_super_admin
from app.database.models import (
    AuditLog,
    Entitlement,
    OAuthClient,
    Plan,
    Product,
    User,
)
from app.models.enums import AuditAction, EntitlementSource, EntitlementStatus, RoleSlug
from app.models.schemas import (
    AdminCreateProductRequest,
    AdminOverviewOut,
    AdminSetStatusRequest,
    AdminUserOut,
    AssignRoleRequest,
    AuditLogOut,
    GrantEntitlementRequest,
    PlanOut,
    ProductOut,
    RegisterClientRequest,
    RegisterClientResponse,
    RevokeEntitlementRequest,
    RoleAssignmentOut,
)
from app.services import audit_service, entitlement_service, oidc_service, product_service, rbac_service
from app.utils.exceptions import ForbiddenError, InvalidPlanError, NotFoundError

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

_GIFTED_SOURCES = {EntitlementSource.GIFTED.value, EntitlementSource.INTERNAL.value, EntitlementSource.PROMOTION.value}


def _require_target(db: Session, user_id: str) -> User:
    target = db.get(User, user_id)
    if target is None:
        raise NotFoundError("User not found.")
    return target


# --- Overview --------------------------------------------------------------

@router.get("/overview", response_model=AdminOverviewOut, dependencies=[Depends(require_global_admin)])
async def overview(db: Session = Depends(get_db)) -> AdminOverviewOut:
    total_users = db.execute(select(func.count(User.id))).scalar_one()
    active_users = db.execute(select(func.count(User.id)).where(User.status == "active")).scalar_one()
    total_products = db.execute(select(func.count(Product.id))).scalar_one()
    paid_entitlements = db.execute(
        select(func.count(Entitlement.id)).where(
            Entitlement.status == EntitlementStatus.ACTIVE.value,
            Entitlement.source == EntitlementSource.PADDLE.value,
        )
    ).scalar_one()
    gifted_entitlements = db.execute(
        select(func.count(Entitlement.id)).where(
            Entitlement.status == EntitlementStatus.ACTIVE.value,
            Entitlement.source.in_(_GIFTED_SOURCES),
        )
    ).scalar_one()
    return AdminOverviewOut(
        total_users=total_users,
        active_users=active_users,
        total_products=total_products,
        paid_entitlements=paid_entitlements,
        gifted_entitlements=gifted_entitlements,
    )


# --- Users -------------------------------------------------------------------

def _to_admin_user_out(db: Session, user: User) -> AdminUserOut:
    roles = rbac_service.list_roles(db, user.id)
    entitlement_count = db.execute(
        select(func.count(Entitlement.id)).where(
            Entitlement.user_id == user.id, Entitlement.status == EntitlementStatus.ACTIVE.value
        )
    ).scalar_one()
    gifted_count = db.execute(
        select(func.count(Entitlement.id)).where(
            Entitlement.user_id == user.id,
            Entitlement.status == EntitlementStatus.ACTIVE.value,
            Entitlement.source.in_(_GIFTED_SOURCES),
        )
    ).scalar_one()
    return AdminUserOut(
        id=user.id, email=user.email, email_verified=user.email_verified, status=user.status,
        created_at=user.created_at,
        roles=[RoleAssignmentOut.model_validate(r, from_attributes=True) for r in roles],
        entitlement_count=entitlement_count, gifted_entitlement_count=gifted_count,
    )


@router.get("/users", response_model=list[AdminUserOut], dependencies=[Depends(require_global_admin)])
async def list_users(db: Session = Depends(get_db), q: str | None = Query(default=None), limit: int = Query(default=50, le=200)) -> list[AdminUserOut]:
    query = select(User).order_by(User.created_at.desc()).limit(limit)
    if q:
        query = select(User).where(User.email.ilike(f"%{q.strip().lower()}%")).order_by(User.created_at.desc()).limit(limit)
    users = db.execute(query).scalars().all()
    return [_to_admin_user_out(db, u) for u in users]


@router.get("/users/{user_id}", response_model=AdminUserOut, dependencies=[Depends(require_global_admin)])
async def get_user(user_id: str, db: Session = Depends(get_db)) -> AdminUserOut:
    return _to_admin_user_out(db, _require_target(db, user_id))


@router.get("/users/{user_id}/memberships", dependencies=[Depends(require_global_admin)])
async def get_user_memberships(user_id: str, db: Session = Depends(get_db)) -> list[dict]:
    _require_target(db, user_id)
    memberships = product_service.list_memberships(db, user_id)
    return [
        {"product_id": m.product_id, "status": m.status, "first_seen_at": m.first_seen_at.isoformat(), "last_seen_at": m.last_seen_at.isoformat()}
        for m in memberships
    ]


@router.get("/users/{user_id}/entitlements", dependencies=[Depends(require_global_admin)])
async def get_user_entitlements(user_id: str, db: Session = Depends(get_db)) -> list[dict]:
    _require_target(db, user_id)
    entitlements = entitlement_service.list_entitlements_for_user(db, user_id)
    out = []
    for e in entitlements:
        plan = db.get(Plan, e.plan_id)
        granter = db.get(User, e.granted_by) if e.granted_by else None
        out.append({
            "id": e.id, "product_id": e.product_id, "plan_slug": plan.slug if plan else None,
            "source": e.source, "status": e.status, "starts_at": e.starts_at.isoformat(),
            "expires_at": e.expires_at.isoformat() if e.expires_at else None,
            "granted_by_email": granter.email if granter else None, "reason": e.reason,
        })
    return out


@router.get("/users/{user_id}/audit-log", response_model=list[AuditLogOut], dependencies=[Depends(require_global_admin)])
async def get_user_audit_log(user_id: str, db: Session = Depends(get_db)) -> list[AuditLogOut]:
    _require_target(db, user_id)
    entries = audit_service.list_recent(db, limit=100, target_id=user_id)
    return [_to_audit_out(db, e) for e in entries]


@router.patch("/users/{user_id}/status", response_model=AdminUserOut)
async def set_user_status(
    user_id: str, payload: AdminSetStatusRequest, db: Session = Depends(get_db), admin: User = Depends(require_global_admin)
) -> AdminUserOut:
    target = _require_target(db, user_id)
    if target.id == admin.id and payload.status != "active":
        raise ForbiddenError("You cannot disable your own account.")
    if payload.status not in ("active", "disabled"):
        raise InvalidPlanError("status must be 'active' or 'disabled'.")
    before = {"status": target.status}
    target.status = payload.status
    audit_service.record(
        db, admin.id, AuditAction.USER_STATUS_CHANGED, "user", target.id,
        before_state=before, after_state={"status": target.status},
    )
    return _to_admin_user_out(db, target)


# --- Roles (super_admin only) ------------------------------------------------

@router.post("/users/{user_id}/roles", response_model=AdminUserOut, dependencies=[Depends(require_super_admin)])
async def assign_role(
    user_id: str, payload: AssignRoleRequest, db: Session = Depends(get_db), admin: User = Depends(require_super_admin)
) -> AdminUserOut:
    target = _require_target(db, user_id)
    try:
        role = RoleSlug(payload.role_slug)
    except ValueError:
        raise InvalidPlanError(f"Unknown role '{payload.role_slug}'.")
    rbac_service.assign_role(db, target, role, payload.scope, granted_by=admin.id)
    audit_service.record(
        db, admin.id, AuditAction.ROLE_ASSIGNED, "user", target.id,
        after_state={"role_slug": role.value, "scope": payload.scope},
    )
    return _to_admin_user_out(db, target)


@router.delete("/users/{user_id}/roles", response_model=AdminUserOut, dependencies=[Depends(require_super_admin)])
async def revoke_role(
    user_id: str, payload: AssignRoleRequest, db: Session = Depends(get_db), admin: User = Depends(require_super_admin)
) -> AdminUserOut:
    target = _require_target(db, user_id)
    try:
        role = RoleSlug(payload.role_slug)
    except ValueError:
        raise InvalidPlanError(f"Unknown role '{payload.role_slug}'.")
    rbac_service.revoke_role(db, target.id, role, payload.scope)
    audit_service.record(
        db, admin.id, AuditAction.ROLE_REVOKED, "user", target.id,
        before_state={"role_slug": role.value, "scope": payload.scope},
    )
    return _to_admin_user_out(db, target)


# --- Products / plans ---------------------------------------------------------

@router.get("/products", response_model=list[ProductOut], dependencies=[Depends(require_global_admin)])
async def list_products(db: Session = Depends(get_db)) -> list[ProductOut]:
    return [ProductOut.model_validate(p, from_attributes=True) for p in product_service.list_products(db)]


@router.post("/products", response_model=ProductOut, dependencies=[Depends(require_global_admin)])
async def create_product(payload: AdminCreateProductRequest, db: Session = Depends(get_db), admin: User = Depends(require_global_admin)) -> ProductOut:
    if db.get(Product, payload.id) is not None:
        raise InvalidPlanError(f"Product '{payload.id}' already exists.")
    product = product_service.create_product(db, payload.id, payload.name, payload.domain, payload.status.value, payload.icon_ref)
    audit_service.record(db, admin.id, AuditAction.PRODUCT_CREATED, "product", product.id, product_id=product.id, after_state={"name": product.name, "domain": product.domain})
    return ProductOut.model_validate(product, from_attributes=True)


@router.get("/products/{product_id}/plans", response_model=list[PlanOut], dependencies=[Depends(require_global_admin)])
async def list_plans(product_id: str, db: Session = Depends(get_db)) -> list[PlanOut]:
    plans = db.execute(select(Plan).where(Plan.product_id == product_id)).scalars().all()
    return [PlanOut.model_validate(p, from_attributes=True) for p in plans]


@router.post("/products/{product_id}/plans", response_model=PlanOut, dependencies=[Depends(require_global_admin)])
async def create_plan(product_id: str, slug: str, name: str, db: Session = Depends(get_db)) -> PlanOut:
    product_service.get_product(db, product_id)
    plan = entitlement_service.get_or_create_plan(db, product_id, slug, name)
    return PlanOut.model_validate(plan, from_attributes=True)


# --- Entitlements / Gifted Access --------------------------------------------

@router.get("/gifted-access", dependencies=[Depends(require_global_admin)])
async def list_gifted_access(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        select(Entitlement).where(
            Entitlement.status == EntitlementStatus.ACTIVE.value,
            Entitlement.source.in_(_GIFTED_SOURCES),
        ).order_by(Entitlement.updated_at.desc())
    ).scalars().all()
    out = []
    for e in rows:
        user = db.get(User, e.user_id)
        plan = db.get(Plan, e.plan_id)
        granter = db.get(User, e.granted_by) if e.granted_by else None
        out.append({
            "id": e.id, "user_id": e.user_id, "user_email": user.email if user else None,
            "product_id": e.product_id, "plan_slug": plan.slug if plan else None,
            "source": e.source, "expires_at": e.expires_at.isoformat() if e.expires_at else None,
            "granted_by_email": granter.email if granter else None, "reason": e.reason,
            "created_at": e.created_at.isoformat(),
        })
    return out


@router.patch("/users/{user_id}/entitlements", dependencies=[Depends(require_global_admin)])
async def grant_or_change_entitlement(
    user_id: str, payload: GrantEntitlementRequest, db: Session = Depends(get_db), admin: User = Depends(require_global_admin)
) -> dict:
    """The Gifted/Entitlement management action (mission-brief section 16).
    Blocked (409-equivalent AppError) if the user already holds an active
    `paddle`-sourced entitlement in this product and the admin is trying to
    replace it with a non-paddle source — an admin action must never
    silently downgrade or corrupt what a real payment already granted
    (mission-brief section 16), mirroring Loady's own
    `PaidSubscriptionActiveError` precedent."""
    target = _require_target(db, user_id)
    existing = entitlement_service.get_active_entitlement(db, target.id, payload.product_id)
    if existing is not None and existing.source == EntitlementSource.PADDLE.value and payload.source != EntitlementSource.PADDLE:
        raise ForbiddenError(
            "This user has an active paid entitlement in this product. "
            "It cannot be silently replaced by a gifted/internal one through this control."
        )
    entitlement = entitlement_service.grant_or_change(
        db, admin, target, payload.product_id, payload.plan_slug, payload.source, payload.expires_at, payload.reason
    )
    return {"id": entitlement.id, "status": entitlement.status, "source": entitlement.source}


@router.delete("/users/{user_id}/entitlements/{product_id}", dependencies=[Depends(require_global_admin)])
async def revoke_entitlement(
    user_id: str, product_id: str, payload: RevokeEntitlementRequest, db: Session = Depends(get_db), admin: User = Depends(require_global_admin)
) -> dict:
    target = _require_target(db, user_id)
    existing = entitlement_service.get_active_entitlement(db, target.id, product_id)
    if existing is not None and existing.source == EntitlementSource.PADDLE.value:
        raise ForbiddenError(
            "This user has an active paid entitlement in this product. "
            "Manage it through the product's own billing workflow, not this control."
        )
    revoked = entitlement_service.revoke(db, admin, target, product_id, payload.reason)
    return {"revoked": revoked is not None}


# --- OAuth client registration (super_admin only) ----------------------------

@router.post("/clients", response_model=RegisterClientResponse, dependencies=[Depends(require_super_admin)])
async def register_client(
    payload: RegisterClientRequest, db: Session = Depends(get_db), admin: User = Depends(require_super_admin)
) -> RegisterClientResponse:
    _client, raw_secret = oidc_service.register_client(
        db, admin, payload.client_id, payload.name, payload.product_id, payload.redirect_uris
    )
    return RegisterClientResponse(client_id=payload.client_id, client_secret=raw_secret)


@router.get("/clients", dependencies=[Depends(require_super_admin)])
async def list_clients(db: Session = Depends(get_db)) -> list[dict]:
    clients = db.execute(select(OAuthClient)).scalars().all()
    return [
        {"client_id": c.client_id, "name": c.name, "product_id": c.product_id, "redirect_uris": c.redirect_uris, "is_active": c.is_active}
        for c in clients
    ]


# --- Audit log ------------------------------------------------------------

def _to_audit_out(db: Session, entry: AuditLog) -> AuditLogOut:
    actor = db.get(User, entry.actor_user_id) if entry.actor_user_id else None
    return AuditLogOut(
        id=entry.id, actor_user_id=entry.actor_user_id, actor_email=actor.email if actor else None,
        action=entry.action, target_type=entry.target_type, target_id=entry.target_id,
        product_id=entry.product_id, before_state=entry.before_state, after_state=entry.after_state,
        reason=entry.reason, created_at=entry.created_at,
    )


@router.get("/audit-log", response_model=list[AuditLogOut], dependencies=[Depends(require_global_admin)])
async def audit_log(db: Session = Depends(get_db), limit: int = Query(default=100, le=500)) -> list[AuditLogOut]:
    entries = audit_service.list_recent(db, limit=limit)
    return [_to_audit_out(db, e) for e in entries]
