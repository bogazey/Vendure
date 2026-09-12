"""Admin surface: overview metrics, user search/detail/credit-grants/status,
Paddle billing-event visibility, and the admin action audit log. All routes
require the `admin` role (see api/deps.require_admin) - never trust a
frontend-only "isAdmin" flag.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.api.routes_health import compute_health
from app.database.commercial_models import AdminActionLog, BillingEvent, Subscription, UsagePeriod, User
from app.models.commercial_enums import AdminActionType, AdPlacementId, Plan, SubscriptionProvider, UserStatus
from app.models.commercial_schemas import (
    AdminActionLogOut,
    AdminAdPlacementOut,
    AdminBillingEventOut,
    AdminGrantCreditsRequest,
    AdminHealthOut,
    AdminOverviewOut,
    AdminSetAccountStatusRequest,
    AdminUpdateAdPlacementRequest,
    AdminUpdateSubscriptionRequest,
    AdminUserListOut,
    AdminUserOut,
)
from app.services import ad_placement_service, gift_subscription_service
from app.services.account_service import ACTIVE_SUBSCRIPTION_STATUSES, account_service
from app.services.admin_audit_service import admin_audit_service
from app.services.plan_policy import get_policy
from app.services.usage_service import usage_service
from app.utils.exceptions import ForbiddenError, UnavailableMediaError

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _to_admin_user_out(session: Session, user: User) -> AdminUserOut:
    plan, subscription = account_service.get_current_plan(session, user.id)
    usage = usage_service.get_usage_out(session, user, plan, subscription)
    plan_base_credits = get_policy(plan).monthly_credits
    credits_bonus = None
    if usage.credits_included is not None and plan_base_credits is not None:
        credits_bonus = max(0, usage.credits_included - plan_base_credits)

    subscription_provider = subscription.provider if subscription else "none"
    gifted_granted_at = None
    gifted_granted_by_email = None
    gifted_reason = None
    if subscription is not None and subscription.provider == SubscriptionProvider.GIFTED.value:
        gifted_granted_at = subscription.created_at
        gifted_reason = subscription.granted_reason
        if subscription.granted_by_admin_id:
            granter = session.get(User, subscription.granted_by_admin_id)
            gifted_granted_by_email = granter.email if granter else None

    return AdminUserOut(
        id=user.id,
        email=user.email,
        status=user.status,
        role=user.role,
        plan=plan,
        subscription_status=subscription.status if subscription else "none",
        credits_used=usage.credits_used,
        credits_included=usage.credits_included,
        credits_bonus=credits_bonus,
        created_at=user.created_at,
        subscription_provider=subscription_provider,
        gifted_granted_at=gifted_granted_at,
        gifted_granted_by_email=gifted_granted_by_email,
        gifted_reason=gifted_reason,
    )


def _emails_by_id(session: Session, user_ids: set[str]) -> dict[str, str]:
    ids = [uid for uid in user_ids if uid]
    if not ids:
        return {}
    rows = session.execute(select(User.id, User.email).where(User.id.in_(ids))).all()
    return {row[0]: row[1] for row in rows}


def _to_billing_event_out_list(session: Session, events: list[BillingEvent]) -> list[AdminBillingEventOut]:
    emails = _emails_by_id(session, {e.user_id for e in events if e.user_id})
    return [
        AdminBillingEventOut(
            provider_event_id=e.provider_event_id,
            event_type=e.event_type,
            processed_at=e.processed_at,
            status=e.status,
            user_id=e.user_id,
            user_email=emails.get(e.user_id) if e.user_id else None,
        )
        for e in events
    ]


def _to_admin_action_log_out_list(session: Session, entries: list[AdminActionLog]) -> list[AdminActionLogOut]:
    ids: set[str] = set()
    for entry in entries:
        ids.add(entry.admin_id)
        if entry.target_user_id:
            ids.add(entry.target_user_id)
    emails = _emails_by_id(session, ids)
    return [
        AdminActionLogOut(
            id=entry.id,
            admin_id=entry.admin_id,
            admin_email=emails.get(entry.admin_id),
            action=entry.action,
            target_user_id=entry.target_user_id,
            target_email=emails.get(entry.target_user_id) if entry.target_user_id else None,
            details=entry.details,
            created_at=entry.created_at,
        )
        for entry in entries
    ]


@router.get("/overview", response_model=AdminOverviewOut, dependencies=[Depends(require_admin)])
async def get_overview(db: Session = Depends(get_db)) -> AdminOverviewOut:
    total_users = db.execute(select(func.count()).select_from(User)).scalar_one()
    active_users = db.execute(
        select(func.count()).select_from(User).where(User.status == UserStatus.ACTIVE.value)
    ).scalar_one()

    # Plan breakdown: for each user_id with a currently-active-ish
    # subscription, take only their most-recently-updated such row (a user
    # should have at most one, but this stays correct even if not) via a
    # subquery-join rather than a window function, so it runs unchanged on
    # both SQLite (dev) and PostgreSQL (production). Restricted to
    # provider="paddle" - paid_subscribers/pro_count/creator_count are
    # authoritative *revenue* figures and must never include a gifted
    # subscription (see gift_subscription_service.py and
    # docs/ANALYTICS.md "Gifted subscriptions are not revenue").
    latest_active_sub = (
        select(Subscription.user_id, func.max(Subscription.updated_at).label("max_updated"))
        .where(Subscription.status.in_(ACTIVE_SUBSCRIPTION_STATUSES), Subscription.provider == SubscriptionProvider.PADDLE.value)
        .group_by(Subscription.user_id)
        .subquery()
    )
    plan_rows = db.execute(
        select(Subscription.plan, func.count())
        .select_from(Subscription)
        .join(
            latest_active_sub,
            (Subscription.user_id == latest_active_sub.c.user_id)
            & (Subscription.updated_at == latest_active_sub.c.max_updated),
        )
        .where(Subscription.status.in_(ACTIVE_SUBSCRIPTION_STATUSES), Subscription.provider == SubscriptionProvider.PADDLE.value)
        .group_by(Subscription.plan)
    ).all()
    plan_counts = {plan: count for plan, count in plan_rows}
    pro_count = plan_counts.get(Plan.PRO.value, 0)
    creator_count = plan_counts.get(Plan.CREATOR.value, 0)
    paid_subscribers = pro_count + creator_count

    # Counted and reported entirely separately - never added into
    # paid_subscribers (see AdminOverviewOut.gifted_subscribers).
    gifted_subscribers = db.execute(
        select(func.count(func.distinct(Subscription.user_id))).where(
            Subscription.status.in_(ACTIVE_SUBSCRIPTION_STATUSES),
            Subscription.provider == SubscriptionProvider.GIFTED.value,
        )
    ).scalar_one()

    free_count = max(0, total_users - paid_subscribers - gifted_subscribers)

    now = datetime.now(timezone.utc)
    credits_consumed = db.execute(
        select(func.coalesce(func.sum(UsagePeriod.credits_used), 0)).where(UsagePeriod.period_end >= now)
    ).scalar_one()

    failure_rows = list(
        db.execute(
            select(BillingEvent)
            .where(BillingEvent.event_type == "transaction.payment_failed")
            .order_by(BillingEvent.processed_at.desc())
            .limit(10)
        ).scalars()
    )

    recent_actions = admin_audit_service.list_recent(db, limit=10)

    return AdminOverviewOut(
        total_users=total_users,
        active_users=active_users,
        disabled_users=max(0, total_users - active_users),
        paid_subscribers=paid_subscribers,
        free_count=free_count,
        pro_count=pro_count,
        creator_count=creator_count,
        gifted_subscribers=gifted_subscribers,
        credits_consumed_current_period=int(credits_consumed),
        recent_billing_failures=_to_billing_event_out_list(db, failure_rows),
        recent_admin_actions=_to_admin_action_log_out_list(db, recent_actions),
    )


@router.get("/health", response_model=AdminHealthOut, dependencies=[Depends(require_admin)])
async def get_admin_health() -> AdminHealthOut:
    health = compute_health()
    return AdminHealthOut(
        status=health.status,
        database_ok=health.database_ok,
        ffmpeg_available=health.ffmpeg_available,
        ytdlp_version=health.ytdlp_version,
        download_dir_writable=health.download_dir_writable,
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
async def grant_credits(
    user_id: str,
    payload: AdminGrantCreditsRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminUserOut:
    user = db.get(User, user_id)
    if user is None:
        raise UnavailableMediaError("User not found.")
    plan, subscription = account_service.get_current_plan(db, user.id)
    usage_service.admin_grant(db, user, plan, subscription, payload.credits, payload.reason)
    admin_audit_service.record(
        db, admin, AdminActionType.GRANT_CREDITS, user.id, {"credits": payload.credits, "reason": payload.reason}
    )
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
    previous_status = user.status
    user.status = payload.status
    if previous_status != payload.status:
        action = (
            AdminActionType.DISABLE_ACCOUNT if payload.status == "disabled" else AdminActionType.REACTIVATE_ACCOUNT
        )
        admin_audit_service.record(
            db, admin, action, user.id, {"previous_status": previous_status, "new_status": payload.status}
        )
    return _to_admin_user_out(db, user)


@router.patch("/users/{user_id}/subscription", response_model=AdminUserOut, dependencies=[Depends(require_admin)])
async def update_user_subscription(
    user_id: str,
    payload: AdminUpdateSubscriptionRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminUserOut:
    """Admin-managed Gifted Subscription: grant/change (plan=pro|creator) or
    revoke (plan=free). Never touches Paddle in any way - see
    gift_subscription_service.py. Blocked outright (409) if the user
    currently has an active Paddle subscription; the frontend is expected
    to disable these controls in that state too, but this is the
    server-authoritative check that actually matters."""
    user = db.get(User, user_id)
    if user is None:
        raise UnavailableMediaError("User not found.")
    if payload.plan == Plan.FREE:
        gift_subscription_service.revoke(db, admin, user, payload.reason)
    else:
        gift_subscription_service.grant_or_change(db, admin, user, payload.plan, payload.reason)
    return _to_admin_user_out(db, user)


@router.get("/billing-events", response_model=list[AdminBillingEventOut], dependencies=[Depends(require_admin)])
async def list_billing_events(
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[AdminBillingEventOut]:
    events = list(
        db.execute(select(BillingEvent).order_by(BillingEvent.processed_at.desc()).limit(limit)).scalars()
    )
    return _to_billing_event_out_list(db, events)


@router.get("/audit-log", response_model=list[AdminActionLogOut], dependencies=[Depends(require_admin)])
async def list_audit_log(
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    target_user_id: str | None = Query(default=None),
) -> list[AdminActionLogOut]:
    entries = admin_audit_service.list_recent(db, limit=limit, target_user_id=target_user_id)
    return _to_admin_action_log_out_list(db, entries)


def _to_admin_ad_placement_out(placement) -> AdminAdPlacementOut:
    return AdminAdPlacementOut(
        id=placement.id,
        description=placement.description,
        enabled=placement.enabled,
        provider=placement.provider,
        public_slot_id=placement.public_slot_id,
        updated_at=placement.updated_at,
    )


@router.get("/ads/placements", response_model=list[AdminAdPlacementOut], dependencies=[Depends(require_admin)])
async def list_ad_placements(db: Session = Depends(get_db)) -> list[AdminAdPlacementOut]:
    return [_to_admin_ad_placement_out(p) for p in ad_placement_service.list_placements(db)]


@router.patch("/ads/placements/{placement_id}", response_model=AdminAdPlacementOut, dependencies=[Depends(require_admin)])
async def update_ad_placement(
    placement_id: AdPlacementId,
    payload: AdminUpdateAdPlacementRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminAdPlacementOut:
    placement = ad_placement_service.get_placement(db, placement_id.value)
    if placement is None:
        raise UnavailableMediaError("Ad placement not found.")
    result = ad_placement_service.update_placement(db, placement, payload)
    if result.changed_fields:
        admin_audit_service.record(
            db, admin, result.action, None, {"placement": placement.id, "changed": result.changed_fields}
        )
    return _to_admin_ad_placement_out(result.placement)
