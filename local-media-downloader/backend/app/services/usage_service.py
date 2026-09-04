"""Credit/usage accounting: the single place that decides whether a user can
start a download right now, and owns the reserve -> commit/refund lifecycle.

Concurrency: reservation uses an atomic `UPDATE ... WHERE <still within
budget>` (not a SELECT-then-UPDATE) so two concurrent reservations racing for
the last credit can never both succeed and drive the balance negative - the
database itself enforces it per-row, portable across SQLite and PostgreSQL.
Period creation is similarly race-safe via a unique (user_id, period_start)
constraint plus a retry-by-reselect on conflict.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import case, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.database.commercial_models import Subscription, UsageEvent, UsagePeriod, User
from app.models.commercial_enums import Plan, ReservationStatus, UsageEventType
from app.models.commercial_schemas import UsageOut
from app.services.plan_policy import get_policy
from app.utils.exceptions import DailyLimitReachedError, InsufficientCreditsError


def _start_of_utc_day(at: datetime) -> datetime:
    return at.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


class UsageService:
    def get_or_create_current_period(
        self, session: Session, user: User, plan: Plan, subscription: Subscription | None
    ) -> UsagePeriod:
        now = datetime.now(timezone.utc)
        policy = get_policy(plan)

        if plan == Plan.FREE:
            period_start = _start_of_utc_day(now)
            period_end = period_start + timedelta(days=1)
        elif subscription and subscription.current_period_start and subscription.current_period_end:
            period_start = subscription.current_period_start
            period_end = subscription.current_period_end
        else:
            # No confirmed billing period yet (e.g. checkout just started and
            # the webhook hasn't landed) - a 30-day rolling window from now
            # keeps the account usable rather than blocking on webhook timing.
            latest = session.execute(
                select(UsagePeriod)
                .where(UsagePeriod.user_id == user.id)
                .order_by(UsagePeriod.period_start.desc())
            ).scalars().first()
            if latest and latest.period_end > now:
                return latest
            period_start = now
            period_end = now + timedelta(days=30)

        existing = session.execute(
            select(UsagePeriod).where(
                UsagePeriod.user_id == user.id, UsagePeriod.period_start == period_start
            )
        ).scalars().first()
        if existing:
            return existing

        period = UsagePeriod(
            user_id=user.id,
            period_start=period_start,
            period_end=period_end,
            credits_included=policy.monthly_credits or 0,
            credits_used=0,
            daily_free_downloads_used=0,
            last_free_reset=now if plan == Plan.FREE else None,
        )
        session.add(period)
        try:
            session.flush()
        except IntegrityError:
            # Lost a race with a concurrent request creating the same period.
            session.rollback()
            existing = session.execute(
                select(UsagePeriod).where(
                    UsagePeriod.user_id == user.id, UsagePeriod.period_start == period_start
                )
            ).scalars().first()
            if existing is None:
                raise
            return existing
        return period

    def reserve(
        self,
        session: Session,
        user: User,
        plan: Plan,
        subscription: Subscription | None,
        credits: int,
        download_job_id: str,
    ) -> str:
        """Atomically reserve `credits` (or one daily free download) from the
        user's current period. Returns a reservation id. Raises
        DailyLimitReachedError / InsufficientCreditsError if there isn't
        enough budget left."""
        period = self.get_or_create_current_period(session, user, plan, subscription)
        policy = get_policy(plan)

        if plan == Plan.FREE:
            limit = policy.daily_free_downloads or 0
            result = session.execute(
                update(UsagePeriod)
                .where(UsagePeriod.id == period.id, UsagePeriod.daily_free_downloads_used < limit)
                .values(daily_free_downloads_used=UsagePeriod.daily_free_downloads_used + 1)
            )
            if result.rowcount == 0:
                raise DailyLimitReachedError(
                    f"You've used all {limit} free downloads for today. "
                    "Upgrade to Pro for more downloads and higher quality."
                )
        else:
            result = session.execute(
                update(UsagePeriod)
                .where(
                    UsagePeriod.id == period.id,
                    (UsagePeriod.credits_included - UsagePeriod.credits_used) >= credits,
                )
                .values(credits_used=UsagePeriod.credits_used + credits)
            )
            if result.rowcount == 0:
                session.refresh(period)
                remaining = max(0, period.credits_included - period.credits_used)
                raise InsufficientCreditsError(
                    f"This download needs {credits} credit(s) but you only have "
                    f"{remaining} left this period."
                )

        event = UsageEvent(
            user_id=user.id,
            type=UsageEventType.RESERVE.value,
            credits=credits,
            download_job_id=download_job_id,
            event_metadata={"status": ReservationStatus.RESERVED.value, "period_id": period.id, "plan": plan.value},
        )
        session.add(event)
        session.flush()
        return event.id

    def commit(self, session: Session, reservation_id: str) -> None:
        """Finalize a reservation after a successful download. Credits were
        already deducted at reserve time, so this just marks the event
        committed for the audit trail - it never charges twice."""
        event = session.get(UsageEvent, reservation_id)
        if event is None or event.event_metadata.get("status") != ReservationStatus.RESERVED.value:
            return
        event.event_metadata = {**event.event_metadata, "status": ReservationStatus.COMMITTED.value}
        flag_modified(event, "event_metadata")
        session.add(
            UsageEvent(
                user_id=event.user_id,
                type=UsageEventType.COMMIT.value,
                credits=event.credits,
                download_job_id=event.download_job_id,
                event_metadata={"reservation_id": event.id},
            )
        )

    def refund(self, session: Session, reservation_id: str) -> None:
        """Give back a reservation's credits/daily-download slot after a
        failed or cancelled download. Idempotent: refunding an
        already-committed or already-refunded reservation is a no-op."""
        event = session.get(UsageEvent, reservation_id)
        if event is None or event.event_metadata.get("status") != ReservationStatus.RESERVED.value:
            return

        period_id = event.event_metadata.get("period_id")
        plan = event.event_metadata.get("plan")
        if period_id:
            if plan == Plan.FREE.value:
                session.execute(
                    update(UsagePeriod)
                    .where(UsagePeriod.id == period_id)
                    .values(
                        daily_free_downloads_used=case(
                            (UsagePeriod.daily_free_downloads_used > 0, UsagePeriod.daily_free_downloads_used - 1),
                            else_=0,
                        )
                    )
                )
            else:
                session.execute(
                    update(UsagePeriod)
                    .where(UsagePeriod.id == period_id)
                    .values(
                        credits_used=case(
                            (UsagePeriod.credits_used > event.credits, UsagePeriod.credits_used - event.credits),
                            else_=0,
                        )
                    )
                )

        event.event_metadata = {**event.event_metadata, "status": ReservationStatus.REFUNDED.value}
        flag_modified(event, "event_metadata")
        session.add(
            UsageEvent(
                user_id=event.user_id,
                type=UsageEventType.REFUND.value,
                credits=event.credits,
                download_job_id=event.download_job_id,
                event_metadata={"reservation_id": event.id},
            )
        )

    def admin_grant(self, session: Session, user: User, plan: Plan, subscription: Subscription | None, credits: int, reason: str) -> None:
        period = self.get_or_create_current_period(session, user, plan, subscription)
        session.execute(
            update(UsagePeriod).where(UsagePeriod.id == period.id).values(
                credits_included=UsagePeriod.credits_included + credits
            )
        )
        session.add(
            UsageEvent(
                user_id=user.id,
                type=UsageEventType.ADMIN_GRANT.value,
                credits=credits,
                download_job_id=None,
                event_metadata={"reason": reason, "period_id": period.id},
            )
        )

    def get_usage_out(self, session: Session, user: User, plan: Plan, subscription: Subscription | None) -> UsageOut:
        period = self.get_or_create_current_period(session, user, plan, subscription)
        policy = get_policy(plan)
        if plan == Plan.FREE:
            limit = policy.daily_free_downloads or 0
            return UsageOut(
                plan=plan,
                period_start=period.period_start,
                period_end=period.period_end,
                credits_included=None,
                credits_used=0,
                credits_remaining=None,
                daily_free_downloads_used=period.daily_free_downloads_used,
                daily_free_downloads_remaining=max(0, limit - period.daily_free_downloads_used),
            )
        return UsageOut(
            plan=plan,
            period_start=period.period_start,
            period_end=period.period_end,
            credits_included=period.credits_included,
            credits_used=period.credits_used,
            credits_remaining=max(0, period.credits_included - period.credits_used),
            daily_free_downloads_used=None,
            daily_free_downloads_remaining=None,
        )


usage_service = UsageService()
