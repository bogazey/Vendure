"""UsageService: reserve/commit/refund lifecycle, including the atomic-UPDATE
race protection under real concurrent access (not just sequential calls)."""
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.database.commercial_db import get_session_factory
from app.database.commercial_models import User
from app.models.commercial_enums import Plan, ReservationStatus
from app.services.auth_service import auth_service
from app.services.usage_service import usage_service
from app.utils.exceptions import DailyLimitReachedError, InsufficientCreditsError


def _make_user(db_session, role="user") -> User:
    result = auth_service.signup(db_session, f"user-{uuid.uuid4().hex[:12]}@example.com", "correcthorse9!")
    db_session.flush()
    return result.user


class TestFreeePlanDailyLimit:
    def test_reserve_consumes_one_daily_slot(self, db_session):
        user = _make_user(db_session)
        reservation_id = usage_service.reserve(db_session, user, Plan.FREE, None, 1, "job-1")
        db_session.flush()
        usage = usage_service.get_usage_out(db_session, user, Plan.FREE, None)
        assert usage.daily_free_downloads_used == 1
        assert usage.daily_free_downloads_remaining == 4
        assert reservation_id

    def test_reserve_past_daily_limit_raises(self, db_session):
        user = _make_user(db_session)
        for i in range(5):
            usage_service.reserve(db_session, user, Plan.FREE, None, 1, f"job-{i}")
            db_session.flush()
        with pytest.raises(DailyLimitReachedError):
            usage_service.reserve(db_session, user, Plan.FREE, None, 1, "job-overflow")

    def test_refund_gives_back_a_daily_slot(self, db_session):
        user = _make_user(db_session)
        reservation_id = usage_service.reserve(db_session, user, Plan.FREE, None, 1, "job-1")
        db_session.flush()
        usage_service.refund(db_session, reservation_id)
        db_session.flush()
        usage = usage_service.get_usage_out(db_session, user, Plan.FREE, None)
        assert usage.daily_free_downloads_used == 0

    def test_commit_does_not_change_balance_and_is_not_refundable_after(self, db_session):
        user = _make_user(db_session)
        reservation_id = usage_service.reserve(db_session, user, Plan.FREE, None, 1, "job-1")
        db_session.flush()
        usage_service.commit(db_session, reservation_id)
        db_session.flush()
        usage = usage_service.get_usage_out(db_session, user, Plan.FREE, None)
        assert usage.daily_free_downloads_used == 1  # committed, not refunded

        # Refunding an already-committed reservation must be a no-op (never
        # double-credit a user who cancels after their download completed).
        usage_service.refund(db_session, reservation_id)
        db_session.flush()
        usage = usage_service.get_usage_out(db_session, user, Plan.FREE, None)
        assert usage.daily_free_downloads_used == 1


class TestPaidPlanCredits:
    def test_reserve_deducts_credits(self, db_session):
        user = _make_user(db_session)
        usage_service.reserve(db_session, user, Plan.PRO, None, 3, "job-1")
        db_session.flush()
        usage = usage_service.get_usage_out(db_session, user, Plan.PRO, None)
        assert usage.credits_used == 3
        assert usage.credits_remaining == 147  # 150 included - 3

    def test_reserve_more_than_remaining_raises(self, db_session):
        user = _make_user(db_session)
        usage_service.reserve(db_session, user, Plan.PRO, None, 150, "job-1")
        db_session.flush()
        with pytest.raises(InsufficientCreditsError):
            usage_service.reserve(db_session, user, Plan.PRO, None, 1, "job-2")

    def test_refund_gives_back_exact_credits(self, db_session):
        user = _make_user(db_session)
        reservation_id = usage_service.reserve(db_session, user, Plan.PRO, None, 3, "job-1")
        db_session.flush()
        usage_service.refund(db_session, reservation_id)
        db_session.flush()
        usage = usage_service.get_usage_out(db_session, user, Plan.PRO, None)
        assert usage.credits_used == 0

    def test_admin_grant_increases_included_credits(self, db_session):
        user = _make_user(db_session)
        usage_service.admin_grant(db_session, user, Plan.PRO, None, 50, "support case")
        db_session.flush()
        usage = usage_service.get_usage_out(db_session, user, Plan.PRO, None)
        assert usage.credits_included == 200  # 150 base + 50 granted


class TestConcurrentReservationNeverGoesNegative:
    def test_race_for_limited_credits_never_overspends(self, db_session):
        """20 threads race to reserve 1 credit each from a pool of 10. The
        atomic UPDATE...WHERE reservation pattern must let exactly 10 succeed
        - never more (which would put the balance negative) and never fewer
        (which would mean lost throughput)."""
        user = _make_user(db_session)
        usage_service.admin_grant(db_session, user, Plan.PRO, None, -140, "shrink pool for test")
        db_session.commit()  # must be visible to the other threads' own sessions

        user_id = user.id
        successes = []
        failures = []

        def attempt(i: int) -> None:
            session = get_session_factory()()
            try:
                thread_user = session.get(User, user_id)
                usage_service.reserve(session, thread_user, Plan.PRO, None, 1, f"job-{i}")
                session.commit()
                successes.append(i)
            except InsufficientCreditsError:
                session.rollback()
                failures.append(i)
            finally:
                session.close()

        with ThreadPoolExecutor(max_workers=20) as pool:
            list(pool.map(attempt, range(20)))

        assert len(successes) == 10
        assert len(failures) == 10

        usage = usage_service.get_usage_out(db_session, user, Plan.PRO, None)
        assert usage.credits_used == 10
        assert usage.credits_remaining == 0
