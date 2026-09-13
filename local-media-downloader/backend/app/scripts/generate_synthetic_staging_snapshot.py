"""Mission 5, phase 4: deterministic synthetic "pre-migration Loady" dataset
for the local production-migration rehearsal.

Usage (run inside the loady-staging-backend container, so it writes through
the same DATABASE_URL/history-db paths the running staging app uses):

    python -m app.scripts.generate_synthetic_staging_snapshot [--reset]
    python -m app.scripts.generate_synthetic_staging_snapshot --manifest-out /path/to/manifest.json

Safety properties (mirrors app/scripts/promote_admin.py's operator-only
posture, and loady_migration_dry_run.py's environment guard):

- Refuses to run at all if DATABASE_URL (or, when set, LMD_DB_PATH for the
  history sqlite file) contains "production" or "prod." - this tool only
  ever writes to a staging/local/test database.
- Every synthetic row is tagged: emails end in
  `@synthetic.rehearsal.invalid` (a reserved, non-resolvable TLD per
  RFC 2606's spirit - never a real domain), and every row this script
  creates is only ever selected back BY that email suffix - so `--reset`
  can delete exactly what this script created and nothing a real user
  might have added to the same staging database.
- Deterministic: a fixed seed (`--seed`, default 20260913) means the exact
  same 51 users, in the exact same order, with the exact same plan/status/
  history/usage shape, are produced every time this is run against a
  freshly-reset database - required so the rehearsal is repeatable (mission
  brief, phase 4).
- NO REAL USER DATA of any kind - names, history titles/URLs, and Paddle-
  like identifiers are all synthesized from the fixed seed.

Emits a machine-readable pre-migration manifest (`--manifest-out`) recording
exactly the invariants phase 9's reconciliation report re-checks after
migration: user counts, plan distribution, admin/verified/disabled counts,
history/usage totals - plus a SHA-256 checksum of the manifest's own content
so a later diff can prove the file wasn't silently edited.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import delete, select

from app.config.commercial_settings import get_commercial_settings
from app.config.paths import DB_PATH
from app.database import history_repo
from app.database.commercial_db import get_session_factory
from app.database.commercial_models import (
    RefreshToken,
    Subscription,
    UsageEvent,
    UsagePeriod,
    User,
)
from app.models.commercial_enums import (
    Plan,
    SubscriptionProvider,
    SubscriptionStatus,
    UsageEventType,
    UserRole,
    UserStatus,
)

SYNTHETIC_EMAIL_SUFFIX = "@synthetic.rehearsal.invalid"
DEFAULT_SEED = 20260913
_EPOCH = datetime(2026, 9, 13, tzinfo=timezone.utc)


def _refuse_if_production(settings) -> None:
    for label, value in (("DATABASE_URL", settings.database_url), ("LMD_DB_PATH", str(DB_PATH))):
        if "production" in value.lower() or "prod." in value.lower():
            print(f"Refusing to run: {label} looks like a production target ({value!r}).")
            raise SystemExit(1)


@dataclass
class Persona:
    label: str
    count: int
    plan: Plan
    provider: str | None  # None => no Subscription row at all (pure Free)
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE
    user_status: UserStatus = UserStatus.ACTIVE
    verified: bool = True
    role: UserRole = UserRole.USER
    already_linked: bool = False  # duplicate/collision edge case
    malformed_plan: str | None = None  # malformed/invalid migration edge case
    with_history: bool = False
    with_usage: bool = False
    with_remember_me: bool = False


PERSONAS: list[Persona] = [
    Persona("free_verified", 20, Plan.FREE, None, with_history=True, with_usage=True, with_remember_me=True),
    Persona("free_unverified", 5, Plan.FREE, None, verified=False),
    Persona("pro_paddle", 8, Plan.PRO, SubscriptionProvider.PADDLE.value, with_history=True, with_usage=True),
    Persona("creator_paddle", 5, Plan.CREATOR, SubscriptionProvider.PADDLE.value, with_history=True, with_usage=True),
    Persona("gifted_pro", 3, Plan.PRO, SubscriptionProvider.GIFTED.value, with_usage=True),
    Persona("gifted_creator", 2, Plan.CREATOR, SubscriptionProvider.GIFTED.value, with_usage=True),
    Persona("disabled_free", 2, Plan.FREE, None, user_status=UserStatus.DISABLED),
    Persona("disabled_pro", 1, Plan.PRO, SubscriptionProvider.PADDLE.value, user_status=UserStatus.DISABLED),
    Persona("admin_pro", 2, Plan.PRO, SubscriptionProvider.PADDLE.value, role=UserRole.ADMIN, with_history=True),
    Persona("unverified_disabled_edge", 1, Plan.FREE, None, verified=False, user_status=UserStatus.DISABLED),
    Persona("already_linked_edge", 1, Plan.PRO, SubscriptionProvider.PADDLE.value, already_linked=True),
    Persona("malformed_plan_edge", 1, Plan.FREE, SubscriptionProvider.PADDLE.value, malformed_plan="legacy_gold_tier"),
]

_PLATFORMS = ["youtube", "tiktok", "instagram", "facebook"]


def _emit(rng: random.Random, session, seq: int, persona: Persona) -> dict:
    created_at = _EPOCH - timedelta(days=rng.randint(1, 400), hours=rng.randint(0, 23))
    email = f"{persona.label}-{seq:03d}{SYNTHETIC_EMAIL_SUFFIX}"

    user = User(
        email=email,
        # Fixed, non-secret synthetic Argon2id-shaped placeholder - login
        # rehearsal (phase 10) sets a real known password separately via
        # security_service where it needs one to actually authenticate;
        # this generator's job is data shape, not credential rehearsal.
        password_hash="$argon2id$synthetic$placeholder$never-a-real-hash",
        email_verified=persona.verified,
        status=persona.user_status.value,
        role=persona.role.value,
        created_at=created_at,
        updated_at=created_at,
    )
    if persona.already_linked:
        user.global_user_id = f"usr_synthetic{seq:08x}0000000000000000"
    session.add(user)
    session.flush()

    if persona.provider is not None:
        plan_value = persona.malformed_plan or persona.plan.value
        period_start = created_at
        period_end = created_at + timedelta(days=30)
        sub = Subscription(
            user_id=user.id,
            provider=persona.provider,
            provider_customer_id=(f"ctm_synthetic_{seq:06d}" if persona.provider == SubscriptionProvider.PADDLE.value else None),
            provider_subscription_id=(f"sub_synthetic_{seq:06d}" if persona.provider == SubscriptionProvider.PADDLE.value else None),
            plan=plan_value,
            status=persona.status.value,
            current_period_start=period_start,
            current_period_end=period_end,
            granted_by_admin_id=None,
            granted_reason=("Synthetic rehearsal gift - phase 4 fixture" if persona.provider == SubscriptionProvider.GIFTED.value else None),
            created_at=created_at,
            updated_at=created_at,
        )
        session.add(sub)

    if persona.with_usage:
        policy_credits = {Plan.FREE: 0, Plan.PRO: 150, Plan.CREATOR: 500}[persona.plan]
        period = UsagePeriod(
            user_id=user.id,
            period_start=created_at,
            period_end=created_at + timedelta(days=30),
            credits_included=policy_credits,
            credits_used=min(policy_credits, rng.randint(0, max(policy_credits, 1))),
            daily_free_downloads_used=rng.randint(0, 5) if persona.plan == Plan.FREE else 0,
        )
        session.add(period)
        session.flush()
        for _ in range(rng.randint(1, 3)):
            session.add(UsageEvent(
                user_id=user.id, type=UsageEventType.COMMIT.value, credits=1,
                download_job_id=f"synthetic-job-{seq}-{rng.randint(1000, 9999)}",
                event_metadata={"synthetic": True}, created_at=created_at,
            ))

    if persona.with_remember_me and rng.random() < 0.4:
        session.add(RefreshToken(
            user_id=user.id,
            token_hash=hashlib.sha256(f"synthetic-refresh-{user.id}".encode()).hexdigest(),
            created_at=created_at,
            expires_at=created_at + timedelta(days=30),
            remember_me=True,
        ))

    history_rows_written = 0
    if persona.with_history:
        for h in range(rng.randint(1, 4)):
            platform = rng.choice(_PLATFORMS)
            history_repo.upsert({
                "id": f"synthetic-hist-{seq:03d}-{h}",
                "url": f"https://{platform}.example.invalid/synthetic/{seq}/{h}",
                "platform": platform,
                "title": f"Synthetic fixture video {seq}-{h}",
                "uploader": "synthetic-uploader",
                "thumbnail": None,
                "format_label": "mp4",
                "resolution": "1080p",
                "filepath": None,
                "filesize": rng.randint(1_000_000, 500_000_000),
                "created_at": (created_at + timedelta(hours=h)).isoformat(),
                "completed_at": (created_at + timedelta(hours=h, minutes=5)).isoformat(),
                "status": "completed",
                "error_message": None,
                "user_id": user.id,
            })
            history_rows_written += 1

    return {
        "email": email, "user_id": user.id, "persona": persona.label,
        "plan": persona.plan.value, "status": persona.user_status.value,
        "verified": persona.verified, "role": persona.role.value,
        "already_linked": persona.already_linked, "history_rows": history_rows_written,
    }


def reset(session) -> int:
    """Deletes every previously-generated synthetic row (matched strictly by
    the reserved email suffix) - never touches any other row."""
    ids = session.execute(
        select(User.id).where(User.email.like(f"%{SYNTHETIC_EMAIL_SUFFIX}"))
    ).scalars().all()
    if not ids:
        return 0
    for uid in ids:
        history_repo.clear_all(user_id=uid)
    session.execute(delete(RefreshToken).where(RefreshToken.user_id.in_(ids)))
    session.execute(delete(UsageEvent).where(UsageEvent.user_id.in_(ids)))
    session.execute(delete(UsagePeriod).where(UsagePeriod.user_id.in_(ids)))
    session.execute(delete(Subscription).where(Subscription.user_id.in_(ids)))
    session.execute(delete(User).where(User.id.in_(ids)))
    session.commit()
    return len(ids)


def generate(seed: int = DEFAULT_SEED, session=None) -> list[dict]:
    """Writes the full synthetic persona set through `session` when given
    (e.g. a test's own `db_session`, so it shares one connection rather than
    racing a second pooled SQLite connection for the same file) - otherwise
    opens and owns a fresh one, exactly as every other operator script in
    this directory does when run standalone from the CLI."""
    settings = get_commercial_settings()
    _refuse_if_production(settings)
    rng = random.Random(seed)
    owns_session = session is None
    session = session or get_session_factory()()
    records: list[dict] = []
    try:
        seq = 1
        for persona in PERSONAS:
            for _ in range(persona.count):
                records.append(_emit(rng, session, seq, persona))
                seq += 1
        session.commit()
    finally:
        if owns_session:
            session.close()
    return records


def build_manifest(records: list[dict]) -> dict:
    total = len(records)
    by_plan: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for r in records:
        by_plan[r["plan"]] = by_plan.get(r["plan"], 0) + 1
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_users": total,
        "plan_distribution": by_plan,
        "status_distribution": by_status,
        "verified_count": sum(1 for r in records if r["verified"]),
        "unverified_count": sum(1 for r in records if not r["verified"]),
        "admin_count": sum(1 for r in records if r["role"] == "admin"),
        "already_linked_count": sum(1 for r in records if r["already_linked"]),
        "history_row_count": sum(r["history_rows"] for r in records),
        "users": records,
    }
    payload = json.dumps(manifest, sort_keys=True).encode("utf-8")
    manifest["checksum_sha256"] = hashlib.sha256(payload).hexdigest()
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--reset", action="store_true", help="Delete previously-generated synthetic rows first.")
    parser.add_argument("--manifest-out", type=Path, default=None, help="Write the pre-migration manifest JSON here.")
    args = parser.parse_args(argv)

    settings = get_commercial_settings()
    _refuse_if_production(settings)

    if args.reset:
        session = get_session_factory()()
        try:
            deleted = reset(session)
        finally:
            session.close()
        print(f"Removed {deleted} previously-generated synthetic user(s).")

    records = generate(seed=args.seed)
    print(f"Generated {len(records)} synthetic users across {len(PERSONAS)} personas.")

    manifest = build_manifest(records)
    if args.manifest_out:
        args.manifest_out.write_text(json.dumps(manifest, indent=2, sort_keys=True))
        print(f"Wrote pre-migration manifest to {args.manifest_out} (sha256={manifest['checksum_sha256'][:16]}...).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
