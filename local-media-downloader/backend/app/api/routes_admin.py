"""Minimal admin surface: view/search users, inspect plan+usage+billing
state, grant credits, enable/disable accounts. All routes require the
`admin` role (see api/deps.require_admin) - never trust a frontend-only
"isAdmin" flag.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.database.commercial_models import BillingEvent, User
from app.models.commercial_schemas import (
    AdminGrantCreditsRequest,
    AdminSetAccountStatusRequest,
    AdminUserListOut,
    AdminUserOut,
)
from app.services.account_service import account_service
from app.services.usage_service import usage_service
from app.utils.exceptions import ForbiddenError, UnavailableMediaError

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _to_admin_user_out(session: Session, user: User) -> AdminUserOut:
    plan, subscription = account_service.get_current_plan(session, user.id)
    usage = usage_service.get_usage_out(session, user, plan, subscription)
    return AdminUserOut(
        id=user.id,
        email=user.email,
        status=user.status,
        role=user.role,
        plan=plan,
        subscription_status=subscription.status if subscription else "none",
        credits_used=usage.credits_used,
        credits_included=usage.credits_included,
        created_at=user.created_at,
    )


@router.get("/users", response_model=AdminUserListOut, dependencies=[Depends(require_admin)])
async def list_users(
    db: Session = Depends(get_db),
    search: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AdminUserListOut:
    query = select(User)
    count_query = select(func.count()).select_from(User)
    if search:
        like = f"%{search}%"
        query = query.where(or_(User.email.ilike(like), User.id.ilike(like)))
        count_query = count_query.where(or_(User.email.ilike(like), User.id.ilike(like)))

    total = db.execute(count_query).scalar_one()
    users = db.execute(query.order_by(User.created_at.desc()).limit(limit).offset(offset)).scalars().all()
    return AdminUserListOut(users=[_to_admin_user_out(db, u) for u in users], total=total)


@router.get("/users/{user_id}", response_model=AdminUserOut, dependencies=[Depends(require_admin)])
async def get_user(user_id: str, db: Session = Depends(get_db)) -> AdminUserOut:
    user = db.get(User, user_id)
    if user is None:
        raise UnavailableMediaError("User not found.")
    return _to_admin_user_out(db, user)


@router.post("/users/{user_id}/grant-credits", response_model=AdminUserOut, dependencies=[Depends(require_admin)])
async def grant_credits(user_id: str, payload: AdminGrantCreditsRequest, db: Session = Depends(get_db)) -> AdminUserOut:
    user = db.get(User, user_id)
    if user is None:
        raise UnavailableMediaError("User not found.")
    plan, subscription = account_service.get_current_plan(db, user.id)
    usage_service.admin_grant(db, user, plan, subscription, payload.credits, payload.reason)
    return _to_admin_user_out(db, user)


@router.post("/users/{user_id}/status", response_model=AdminUserOut, dependencies=[Depends(require_admin)])
async def set_account_status(
    user_id: str, payload: AdminSetAccountStatusRequest, db: Session = Depends(get_db), admin: User = Depends(require_admin)
) -> AdminUserOut:
    user = db.get(User, user_id)
    if user is None:
        raise UnavailableMediaError("User not found.")
    if user.id == admin.id and payload.status == "disabled":
        raise ForbiddenError("You can't disable your own admin account.")
    user.status = payload.status
    return _to_admin_user_out(db, user)


@router.get("/billing-events", dependencies=[Depends(require_admin)])
async def list_billing_events(
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict]:
    events = db.execute(
        select(BillingEvent).order_by(BillingEvent.processed_at.desc()).limit(limit)
    ).scalars().all()
    return [
        {
            "provider_event_id": e.provider_event_id,
            "event_type": e.event_type,
            "processed_at": e.processed_at.isoformat(),
            "status": e.status,
        }
        for e in events
    ]
