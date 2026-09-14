"""Revenue metrics (Mission 6 continuation, Phase 12) - computed ONLY from
`PaymentRecord` (the sole table any revenue figure may ever be summed
from - see `BILLING.md`) and `Subscription`/`Price` for MRR/ARR. Every
metric that cannot be honestly computed from real data is returned as
`None` with an explanatory note, never estimated or fabricated (mission
brief: "never fabricate values").
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import PaymentRecord, Price, Subscription, SubscriptionItem

_ACTIVE_STATUSES = ("active", "trialing", "past_due")


@dataclass
class RevenueMetrics:
    scope: dict
    revenue_cents: int
    refunded_cents: int
    net_revenue_cents: int
    paid_subscribers: int
    mrr_cents: int | None
    arr_cents: int | None
    arpu_cents: float | None
    churn_rate: float | None
    notes: list[str] = field(default_factory=list)


def compute_metrics(
    session: Session,
    *,
    product_id: str | None = None,
    plan_id: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> RevenueMetrics:
    now = end or datetime.now(timezone.utc)
    notes: list[str] = []

    # --- Realized revenue: PaymentRecord only, never Entitlement/gift/subscription rows ---
    payment_query = select(PaymentRecord)
    if product_id:
        payment_query = payment_query.where(PaymentRecord.product_id == product_id)
    if start:
        payment_query = payment_query.where(func.coalesce(PaymentRecord.occurred_at, PaymentRecord.created_at) >= start)
    if end:
        payment_query = payment_query.where(func.coalesce(PaymentRecord.occurred_at, PaymentRecord.created_at) <= end)
    if plan_id:
        # PaymentRecord has no direct plan_id - resolved via its
        # subscription's item, when it has one (a one-time/non-subscription
        # payment has no plan to filter by and is simply excluded from a
        # plan-scoped query, not fabricated into one).
        payment_query = payment_query.join(Subscription, PaymentRecord.subscription_id == Subscription.id).join(
            SubscriptionItem, SubscriptionItem.subscription_id == Subscription.id
        ).where(SubscriptionItem.plan_id == plan_id)

    payments = session.execute(payment_query).scalars().all()
    revenue_cents = sum(p.amount_cents for p in payments if p.status in ("completed", "refunded", "partially_refunded"))
    refunded_cents = sum(p.refunded_amount_cents or 0 for p in payments)
    net_revenue_cents = revenue_cents - refunded_cents

    # --- Paid subscriber count: real, currently-active Subscription rows only ---
    sub_query = select(Subscription).where(Subscription.status.in_(_ACTIVE_STATUSES))
    if product_id:
        sub_query = sub_query.where(Subscription.product_id == product_id)
    if plan_id:
        sub_query = sub_query.join(SubscriptionItem, SubscriptionItem.subscription_id == Subscription.id).where(
            SubscriptionItem.plan_id == plan_id
        )
    active_subscriptions = session.execute(sub_query).scalars().all()
    paid_subscribers = len({s.user_id for s in active_subscriptions})

    # --- MRR: only from subscriptions with a resolvable, real Price row ---
    mrr_cents = 0
    resolvable = 0
    for subscription in active_subscriptions:
        if subscription.price_id is None:
            continue
        price = session.get(Price, subscription.price_id)
        if price is None:
            continue
        if price.interval == "month":
            mrr_cents += price.amount_cents // max(price.interval_count, 1)
            resolvable += 1
        elif price.interval == "year":
            mrr_cents += price.amount_cents // (12 * max(price.interval_count, 1))
            resolvable += 1
        # Other intervals (one_time, week, ...) deliberately not folded
        # into a "monthly recurring" figure - not a meaningful MRR
        # contribution, not fabricated into one either.

    if resolvable < len(active_subscriptions):
        notes.append(
            f"{len(active_subscriptions) - resolvable} of {len(active_subscriptions)} active subscription(s) "
            "have no resolvable Price row (pre-dates pricing, or a non-monthly/annual interval) and were "
            "excluded from MRR/ARR rather than estimated."
        )
    mrr = mrr_cents if active_subscriptions else None
    arr = mrr * 12 if mrr is not None else None
    if not active_subscriptions:
        notes.append("No active subscriptions in scope - MRR/ARR unavailable, not zero-by-assumption.")

    arpu = (net_revenue_cents / paid_subscribers) if paid_subscribers > 0 else None
    if paid_subscribers == 0:
        notes.append("No paid subscribers in scope - ARPU unavailable.")

    # --- Churn: only computed when there is a real cohort to divide by ---
    churn_rate: float | None = None
    if start is not None:
        cohort_query = select(func.count(Subscription.id)).where(
            Subscription.created_at <= start,
            (Subscription.canceled_at.is_(None)) | (Subscription.canceled_at > start),
        )
        if product_id:
            cohort_query = cohort_query.where(Subscription.product_id == product_id)
        cohort_size = session.execute(cohort_query).scalar_one()

        canceled_query = select(func.count(Subscription.id)).where(
            Subscription.canceled_at.is_not(None), Subscription.canceled_at >= start, Subscription.canceled_at <= now,
        )
        if product_id:
            canceled_query = canceled_query.where(Subscription.product_id == product_id)
        canceled_in_period = session.execute(canceled_query).scalar_one()

        if cohort_size > 0:
            churn_rate = canceled_in_period / cohort_size
        else:
            notes.append("No subscriptions existed at the start of the period - churn unavailable.")
    else:
        notes.append("No date range provided - churn requires a period to measure against, so it is unavailable.")

    return RevenueMetrics(
        scope={"product_id": product_id, "plan_id": plan_id, "start": start.isoformat() if start else None, "end": end.isoformat() if end else None},
        revenue_cents=revenue_cents, refunded_cents=refunded_cents, net_revenue_cents=net_revenue_cents,
        paid_subscribers=paid_subscribers, mrr_cents=mrr, arr_cents=arr, arpu_cents=arpu, churn_rate=churn_rate,
        notes=notes,
    )
