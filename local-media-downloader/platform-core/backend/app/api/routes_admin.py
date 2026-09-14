"""Grand Admin API — most routes require at least `require_global_admin`
(role `admin` or `super_admin` at global scope); role/client management
additionally requires `require_super_admin`. A normal user, or a user with
only a product-scoped role, gets 401/403 from every such route — there is
no path by which a product-scoped admin can escalate to global admin
(mission-brief sections 17/32/46).

Mission 6 continuation (Product-Scoped RBAC): routes whose resource
belongs to exactly one product (capabilities, gifted access, the simple
plan-create endpoint below) instead use `require_product_admin`/
`require_plan_admin`, which ALSO accept a global admin - a product-scoped
`admin` may manage only their own product; a global admin may manage
every product. See `api/deps.py` and `docs/platform/ADMIN_RBAC.md`.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_user,
    get_db,
    rate_limit_admin_mutation,
    require_client_admin,
    require_global_admin,
    require_global_admin_or_any_product_admin,
    require_plan_admin,
    require_product_admin,
    require_super_admin,
)
from app.database.models import (
    AuditLog,
    BillingWebhookEvent,
    Bundle,
    Entitlement,
    GiftedAccess,
    OAuthClient,
    PaymentRecord,
    Plan,
    Product,
    Subscription,
    User,
)
from app.models.enums import AuditAction, CapabilityValueType, EntitlementSource, EntitlementStatus, RoleSlug
from app.models.schemas import (
    AdminCreateProductRequest,
    AdminOverviewOut,
    AdminSetStatusRequest,
    AdminUserOut,
    AssignRoleRequest,
    AuditLogOut,
    GrantEntitlementRequest,
    PlanOut,
    ProductOnboardRequest,
    ProductOnboardResponse,
    ProductOut,
    RegisterClientRequest,
    RegisterClientResponse,
    RevokeEntitlementRequest,
    RoleAssignmentOut,
)
from app.services import (
    audit_service,
    billing,
    bundle_service,
    capability_service,
    entitlement_service,
    gift_service,
    oidc_service,
    product_service,
    rbac_service,
    revenue_service,
    service_auth,
    webhook_service,
)
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


@router.patch("/users/{user_id}/status", response_model=AdminUserOut, dependencies=[Depends(rate_limit_admin_mutation)])
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

@router.post("/users/{user_id}/roles", response_model=AdminUserOut, dependencies=[Depends(require_super_admin), Depends(rate_limit_admin_mutation)])
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


@router.delete("/users/{user_id}/roles", response_model=AdminUserOut, dependencies=[Depends(require_super_admin), Depends(rate_limit_admin_mutation)])
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

@router.get("/products", response_model=list[ProductOut], dependencies=[Depends(require_global_admin_or_any_product_admin)])
async def list_products(db: Session = Depends(get_db), admin: User = Depends(get_current_user)) -> list[ProductOut]:
    # A product-scoped-only admin (e.g. a Loady admin with no global role)
    # has no other route into Grand Admin's product management UI - the
    # per-product page (Plans/Prices/Capabilities) they're authorized to
    # use is reached by first listing products, so this must show at
    # least their own product rather than 403 the whole page.
    visible = rbac_service.admin_visible_product_ids(db, admin.id)
    products = product_service.list_products(db)
    if visible is not None:
        products = [p for p in products if p.id in visible]
    return [ProductOut.model_validate(p, from_attributes=True) for p in products]


@router.post("/products", response_model=ProductOut, dependencies=[Depends(require_global_admin), Depends(rate_limit_admin_mutation)])
async def create_product(payload: AdminCreateProductRequest, db: Session = Depends(get_db), admin: User = Depends(require_global_admin)) -> ProductOut:
    if db.get(Product, payload.id) is not None:
        raise InvalidPlanError(f"Product '{payload.id}' already exists.")
    product = product_service.create_product(
        db, payload.id, payload.name, payload.domain, payload.status.value, payload.icon_ref,
        description=payload.description, is_discoverable=payload.is_discoverable,
    )
    audit_service.record(db, admin.id, AuditAction.PRODUCT_CREATED, "product", product.id, product_id=product.id, after_state={"name": product.name, "domain": product.domain})
    return ProductOut.model_validate(product, from_attributes=True)


@router.post(
    "/products/onboard", response_model=ProductOnboardResponse,
    dependencies=[Depends(require_super_admin), Depends(rate_limit_admin_mutation)],
)
async def onboard_product(
    payload: ProductOnboardRequest, db: Session = Depends(get_db), admin: User = Depends(require_super_admin)
) -> ProductOnboardResponse:
    """The Grand Admin "Add Product" flow (mission 6 continuation): creates
    the product AND registers its initial OAuth client in one super_admin-
    gated action, instead of requiring two separate calls. `super_admin`
    (not merely `require_global_admin`, which the standalone `POST
    /products` above accepts) because this also registers an OAuth
    client - the same bar `POST /clients` already sets on its own, and a
    product-scoped admin can never reach this route regardless (product-
    scoped roles are never `super_admin`).

    The returned `client_secret` is plaintext and appears in exactly this
    one response - only its Argon2 hash is ever persisted
    (`oidc_service.register_client`), and there is no endpoint anywhere
    that can retrieve a plaintext secret after this. If registering the
    client fails (e.g. a duplicate `client_id`), the product row is rolled
    back too - `get_db` only commits when the whole request completes
    without raising, so this is atomic without extra bookkeeping here."""
    if db.get(Product, payload.id) is not None:
        raise InvalidPlanError(f"Product '{payload.id}' already exists.")
    product = product_service.create_product(
        db, payload.id, payload.name, payload.domain, payload.status.value, None,
        description=payload.description, is_discoverable=payload.is_discoverable,
    )
    audit_service.record(
        db, admin.id, AuditAction.PRODUCT_CREATED, "product", product.id, product_id=product.id,
        after_state={"name": product.name, "domain": product.domain, "via": "onboard"},
    )
    _client, raw_secret = oidc_service.register_client(
        db, admin, payload.client_id, payload.client_name, product.id, payload.redirect_uris
    )
    return ProductOnboardResponse(
        product=ProductOut.model_validate(product, from_attributes=True),
        client_id=payload.client_id,
        client_secret=raw_secret,
    )


@router.get("/products/{product_id}/plans", response_model=list[PlanOut], dependencies=[Depends(require_product_admin)])
async def list_plans(product_id: str, db: Session = Depends(get_db)) -> list[PlanOut]:
    plans = db.execute(select(Plan).where(Plan.product_id == product_id)).scalars().all()
    return [PlanOut.model_validate(p, from_attributes=True) for p in plans]


@router.post("/products/{product_id}/plans", response_model=PlanOut, dependencies=[Depends(require_product_admin), Depends(rate_limit_admin_mutation)])
async def create_plan(product_id: str, slug: str, name: str, db: Session = Depends(get_db)) -> PlanOut:
    """Minimal legacy form (name+slug only) - kept for backward
    compatibility with Mission 6 phase 1 callers. `routes_catalog.py`'s
    `POST /api/v1/admin/catalog/products/{product_id}/plans` is the full
    Product Subscription Manager form (description, sort order, upgrade
    rank, gifted/trial eligibility) and is what Grand Admin's plan editor
    actually uses."""
    product_service.get_product(db, product_id)
    plan = entitlement_service.get_or_create_plan(db, product_id, slug, name)
    return PlanOut.model_validate(plan, from_attributes=True)


# --- Entitlements / Gifted Access --------------------------------------------

@router.get("/gifted-access", dependencies=[Depends(require_global_admin_or_any_product_admin)])
async def list_gifted_access(db: Session = Depends(get_db), admin: User = Depends(get_current_user)) -> list[dict]:
    visible = rbac_service.admin_visible_product_ids(db, admin.id)
    query = select(Entitlement).where(
        Entitlement.status == EntitlementStatus.ACTIVE.value,
        Entitlement.source.in_(_GIFTED_SOURCES),
    ).order_by(Entitlement.updated_at.desc())
    if visible is not None:
        query = query.where(Entitlement.product_id.in_(visible))
    rows = db.execute(query).scalars().all()
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


@router.patch("/users/{user_id}/entitlements", dependencies=[Depends(rate_limit_admin_mutation)])
async def grant_or_change_entitlement(
    user_id: str, payload: GrantEntitlementRequest, db: Session = Depends(get_db), admin: User = Depends(get_current_user)
) -> dict:
    """The Gifted/Entitlement management action (mission-brief section 16).
    Blocked (409-equivalent AppError) if the user already holds an active
    `paddle`-sourced entitlement in this product and the admin is trying to
    replace it with a non-paddle source — an admin action must never
    silently downgrade or corrupt what a real payment already granted
    (mission-brief section 16), mirroring Loady's own
    `PaidSubscriptionActiveError` precedent.

    Mission 6 continuation security review finding: a revenue-adjacent
    source (`paddle`/`lifetime`) may only ever be set by a GLOBAL admin,
    never a product-scoped one - product-scoping this route (so a
    per-product admin could manage their own product's entitlements) would
    otherwise have newly let a product-scoped admin fabricate a "paid"-
    looking entitlement for their own product with no real payment behind
    it, inflating paid-subscriber counts/reports (PaymentRecord itself
    can't be faked this way, but this source tag is what several report
    queries filter on - see BILLING.md)."""
    if payload.source in (EntitlementSource.PADDLE, EntitlementSource.LIFETIME):
        if not rbac_service.is_global_admin(db, admin.id):
            raise ForbiddenError("Only a global admin may mark an entitlement as paddle/lifetime-sourced.")
    elif not rbac_service.is_global_or_product_admin(db, admin.id, payload.product_id):
        raise ForbiddenError(f"You do not have admin access to product '{payload.product_id}'.")
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


@router.delete("/users/{user_id}/entitlements/{product_id}", dependencies=[Depends(rate_limit_admin_mutation)])
async def revoke_entitlement(
    user_id: str, product_id: str, payload: RevokeEntitlementRequest, db: Session = Depends(get_db), admin: User = Depends(require_product_admin)
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

@router.post("/clients", response_model=RegisterClientResponse, dependencies=[Depends(require_super_admin), Depends(rate_limit_admin_mutation)])
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


# =============================================================================
# Mission 6 (Phase 31): capabilities / plan entitlements
# =============================================================================


@router.get("/products/{product_id}/capabilities", dependencies=[Depends(require_product_admin)])
async def list_capabilities(product_id: str, db: Session = Depends(get_db)) -> list[dict]:
    defs = capability_service.list_capabilities(db, product_id)
    return [
        {"id": d.id, "key": d.key, "value_type": d.value_type, "description": d.description, "allowed_values": d.allowed_values}
        for d in defs
    ]


@router.post("/products/{product_id}/capabilities", dependencies=[Depends(rate_limit_admin_mutation)])
async def define_capability(product_id: str, payload: dict, db: Session = Depends(get_db), admin: User = Depends(require_product_admin)) -> dict:
    product_service.get_product(db, product_id)
    try:
        value_type = CapabilityValueType(payload["value_type"])
    except (KeyError, ValueError):
        raise InvalidPlanError("value_type must be one of: boolean, integer, string, enum.")
    definition = capability_service.define_capability(
        db, product_id, payload["key"], value_type, payload.get("description"), payload.get("allowed_values"),
    )
    audit_service.record(db, admin.id, AuditAction.CAPABILITY_DEFINED, "entitlement_definition", definition.id, product_id, after_state={"key": definition.key})
    return {"id": definition.id, "key": definition.key, "value_type": definition.value_type}


@router.get("/plans/{plan_id}/capabilities", dependencies=[Depends(require_plan_admin)])
async def get_plan_capabilities(plan_id: str, db: Session = Depends(get_db)) -> dict:
    if db.get(Plan, plan_id) is None:
        raise NotFoundError("Plan not found.")
    return capability_service.get_plan_capabilities(db, plan_id)


@router.put("/plans/{plan_id}/capabilities/{key}", dependencies=[Depends(rate_limit_admin_mutation)])
async def set_plan_capability(plan_id: str, key: str, payload: dict, db: Session = Depends(get_db), admin: User = Depends(require_plan_admin)) -> dict:
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise NotFoundError("Plan not found.")
    row = capability_service.set_plan_entitlement(db, plan, key, payload["value"])
    audit_service.record(db, admin.id, AuditAction.PLAN_ENTITLEMENT_SET, "plan_entitlement", row.id, plan.product_id, after_state={"key": key, "value": payload["value"]})
    return {"plan_id": plan_id, "key": key, "value": payload["value"]}


@router.get("/users/{user_id}/effective-entitlements", dependencies=[Depends(require_product_admin)])
async def effective_entitlements(user_id: str, product_id: str = Query(...), db: Session = Depends(get_db)) -> dict:
    _require_target(db, user_id)
    result = capability_service.resolve_effective_entitlements(db, user_id, product_id)
    return {
        "product_id": result.product_id,
        "capabilities": result.capabilities,
        "sources": [
            {"kind": s.kind, "plan_id": s.plan_id, "plan_slug": s.plan_slug, "status": s.status,
             "expires_at": s.expires_at.isoformat() if s.expires_at else None, "rank": s.rank}
            for s in result.sources
        ],
    }


# =============================================================================
# Mission 6 (Phase 13): gifted access v2
# =============================================================================


@router.get("/users/{user_id}/gifts", dependencies=[Depends(require_global_admin_or_any_product_admin)])
async def list_user_gifts(user_id: str, db: Session = Depends(get_db), admin: User = Depends(get_current_user)) -> list[dict]:
    _require_target(db, user_id)
    visible = rbac_service.admin_visible_product_ids(db, admin.id)
    history = gift_service.list_gift_history(db, user_id)
    if visible is not None:
        history = [g for g in history if g.product_id in visible]
    return [_gift_out(db, g) for g in history]


def _gift_out(db: Session, gift: GiftedAccess) -> dict:
    plan = db.get(Plan, gift.plan_id)
    return {
        "id": gift.id, "product_id": gift.product_id, "plan_slug": plan.slug if plan else None,
        "status": gift.status, "reason": gift.reason, "granted_at": gift.granted_at.isoformat(),
        "starts_at": gift.starts_at.isoformat(), "expires_at": gift.expires_at.isoformat() if gift.expires_at else None,
        "revoked_at": gift.revoked_at.isoformat() if gift.revoked_at else None, "revoke_reason": gift.revoke_reason,
    }


@router.post("/users/{user_id}/gifts", dependencies=[Depends(rate_limit_admin_mutation)])
async def grant_gift(user_id: str, payload: dict, db: Session = Depends(get_db), admin: User = Depends(get_current_user)) -> dict:
    # product_id lives in the body, not a path/query parameter, so the
    # product-scope check happens here rather than as a route dependency
    # (mission 6 continuation: product-scoped RBAC).
    if not rbac_service.is_global_or_product_admin(db, admin.id, payload["product_id"]):
        raise ForbiddenError(f"You do not have admin access to product '{payload['product_id']}'.")
    target = _require_target(db, user_id)
    plan = entitlement_service.get_plan(db, payload["product_id"], payload["plan_slug"])
    expires_at = datetime.fromisoformat(payload["expires_at"]) if payload.get("expires_at") else None
    gift = gift_service.grant_gift(db, admin, target, plan, payload.get("reason"), expires_at)
    return _gift_out(db, gift)


@router.delete("/gifts/{gift_id}", dependencies=[Depends(rate_limit_admin_mutation)])
async def revoke_gift(gift_id: str, payload: dict | None = None, db: Session = Depends(get_db), admin: User = Depends(get_current_user)) -> dict:
    existing = db.get(GiftedAccess, gift_id)
    if existing is None:
        raise NotFoundError("Gift not found.")
    if not rbac_service.is_global_or_product_admin(db, admin.id, existing.product_id):
        raise ForbiddenError(f"You do not have admin access to product '{existing.product_id}'.")
    reason = (payload or {}).get("reason")
    gift = gift_service.revoke_gift(db, admin, gift_id, reason)
    return _gift_out(db, gift)


# =============================================================================
# Mission 6 (Phase 15): bundles
# =============================================================================


@router.get("/bundles", dependencies=[Depends(require_global_admin)])
async def list_bundles(db: Session = Depends(get_db)) -> list[dict]:
    bundles = db.execute(select(Bundle).order_by(Bundle.created_at.desc())).scalars().all()
    return [{"id": b.id, "slug": b.slug, "name": b.name, "status": b.status} for b in bundles]


@router.post("/bundles", dependencies=[Depends(require_global_admin), Depends(rate_limit_admin_mutation)])
async def create_bundle(payload: dict, db: Session = Depends(get_db), admin: User = Depends(require_global_admin)) -> dict:
    bundle = bundle_service.create_bundle(db, admin, payload["slug"], payload["name"])
    return {"id": bundle.id, "slug": bundle.slug, "name": bundle.name}


@router.post("/bundles/{bundle_id}/products", dependencies=[Depends(require_global_admin), Depends(rate_limit_admin_mutation)])
async def add_bundle_product(bundle_id: str, payload: dict, db: Session = Depends(get_db)) -> dict:
    bundle = bundle_service.get_bundle(db, bundle_id)
    plan = entitlement_service.get_plan(db, payload["product_id"], payload["plan_slug"])
    row = bundle_service.add_product_plan(db, bundle, plan)
    return {"bundle_id": bundle.id, "product_id": row.product_id, "plan_id": row.plan_id}


@router.get("/bundles/{bundle_id}", dependencies=[Depends(require_global_admin)])
async def get_bundle_detail(bundle_id: str, db: Session = Depends(get_db)) -> dict:
    bundle = bundle_service.get_bundle(db, bundle_id)
    products = bundle_service.list_bundle_products(db, bundle_id)
    return {
        "id": bundle.id, "slug": bundle.slug, "name": bundle.name, "status": bundle.status,
        "products": [{"product_id": p.product_id, "plan_id": p.plan_id} for p in products],
    }


@router.post("/users/{user_id}/bundles/{bundle_id}/access", dependencies=[Depends(require_global_admin), Depends(rate_limit_admin_mutation)])
async def grant_bundle_access(user_id: str, bundle_id: str, payload: dict, db: Session = Depends(get_db), admin: User = Depends(require_global_admin)) -> dict:
    target = _require_target(db, user_id)
    bundle = bundle_service.get_bundle(db, bundle_id)
    expires_at = datetime.fromisoformat(payload["expires_at"]) if payload.get("expires_at") else None
    access = bundle_service.grant_bundle_access(db, admin, target, bundle, payload.get("source", "internal"), expires_at)
    return {"id": access.id, "bundle_id": access.bundle_id, "status": access.status}


@router.delete("/bundle-access/{access_id}", dependencies=[Depends(require_global_admin), Depends(rate_limit_admin_mutation)])
async def revoke_bundle_access(access_id: str, payload: dict | None = None, db: Session = Depends(get_db), admin: User = Depends(require_global_admin)) -> dict:
    access = bundle_service.revoke_bundle_access(db, admin, access_id, (payload or {}).get("reason"))
    return {"id": access.id, "status": access.status}


@router.get("/users/{user_id}/bundle-access", dependencies=[Depends(require_global_admin)])
async def list_user_bundle_access(user_id: str, db: Session = Depends(get_db)) -> list[dict]:
    _require_target(db, user_id)
    return [
        {"id": a.id, "bundle_id": a.bundle_id, "status": a.status, "source": a.source,
         "expires_at": a.expires_at.isoformat() if a.expires_at else None}
        for a in bundle_service.list_user_bundle_access(db, user_id)
    ]


# =============================================================================
# Mission 6 (Phase 31): subscriptions / payments / billing webhooks (read)
# =============================================================================


@router.get("/subscriptions", dependencies=[Depends(require_global_admin_or_any_product_admin)])
async def list_subscriptions(db: Session = Depends(get_db), admin: User = Depends(get_current_user), user_id: str | None = Query(default=None), limit: int = Query(default=100, le=500)) -> list[dict]:
    visible = rbac_service.admin_visible_product_ids(db, admin.id)
    query = select(Subscription).order_by(Subscription.created_at.desc()).limit(limit)
    if user_id:
        query = query.where(Subscription.user_id == user_id)
    if visible is not None:
        query = query.where(Subscription.product_id.in_(visible))
    rows = db.execute(query).scalars().all()
    return [
        {"id": s.id, "user_id": s.user_id, "product_id": s.product_id, "provider": s.provider,
         "status": s.status, "current_period_end": s.current_period_end.isoformat() if s.current_period_end else None,
         "cancel_at_period_end": s.cancel_at_period_end}
        for s in rows
    ]


@router.get("/payments", dependencies=[Depends(require_global_admin_or_any_product_admin)])
async def list_payments(db: Session = Depends(get_db), admin: User = Depends(get_current_user), user_id: str | None = Query(default=None), limit: int = Query(default=100, le=500)) -> list[dict]:
    """Every row here is real (mission-brief Phase 12/36): only
    `webhook_service._apply_transaction_event` ever inserts a
    `PaymentRecord`, and only from a signature-verified
    `transaction.completed` provider event - nothing in this listing is
    ever estimated or fabricated. A product-scoped admin (mission 6
    continuation) sees only their own product's payments - "Filey admin
    must not see Loady's payments" applies here exactly as much as to
    prices/plans."""
    visible = rbac_service.admin_visible_product_ids(db, admin.id)
    query = select(PaymentRecord).order_by(PaymentRecord.created_at.desc()).limit(limit)
    if user_id:
        query = query.where(PaymentRecord.user_id == user_id)
    if visible is not None:
        query = query.where(PaymentRecord.product_id.in_(visible))
    rows = db.execute(query).scalars().all()
    return [
        {"id": p.id, "user_id": p.user_id, "product_id": p.product_id, "provider": p.provider,
         "amount_cents": p.amount_cents, "currency": p.currency, "status": p.status,
         "refunded_amount_cents": p.refunded_amount_cents, "created_at": p.created_at.isoformat()}
        for p in rows
    ]


@router.get("/billing/webhooks", dependencies=[Depends(require_global_admin)])
async def list_billing_webhooks(db: Session = Depends(get_db), status_filter: str | None = Query(default=None, alias="status"), limit: int = Query(default=100, le=500)) -> list[dict]:
    query = select(BillingWebhookEvent).order_by(BillingWebhookEvent.received_at.desc()).limit(limit)
    if status_filter:
        query = query.where(BillingWebhookEvent.status == status_filter)
    rows = db.execute(query).scalars().all()
    return [
        {"id": w.id, "provider": w.provider, "event_type": w.event_type, "status": w.status,
         "failure_reason": w.failure_reason, "retry_count": w.retry_count, "received_at": w.received_at.isoformat()}
        for w in rows
    ]


@router.post("/billing/webhooks/{webhook_event_id}/replay", dependencies=[Depends(require_super_admin), Depends(rate_limit_admin_mutation)])
async def replay_billing_webhook(webhook_event_id: str, db: Session = Depends(get_db)) -> dict:
    journal = db.get(BillingWebhookEvent, webhook_event_id)
    if journal is None:
        raise NotFoundError("Webhook event not found.")
    provider = billing.get_billing_provider(journal.provider)
    result = webhook_service.replay_failed_event(db, provider, webhook_event_id)
    return {"id": result.id, "status": result.status}


# =============================================================================
# Mission 6 continuation: service clients. Granting a scope / configuring
# a webhook is now product-scoped (`require_client_admin` also accepts a
# global admin) - a product's own admin may configure ITS OWN client
# without needing super_admin. Registering a brand-new client and
# rotating an existing secret remain super_admin-only (see
# `api/deps.py::require_client_admin`'s own docstring for why).
# =============================================================================


@router.post("/clients/{client_id}/service-grants", dependencies=[Depends(rate_limit_admin_mutation)])
async def grant_service_scope(client_id: str, payload: dict, db: Session = Depends(get_db), admin: User = Depends(require_client_admin)) -> dict:
    client = db.get(OAuthClient, client_id)
    if client is None:
        raise NotFoundError("Client not found.")
    grant = service_auth.grant_scope(db, admin, client, payload["scope"])
    return {"client_id": client_id, "scope": grant.scope}


@router.get("/clients/{client_id}/service-grants", dependencies=[Depends(require_client_admin)])
async def list_service_scopes(client_id: str, db: Session = Depends(get_db)) -> list[str]:
    return service_auth.list_scopes(db, client_id)


@router.post("/clients/{client_id}/rotate-secret", dependencies=[Depends(require_super_admin), Depends(rate_limit_admin_mutation)])
async def rotate_client_secret(client_id: str, db: Session = Depends(get_db), admin: User = Depends(require_super_admin)) -> dict:
    client = db.get(OAuthClient, client_id)
    if client is None:
        raise NotFoundError("Client not found.")
    raw_secret = service_auth.rotate_client_secret(db, admin, client)
    return {"client_id": client_id, "client_secret": raw_secret}


@router.post("/clients/{client_id}/webhook", dependencies=[Depends(rate_limit_admin_mutation)])
async def configure_client_webhook(client_id: str, payload: dict, db: Session = Depends(get_db), admin: User = Depends(require_client_admin)) -> dict:
    """Opts a product's registered client into outbound Platform Core
    webhooks (mission-brief Phase 41). The returned signing secret is
    shown exactly once, matching the existing client-secret/rotate-secret
    precedent - it is never retrievable again after this response."""
    client = db.get(OAuthClient, client_id)
    if client is None:
        raise NotFoundError("Client not found.")
    raw_secret = service_auth.configure_webhook(db, admin, client, payload["webhook_url"])
    return {"client_id": client_id, "webhook_url": client.webhook_url, "webhook_signing_secret": raw_secret}


@router.get("/system-health", dependencies=[Depends(require_global_admin)])
async def system_health(db: Session = Depends(get_db)) -> dict:
    """Grand Admin System Health (mission-brief Phase 48) - operational
    signals only, never secrets and never a raw exception message. This
    is deliberately separate from `/ready` (`main.py`): a webhook backlog
    or a run of failed deliveries is a business-level signal an admin
    should see, not a reason to fail container orchestration health
    checks and get restart-looped (see `/ready`'s own docstring for why
    that distinction matters)."""
    from app.database.models import BillingWebhookEvent, OutboxEvent
    from app.security.jwt_keys import signing_key_is_available

    outbox_pending = db.execute(select(func.count(OutboxEvent.id)).where(OutboxEvent.status == "pending")).scalar_one()
    outbox_failed = db.execute(select(func.count(OutboxEvent.id)).where(OutboxEvent.status == "failed")).scalar_one()
    webhook_failed = db.execute(select(func.count(BillingWebhookEvent.id)).where(BillingWebhookEvent.status == "failed")).scalar_one()
    webhook_pending = db.execute(select(func.count(BillingWebhookEvent.id)).where(BillingWebhookEvent.status == "pending")).scalar_one()

    # Reaching this line at all already proves DB connectivity - `get_db`
    # would have raised before this route body ever ran otherwise.
    return {
        "database": True,
        "signing_key_configured": signing_key_is_available(),
        "outbox": {"pending": outbox_pending, "failed": outbox_failed},
        "billing_webhooks": {"pending": webhook_pending, "failed": webhook_failed},
    }


@router.get("/revenue/metrics", dependencies=[Depends(require_global_admin_or_any_product_admin)])
async def revenue_metrics(
    db: Session = Depends(get_db), admin: User = Depends(get_current_user),
    product_id: str | None = Query(default=None), plan_id: str | None = Query(default=None),
    start: str | None = Query(default=None), end: str | None = Query(default=None),
) -> dict:
    """Mission-brief Phase 12. A product-scoped admin MUST pass their own
    product_id - a global-metrics query (no product_id) is global-admin
    only, since it would otherwise aggregate every product's revenue,
    including ones the caller has no access to."""
    if product_id is not None:
        if not rbac_service.is_global_or_product_admin(db, admin.id, product_id):
            raise ForbiddenError(f"You do not have admin access to product '{product_id}'.")
    elif not rbac_service.is_global_admin(db, admin.id):
        raise ForbiddenError("An ecosystem-wide (no product_id) metrics query requires global admin.")

    metrics = revenue_service.compute_metrics(
        db, product_id=product_id, plan_id=plan_id,
        start=datetime.fromisoformat(start) if start else None,
        end=datetime.fromisoformat(end) if end else None,
    )
    return {
        "scope": metrics.scope, "revenue_cents": metrics.revenue_cents, "refunded_cents": metrics.refunded_cents,
        "net_revenue_cents": metrics.net_revenue_cents, "paid_subscribers": metrics.paid_subscribers,
        "mrr_cents": metrics.mrr_cents, "arr_cents": metrics.arr_cents, "arpu_cents": metrics.arpu_cents,
        "churn_rate": metrics.churn_rate, "notes": metrics.notes,
    }


@router.get("/outbox", dependencies=[Depends(require_global_admin_or_any_product_admin)])
async def list_outbox_events(db: Session = Depends(get_db), admin: User = Depends(get_current_user), status_filter: str | None = Query(default=None, alias="status"), limit: int = Query(default=100, le=500)) -> list[dict]:
    from app.database.models import OutboxEvent

    visible = rbac_service.admin_visible_product_ids(db, admin.id)
    query = select(OutboxEvent).order_by(OutboxEvent.created_at.desc()).limit(limit)
    if status_filter:
        query = query.where(OutboxEvent.status == status_filter)
    if visible is not None:
        # A product-less (global/system) event has product_id IS NULL -
        # never shown to a product-scoped-only admin, since it isn't
        # theirs to see either.
        query = query.where(OutboxEvent.product_id.in_(visible))
    rows = db.execute(query).scalars().all()
    return [
        {"id": e.id, "event_type": e.event_type, "product_id": e.product_id, "status": e.status,
         "attempts": e.attempts, "last_error": e.last_error, "created_at": e.created_at.isoformat()}
        for e in rows
    ]
