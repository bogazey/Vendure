"""The Product Subscription Manager API (Mission 6 continuation, TOP
PRIORITY): plan/version/price CRUD, entirely product-scoped RBAC (a
product-scoped `admin` may manage only their own product's catalog - see
`api/deps.py::require_product_admin`/`require_plan_admin`/
`require_price_admin`, and `docs/platform/ADMIN_RBAC.md`)."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, rate_limit_admin_mutation, require_plan_admin, require_price_admin, require_product_admin
from app.database.models import Plan, PlanVersion, Price, User
from app.services import catalog_service
from app.utils.exceptions import NotFoundError

router = APIRouter(prefix="/api/v1/admin/catalog", tags=["catalog"])


def _plan_out(plan: Plan) -> dict:
    return {
        "id": plan.id, "product_id": plan.product_id, "slug": plan.slug, "name": plan.name,
        "description": plan.description, "status": plan.status, "is_public": plan.is_public,
        "sort_order": plan.sort_order, "upgrade_rank": plan.upgrade_rank,
        "gifted_eligible": plan.gifted_eligible, "trial_eligible": plan.trial_eligible,
        "current_version_id": plan.current_version_id,
    }


def _version_out(version: PlanVersion) -> dict:
    return {
        "id": version.id, "plan_id": version.plan_id, "version_number": version.version_number,
        "status": version.status, "capability_snapshot": version.capability_snapshot,
        "published_at": version.published_at.isoformat() if version.published_at else None,
    }


def _price_out(price: Price) -> dict:
    return {
        "id": price.id, "product_id": price.product_id, "plan_id": price.plan_id,
        "plan_version_id": price.plan_version_id, "provider": price.provider,
        "provider_price_id": price.provider_price_id, "currency": price.currency,
        "amount_cents": price.amount_cents, "interval": price.interval, "interval_count": price.interval_count,
        "is_public": price.is_public, "is_active": price.is_active,
        "created_at": price.created_at.isoformat(), "retired_at": price.retired_at.isoformat() if price.retired_at else None,
    }


# --- Plans ---------------------------------------------------------------------


@router.get("/products/{product_id}/plans", dependencies=[Depends(require_product_admin)])
async def list_plans(product_id: str, db: Session = Depends(get_db)) -> list[dict]:
    return [_plan_out(p) for p in catalog_service.list_plans(db, product_id)]


@router.post("/products/{product_id}/plans", dependencies=[Depends(rate_limit_admin_mutation)])
async def create_plan(product_id: str, payload: dict, db: Session = Depends(get_db), admin: User = Depends(require_product_admin)) -> dict:
    plan = catalog_service.create_plan(
        db, admin, product_id, payload["slug"], payload["name"],
        description=payload.get("description"), sort_order=payload.get("sort_order", 0),
        upgrade_rank=payload.get("upgrade_rank", 0), gifted_eligible=payload.get("gifted_eligible", True),
        trial_eligible=payload.get("trial_eligible", True), is_public=payload.get("is_public", True),
    )
    return _plan_out(plan)


@router.get("/plans/{plan_id}", dependencies=[Depends(require_plan_admin)])
async def get_plan(plan_id: str, db: Session = Depends(get_db)) -> dict:
    return _plan_out(catalog_service.get_plan_or_404(db, plan_id))


@router.patch("/plans/{plan_id}", dependencies=[Depends(rate_limit_admin_mutation)])
async def update_plan(plan_id: str, payload: dict, db: Session = Depends(get_db), admin: User = Depends(require_plan_admin)) -> dict:
    plan = catalog_service.get_plan_or_404(db, plan_id)
    catalog_service.update_plan(db, admin, plan, **payload)
    return _plan_out(plan)


@router.post("/plans/{plan_id}/archive", dependencies=[Depends(rate_limit_admin_mutation)])
async def archive_plan(plan_id: str, db: Session = Depends(get_db), admin: User = Depends(require_plan_admin)) -> dict:
    plan = catalog_service.get_plan_or_404(db, plan_id)
    catalog_service.archive_plan(db, admin, plan)
    return _plan_out(plan)


@router.post("/plans/{plan_id}/activate", dependencies=[Depends(rate_limit_admin_mutation)])
async def activate_plan(plan_id: str, db: Session = Depends(get_db), admin: User = Depends(require_plan_admin)) -> dict:
    plan = catalog_service.get_plan_or_404(db, plan_id)
    catalog_service.activate_plan(db, admin, plan)
    return _plan_out(plan)


@router.get("/plans/{plan_id}/stats", dependencies=[Depends(require_plan_admin)])
async def plan_stats(plan_id: str, db: Session = Depends(get_db)) -> dict:
    return catalog_service.plan_stats(db, plan_id)


# --- Plan versions ---------------------------------------------------------------


@router.get("/plans/{plan_id}/versions", dependencies=[Depends(require_plan_admin)])
async def list_versions(plan_id: str, db: Session = Depends(get_db)) -> list[dict]:
    return [_version_out(v) for v in catalog_service.list_plan_versions(db, plan_id)]


@router.post("/plans/{plan_id}/versions", dependencies=[Depends(rate_limit_admin_mutation)])
async def publish_version(plan_id: str, db: Session = Depends(get_db), admin: User = Depends(require_plan_admin)) -> dict:
    plan = catalog_service.get_plan_or_404(db, plan_id)
    version = catalog_service.publish_plan_version(db, admin, plan)
    return _version_out(version)


# --- Prices ------------------------------------------------------------------


@router.get("/plans/{plan_id}/prices", dependencies=[Depends(require_plan_admin)])
async def list_prices(plan_id: str, db: Session = Depends(get_db), only_active: bool = Query(default=False)) -> list[dict]:
    return [_price_out(p) for p in catalog_service.list_prices(db, plan_id, only_active=only_active)]


@router.post("/plans/{plan_id}/prices", dependencies=[Depends(rate_limit_admin_mutation)])
async def create_price(plan_id: str, payload: dict, db: Session = Depends(get_db), admin: User = Depends(require_plan_admin)) -> dict:
    plan = catalog_service.get_plan_or_404(db, plan_id)
    price = catalog_service.create_price(
        db, admin, plan, provider=payload["provider"], currency=payload["currency"],
        amount_cents=payload["amount_cents"], interval=payload["interval"],
        interval_count=payload.get("interval_count", 1), provider_price_id=payload.get("provider_price_id"),
        is_public=payload.get("is_public", True),
    )
    return _price_out(price)


@router.post("/prices/{price_id}/retire", dependencies=[Depends(rate_limit_admin_mutation)])
async def retire_price(price_id: str, payload: dict | None = None, db: Session = Depends(get_db), admin: User = Depends(require_price_admin)) -> dict:
    price = db.get(Price, price_id)
    if price is None:
        raise NotFoundError("Price not found.")
    catalog_service.retire_price(db, admin, price, (payload or {}).get("reason"))
    return _price_out(price)


@router.patch("/prices/{price_id}/visibility", dependencies=[Depends(rate_limit_admin_mutation)])
async def update_price_visibility(price_id: str, payload: dict, db: Session = Depends(get_db), admin: User = Depends(require_price_admin)) -> dict:
    price = db.get(Price, price_id)
    if price is None:
        raise NotFoundError("Price not found.")
    catalog_service.update_price_visibility(db, admin, price, is_public=payload["is_public"])
    return _price_out(price)
