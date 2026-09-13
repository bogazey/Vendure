"""Loady -> Platform Core migration dry-run / real-run CLI.

**Never point this at a production database.** `--loady-database-url`
must be a LOCAL COPY or test database - this script has no special
handling for "production," it will happily migrate whatever database URL
you give it, which is exactly why the operator, not the script, is
responsible for never pointing it at one.

Usage:
    python -m app.scripts.loady_migration_dry_run \
        --loady-database-url sqlite:////path/to/a/local/copy/of/commercial.db \
        [--commit] [--reason "initial migration dry run"]

Without `--commit`, this is a true dry run: every read and write happens
exactly as a real run would (through `session.flush()`/the Loady
connection's transaction), but everything is rolled back at the very end
- the printed report reflects exactly what WOULD have been written.
With `--commit`, the same run is committed for real.

Exit code 0 on success (even with some `conflicted`/`failed` rows -
those are reported, not fatal); exit code 1 if the tool itself errors out
before producing a report.
"""
from __future__ import annotations

import argparse
import sys

import secrets

from sqlalchemy import create_engine, select

from app.database.db import get_session_factory
from app.database.models import User
from app.database.seed_roles import ensure_roles
from app.models.enums import GLOBAL_SCOPE, RoleSlug
from app.security.passwords import hash_password
from app.services import rbac_service
from app.services.loady_migration_service import run_migration


def _get_or_create_migration_actor(session) -> User:
    existing = session.execute(
        select(User).where(User.email == "loady-migration@platform-core.local")
    ).scalars().first()
    if existing is not None:
        return existing

    user = User(
        email="loady-migration@platform-core.local",
        password_hash=hash_password(secrets.token_urlsafe(32)),
        email_verified=True,
    )
    session.add(user)
    session.flush()
    ensure_roles(session)
    rbac_service.assign_role(session, user, RoleSlug.SUPER_ADMIN, GLOBAL_SCOPE, granted_by=None)
    return user


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--loady-database-url", required=True, help="A LOCAL COPY of Loady's commercial database URL - never production.")
    parser.add_argument("--commit", action="store_true", help="Actually persist the migration. Omit for a true dry run.")
    parser.add_argument("--reason", default="Loady migration dry run", help="Reason recorded on every audit log entry this run writes.")
    args = parser.parse_args()

    if "production" in args.loady_database_url.lower():
        print("Refusing to run: --loady-database-url contains the word 'production'.", file=sys.stderr)
        return 1

    loady_engine = create_engine(args.loady_database_url)
    platform_session = get_session_factory()()

    try:
        # The migration actor is a persistent system account, committed on
        # its own regardless of --commit - a dry run must not roll away
        # the very account future runs (dry or real) attribute audit
        # entries to.
        actor = _get_or_create_migration_actor(platform_session)
        platform_session.commit()

        report = run_migration(platform_session, loady_engine, actor=actor, reason=args.reason, dry_run=not args.commit)
        print("=== COMMITTED ===" if args.commit else "=== DRY RUN (nothing was written - pass --commit to persist) ===")

        summary = report.summary()
        print(f"created={summary['created']} linked={summary['linked']} skipped={summary['skipped']} "
              f"conflicted={summary['conflicted']} failed={summary['failed']}")
        for label, rows in (
            ("CREATED", report.created), ("LINKED", report.linked), ("SKIPPED", report.skipped),
            ("CONFLICTED", report.conflicted), ("FAILED", report.failed),
        ):
            if not rows:
                continue
            print(f"\n-- {label} --")
            for row in rows:
                print(f"  {row}")
        return 0
    finally:
        platform_session.close()


if __name__ == "__main__":
    raise SystemExit(main())
