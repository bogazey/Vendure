"""The 12 synthetic Loady fixtures the mission requires, run through the
real migration service against a temporary SQLite database whose schema
matches docs/platform/LOADY_MIGRATION_AUDIT.md exactly (no production
data, no real credentials - every password/email here is synthetic)."""
from __future__ import annotations

import tempfile
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select, text

from app.database.models import Entitlement, ProductMembership, RoleAssignment, User
from app.security.passwords import hash_password
from app.services.loady_migration_service import run_migration

_NOW = datetime.now(timezone.utc)
_PAST = (_NOW - timedelta(days=5)).isoformat()
_FUTURE = (_NOW + timedelta(days=25)).isoformat()


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def loady_engine():
    """A throwaway SQLite file mirroring Loady's real `users`/
    `subscriptions` schema (see LOADY_MIGRATION_AUDIT.md §1/§13) -
    intentionally hand-built with raw SQL rather than importing Loady's
    ORM, exactly like the real migration script will face a Loady
    database it never imports Python classes from."""
    path = tempfile.mktemp(suffix=".db")
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE users (
                id VARCHAR(36) PRIMARY KEY,
                email VARCHAR(320) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                email_verified BOOLEAN NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'active',
                role VARCHAR(20) NOT NULL DEFAULT 'user',
                global_user_id VARCHAR(48)
            )
        """))
        conn.execute(text("""
            CREATE TABLE subscriptions (
                id VARCHAR(36) PRIMARY KEY,
                user_id VARCHAR(36) NOT NULL,
                provider VARCHAR(30) NOT NULL DEFAULT 'paddle',
                provider_customer_id VARCHAR(120),
                provider_subscription_id VARCHAR(120),
                plan VARCHAR(20) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'none',
                current_period_start TEXT,
                current_period_end TEXT,
                cancel_at_period_end BOOLEAN NOT NULL DEFAULT 0,
                granted_by_admin_id VARCHAR(36),
                granted_reason VARCHAR(500),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """))
    yield engine
    engine.dispose()


def _insert_user(engine, *, email, password="synthetic-test-password-1", email_verified=True,
                  status="active", role="user", global_user_id=None, created_at=None) -> str:
    user_id = _uid()
    with engine.begin() as conn:
        conn.execute(
            text("""INSERT INTO users (id, email, password_hash, email_verified, created_at, updated_at, status, role, global_user_id)
                    VALUES (:id, :email, :ph, :ev, :ca, :ca, :status, :role, :gid)"""),
            {"id": user_id, "email": email, "ph": hash_password(password), "ev": email_verified,
             "ca": (created_at or _NOW).isoformat(), "status": status, "role": role, "gid": global_user_id},
        )
    return user_id


def _insert_subscription(engine, *, user_id, provider, plan, status="active",
                          current_period_end=None, granted_by_admin_id=None, granted_reason=None):
    with engine.begin() as conn:
        conn.execute(
            text("""INSERT INTO subscriptions
                    (id, user_id, provider, plan, status, current_period_end, granted_by_admin_id, granted_reason, created_at, updated_at)
                    VALUES (:id, :uid, :provider, :plan, :status, :cpe, :granted_by, :reason, :now, :now)"""),
            {"id": _uid(), "uid": user_id, "provider": provider, "plan": plan, "status": status,
             "cpe": current_period_end, "granted_by": granted_by_admin_id, "reason": granted_reason, "now": _NOW.isoformat()},
        )


@pytest.fixture()
def migration_actor(db_session) -> User:
    # A unique email per test - run_migration commits platform_session
    # when dry_run=False, so a fixed email here would collide across
    # tests sharing the session-scoped test database.
    actor = User(email=f"migration-actor-{_uid()}@example.com", password_hash="x", email_verified=True)
    db_session.add(actor)
    db_session.flush()
    return actor


def _build_all_fixtures(loady_engine) -> dict[str, str]:
    """Returns {label: loady_user_id} for the 12 required fixtures."""
    ids: dict[str, str] = {}

    # 1. Free Loady user (no subscription row at all)
    ids["free"] = _insert_user(loady_engine, email="free-user@example.com")

    # 2. Paid Pro user
    ids["paid_pro"] = _insert_user(loady_engine, email="paid-pro@example.com")
    _insert_subscription(loady_engine, user_id=ids["paid_pro"], provider="paddle", plan="pro",
                          current_period_end=_FUTURE)

    # 3. Paid Creator user
    ids["paid_creator"] = _insert_user(loady_engine, email="paid-creator@example.com")
    _insert_subscription(loady_engine, user_id=ids["paid_creator"], provider="paddle", plan="creator",
                          current_period_end=_FUTURE)

    # 6. Loady admin user (created early so it exists for gifted-grant attribution below)
    ids["admin"] = _insert_user(loady_engine, email="loady-admin@example.com", role="admin")

    # 4. Gifted Pro user (granted by the admin above)
    ids["gifted_pro"] = _insert_user(loady_engine, email="gifted-pro@example.com")
    _insert_subscription(loady_engine, user_id=ids["gifted_pro"], provider="gifted", plan="pro",
                          granted_by_admin_id=ids["admin"], granted_reason="beta tester")

    # 5. Gifted Creator user
    ids["gifted_creator"] = _insert_user(loady_engine, email="gifted-creator@example.com")
    _insert_subscription(loady_engine, user_id=ids["gifted_creator"], provider="gifted", plan="creator",
                          granted_by_admin_id=ids["admin"], granted_reason="partner account",
                          current_period_end=_FUTURE)

    # 7. Email-unverified user
    ids["unverified"] = _insert_user(loady_engine, email="unverified@example.com", email_verified=False)

    # 8. Disabled user
    ids["disabled"] = _insert_user(loady_engine, email="disabled-user@example.com", status="disabled")

    # 9/10. Users with download history - history lives in Loady's SEPARATE
    # sqlite3 `app.db`, not in this commercial-schema test DB at all (see
    # LOADY_MIGRATION_AUDIT.md §18) - the migration never touches it, so no
    # rows are needed here to prove that; the identity row alone suffices.
    ids["with_history"] = _insert_user(loady_engine, email="has-history@example.com")
    ids["with_many_history"] = _insert_user(loady_engine, email="has-lots-of-history@example.com")

    # 11. User with an existing (expired) Paddle reference - a lapsed
    # subscription, no longer "active" by status, so entitlement is free,
    # but the Paddle ids remain in Loady's own DB regardless (never copied).
    ids["lapsed_paddle"] = _insert_user(loady_engine, email="lapsed-paddle@example.com")
    _insert_subscription(loady_engine, user_id=ids["lapsed_paddle"], provider="paddle", plan="pro",
                          status="canceled", current_period_end=_PAST)

    # 12. Collision/invalid migration case - a Loady row that already
    # claims a global_user_id, but nothing on Platform Core has that id
    # (an orphaned/invalid reference - e.g. from a botched prior run).
    ids["orphaned_link"] = _insert_user(
        loady_engine, email="orphaned@example.com", global_user_id="usr_does_not_exist_on_platform_core"
    )

    return ids


def test_all_twelve_fixtures_migrate_with_correct_classification(db_session, loady_engine, migration_actor):
    ids = _build_all_fixtures(loady_engine)

    report = run_migration(db_session, loady_engine, actor=migration_actor, reason="fixture test", dry_run=False)
    db_session.flush()

    summary = report.summary()
    assert summary["created"] == 11  # every fixture except the pre-linked orphan
    assert summary["conflicted"] == 1  # the orphaned_link fixture
    assert summary["failed"] == 0

    by_loady_id = {row["loady_user_id"]: row for row in report.created}

    assert by_loady_id[ids["free"]]["entitlement_source"] == "free"
    assert by_loady_id[ids["free"]]["plan"] == "free"

    assert by_loady_id[ids["paid_pro"]]["entitlement_source"] == "paddle"
    assert by_loady_id[ids["paid_pro"]]["plan"] == "pro"

    assert by_loady_id[ids["paid_creator"]]["entitlement_source"] == "paddle"
    assert by_loady_id[ids["paid_creator"]]["plan"] == "creator"

    assert by_loady_id[ids["gifted_pro"]]["entitlement_source"] == "gifted"
    assert by_loady_id[ids["gifted_creator"]]["entitlement_source"] == "gifted"

    assert by_loady_id[ids["lapsed_paddle"]]["entitlement_source"] == "free", "a canceled/expired subscription must not count as active"

    conflicted_ids = {row["loady_user_id"] for row in report.conflicted}
    assert conflicted_ids == {ids["orphaned_link"]}

    # Admin mapping: product-scoped, never global (mission-brief section 46).
    admin_global_id = by_loady_id[ids["admin"]]["global_user_id"]
    roles = db_session.query(RoleAssignment).filter_by(user_id=admin_global_id).all()
    assert any(r.role_slug == "admin" and r.scope == "product:loady" for r in roles)
    assert not any(r.scope == "global" for r in roles), "Loady admin must never become a Grand Admin"

    # Gifted grant attribution: the gifted entitlements should show the
    # migrated admin (not the migration script's own actor) as the granter.
    gifted_pro_global_id = by_loady_id[ids["gifted_pro"]]["global_user_id"]
    entitlement = (
        db_session.query(Entitlement)
        .filter_by(user_id=gifted_pro_global_id, product_id="loady")
        .first()
    )
    assert entitlement.granted_by == admin_global_id
    assert entitlement.reason == "beta tester"

    # Disabled user: status carried over faithfully, not silently activated.
    disabled_global_id = by_loady_id[ids["disabled"]]["global_user_id"]
    platform_disabled_user = db_session.get(User, disabled_global_id)
    assert platform_disabled_user.status == "disabled"

    # Unverified user: email_verified carried over faithfully.
    unverified_global_id = by_loady_id[ids["unverified"]]["global_user_id"]
    assert db_session.get(User, unverified_global_id).email_verified is False

    # Product membership recorded for every successfully migrated user.
    memberships = db_session.query(ProductMembership).filter_by(product_id="loady").count()
    assert memberships == 11


def test_migration_never_creates_a_payment_record_for_gifted_users(db_session, loady_engine, migration_actor):
    from app.database.models import PaymentRecord

    admin_id = _insert_user(loady_engine, email="admin2@example.com", role="admin")
    gifted_id = _insert_user(loady_engine, email="gifted-only@example.com")
    _insert_subscription(loady_engine, user_id=gifted_id, provider="gifted", plan="creator",
                          granted_by_admin_id=admin_id, granted_reason="internal test account")

    run_migration(db_session, loady_engine, actor=migration_actor, reason="no-revenue check", dry_run=False)
    db_session.flush()

    # Scoped to the migrated global user id, not a global table count -
    # Mission 6 added real (signature-verified, transaction.completed-
    # driven) PaymentRecord writes elsewhere in this same test database,
    # so "zero PaymentRecord rows anywhere" is no longer a meaningful
    # invariant; "the migration created none for this gifted-only user"
    # still is, and is what this test actually checks.
    migrated_user = db_session.execute(
        select(User).where(User.email == "gifted-only@example.com")
    ).scalars().first()
    assert migrated_user is not None
    assert db_session.query(PaymentRecord).filter(PaymentRecord.user_id == migrated_user.id).count() == 0


def test_running_migration_twice_is_idempotent(db_session, loady_engine, migration_actor):
    _build_all_fixtures(loady_engine)

    report1 = run_migration(db_session, loady_engine, actor=migration_actor, reason="run 1", dry_run=False)
    db_session.commit()
    total_users_after_first = db_session.query(User).count()
    total_entitlements_after_first = db_session.query(Entitlement).count()
    total_memberships_after_first = db_session.query(ProductMembership).count()

    report2 = run_migration(db_session, loady_engine, actor=migration_actor, reason="run 2", dry_run=False)
    db_session.commit()

    summary2 = report2.summary()
    assert summary2["created"] == 0, "a second run must never create duplicate Platform Core users"
    assert summary2["skipped"] == 11, "every already-linked user should be reported as skipped, not re-created"
    assert summary2["conflicted"] == report1.summary()["conflicted"]

    assert db_session.query(User).count() == total_users_after_first
    assert db_session.query(Entitlement).count() == total_entitlements_after_first, "no duplicate entitlement rows"
    assert db_session.query(ProductMembership).count() == total_memberships_after_first, "no duplicate memberships"

    # The Loady-side write-back must also be idempotent - every migrated
    # row's global_user_id should be unchanged between runs.
    with loady_engine.connect() as conn:
        rows = conn.execute(text("SELECT id, global_user_id FROM users WHERE email != 'orphaned@example.com'")).all()
        assert all(r[1] is not None for r in rows)


def test_unrecognized_subscription_provider_is_reported_not_guessed(db_session, loady_engine, migration_actor):
    user_id = _insert_user(loady_engine, email="weird-provider@example.com")
    _insert_subscription(loady_engine, user_id=user_id, provider="stripe", plan="pro")

    report = run_migration(db_session, loady_engine, actor=migration_actor, reason="unknown provider check", dry_run=False)
    db_session.flush()

    assert len(report.failed) == 1
    assert "stripe" in report.failed[0]["reason"]
    assert report.summary()["created"] == 0 or report.created[0]["loady_user_id"] != user_id


def test_linking_to_a_pre_existing_platform_core_account_with_same_email(db_session, loady_engine, migration_actor):
    """A user who already has a Platform Core account (e.g. from a demo
    product) with the same email must be LINKED, not duplicated."""
    shared_email = "already-on-platform-core@example.com"
    existing_platform_user = User(email=shared_email, password_hash="existing-hash-unchanged", email_verified=True)
    db_session.add(existing_platform_user)
    db_session.flush()
    existing_id = existing_platform_user.id
    existing_hash = existing_platform_user.password_hash

    loady_id = _insert_user(loady_engine, email=shared_email, password="a-totally-different-loady-password")

    report = run_migration(db_session, loady_engine, actor=migration_actor, reason="link check", dry_run=False)
    db_session.flush()

    assert report.summary()["linked"] == 1
    assert report.linked[0]["global_user_id"] == existing_id

    # The existing Platform Core account's credential must NEVER be
    # overwritten by the Loady side's password hash.
    db_session.refresh(existing_platform_user)
    assert existing_platform_user.password_hash == existing_hash

    with loady_engine.connect() as conn:
        row = conn.execute(text("SELECT global_user_id FROM users WHERE id = :id"), {"id": loady_id}).first()
        assert row[0] == existing_id


def test_safe_error_reason_never_includes_a_password_hash(db_session):
    """Security review finding: `str(exc)` on a SQLAlchemy IntegrityError
    embeds the failing INSERT's bound parameters - for phase 1's user-
    creation statement, that includes the migrated user's real Argon2
    password hash. `_safe_error_reason` must strip that out before it
    ever reaches `report.failed` (printed verbatim by
    loady_migration_dry_run.py)."""
    from sqlalchemy.exc import IntegrityError

    from app.services.loady_migration_service import _safe_error_reason

    secret_hash = "argon2id$v=19$m=65536,t=3,p=4$totally-real-secret-hash-value"
    db_session.add(User(email="dup-reason@example.com", password_hash="first-hash", email_verified=True))
    db_session.flush()
    try:
        db_session.add(User(email="dup-reason@example.com", password_hash=secret_hash, email_verified=True))
        db_session.flush()
        assert False, "expected a UNIQUE constraint violation"
    except IntegrityError as exc:
        reason = _safe_error_reason(exc)
    finally:
        db_session.rollback()

    assert secret_hash not in reason
    assert "IntegrityError" in reason
