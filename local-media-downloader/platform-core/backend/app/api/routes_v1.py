"""Versioned (`/api/v1`) resource endpoints (mission-brief section 29):

- Bearer-authenticated endpoints called BY a product's own backend on
  behalf of one of its signed-in users (`/api/v1/entitlements/me`) —
  scoped strictly to the calling client's own `product_id`, so Product A's
  backend can never read Product B's entitlement for the same user
  (mission-brief section 31, step 10).
- Central-session-cookie-authenticated endpoints for the future unified
  account portal (mission-brief section 19) — "My Products",
  "Subscriptions" foundations.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.api.deps import BearerPrincipal, get_bearer_principal, get_current_user, get_db
from app.database.models import Plan, User
from app.models.enums import AuditAction
from app.security.jwt_tokens import introspect_oidc_access_token
from app.services import audit_service, entitlement_service, product_service
from app.utils.exceptions import AuthError

# Mission 6 (Phase 23): "user-visible security events" - a deliberately
# small, non-technical allowlist filtered out of the full AuditLog (which
# also carries admin/system actions no end user should see, e.g. another
# admin's role grants). New event types are added here explicitly, never
# by defaulting to "show everything."
_SECURITY_EVENT_ACTIONS = {
    AuditAction.USER_SIGNUP.value,
    AuditAction.USER_LOGIN.value,
    AuditAction.PASSWORD_CHANGED.value,
    AuditAction.SESSION_REVOKED.value,
    AuditAction.ALL_SESSIONS_REVOKED.value,
}

router = APIRouter(prefix="/api/v1", tags=["v1"])


def _entitlement_view(session: Session, entitlement) -> dict:
    plan = session.get(Plan, entitlement.plan_id)
    return {
        "product_id": entitlement.product_id,
        "plan_slug": plan.slug if plan else None,
        "plan_name": plan.name if plan else None,
        "source": entitlement.source,
        "status": entitlement.status,
        "starts_at": entitlement.starts_at.isoformat(),
        "expires_at": entitlement.expires_at.isoformat() if entitlement.expires_at else None,
    }


@router.get("/entitlements/me")
async def my_entitlement_for_calling_product(
    db: Session = Depends(get_db), principal: BearerPrincipal = Depends(get_bearer_principal)
) -> dict:
    """Called by a product's backend with the user's OIDC access token.
    Returns only that product's entitlement — never another product's,
    regardless of what the same global user holds elsewhere."""
    if principal.client.product_id is None:
        return {"entitled": False, "entitlement": None}
    entitlement = entitlement_service.get_active_entitlement(db, principal.user.id, principal.client.product_id)
    if entitlement is None:
        return {"entitled": False, "entitlement": None}
    return {"entitled": True, "entitlement": _entitlement_view(db, entitlement)}


@router.get("/me/status")
async def my_status(db: Session = Depends(get_db), authorization: Optional[str] = Header(default=None)) -> dict:
    """Bearer-authenticated account-status introspection (mission 4, phase
    12 — see docs/platform/SESSION_REVOCATION.md). Deliberately does NOT
    gate on `user.status` the way `get_bearer_principal` does for every
    other `/api/v1` route: a disabled account still gets a normal 200 here
    with `"status": "disabled"` in the body, so a product's backend can
    positively distinguish "this account is centrally disabled" from "this
    bearer token itself is invalid/expired" (both would otherwise collapse
    into the same generic 401, which is exactly right for every other
    endpoint but wrong for the one endpoint whose entire purpose is to let
    a product periodically re-validate an already-authenticated user's
    standing without forcing a fresh login)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError("Missing bearer token.")
    token = authorization[len("bearer "):].strip()
    payload = introspect_oidc_access_token(token)
    if payload is None:
        raise AuthError("Invalid or expired access token.")
    user = db.get(User, payload.get("sub"))
    if user is None:
        raise AuthError("Invalid or expired access token.")
    return {"sub": user.id, "status": user.status}


@router.get("/me/memberships")
async def my_memberships(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict]:
    memberships = product_service.list_memberships(db, user.id)
    return [
        {
            "product_id": m.product_id,
            "status": m.status,
            "first_seen_at": m.first_seen_at.isoformat(),
            "last_seen_at": m.last_seen_at.isoformat(),
        }
        for m in memberships
    ]


@router.get("/me/entitlements")
async def my_entitlements(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict]:
    entitlements = entitlement_service.list_entitlements_for_user(db, user.id)
    return [_entitlement_view(db, e) for e in entitlements]


@router.get("/me/security-events")
async def my_security_events(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict]:
    entries = audit_service.list_for_actor(db, user.id, actions=_SECURITY_EVENT_ACTIONS)
    return [
        {"action": e.action, "created_at": e.created_at.isoformat(), "target_type": e.target_type}
        for e in entries
    ]


@router.get("/products")
async def list_products_endpoint(db: Session = Depends(get_db), _user: User = Depends(get_current_user)) -> list[dict]:
    products = product_service.list_products(db)
    return [
        {"id": p.id, "name": p.name, "domain": p.domain, "status": p.status, "icon_ref": p.icon_ref}
        for p in products
    ]
