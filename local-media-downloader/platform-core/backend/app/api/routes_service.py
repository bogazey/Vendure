"""Service-to-service (client-credentials) resource endpoints (mission-brief
Phases 36-37). Every route here is scoped to `principal.client.product_id`
- there is no path parameter or query parameter that lets a service caller
ask about a different product's data, and no route here can mutate a
plan, role, or entitlement (`ALLOWED_SERVICE_SCOPES` in `service_auth.py`
is read-only by construction, so this is enforced at the scope-definition
layer, not just by omission from this router)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import ServicePrincipal, get_db, require_service_scope
from app.services import capability_service, product_service
from app.utils.exceptions import ForbiddenError
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/v1/service", tags=["service"])


@router.get("/entitlements/{user_id}")
async def service_get_entitlements(
    user_id: str,
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(require_service_scope("service:entitlements:read")),
) -> dict:
    if principal.client.product_id is None:
        raise ForbiddenError("This service client is not registered to a specific product.")
    result = capability_service.resolve_effective_entitlements(db, user_id, principal.client.product_id)
    return {
        "product_id": result.product_id,
        "capabilities": result.capabilities,
        "sources": [
            {"kind": s.kind, "plan_id": s.plan_id, "plan_slug": s.plan_slug, "status": s.status,
             "expires_at": s.expires_at.isoformat() if s.expires_at else None}
            for s in result.sources
        ],
    }


@router.get("/memberships/{user_id}")
async def service_get_membership(
    user_id: str,
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(require_service_scope("service:memberships:read")),
) -> dict:
    if principal.client.product_id is None:
        raise ForbiddenError("This service client is not registered to a specific product.")
    memberships = product_service.list_memberships(db, user_id)
    own = next((m for m in memberships if m.product_id == principal.client.product_id), None)
    if own is None:
        return {"member": False}
    return {
        "member": True, "status": own.status,
        "first_seen_at": own.first_seen_at.isoformat(), "last_seen_at": own.last_seen_at.isoformat(),
    }
