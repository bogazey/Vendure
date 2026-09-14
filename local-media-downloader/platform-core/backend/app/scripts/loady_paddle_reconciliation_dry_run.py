"""Loady -> Platform Core Paddle billing reconciliation dry-run / real-run
CLI (Mission 8: Billing Ownership Transition).

**Never point this at a production database, and this never calls Paddle
Live** - the bootstrap events this script generates are signed with
`FakeBillingProvider`'s own fixed local test secret, exactly the same
mechanism the existing billing test suite already uses. A real cutover
would feed genuine historical Paddle webhook payloads through
`PaddleBillingProvider` instead - see docs/platform/
PADDLE_LIVE_INPUTS_REQUIRED.md for exactly what that would require.

Usage:
    python -m app.scripts.loady_paddle_reconciliation_dry_run \\
        --loady-database-url sqlite:////path/to/a/local/copy/of/commercial.db \\
        [--commit] [--additional-events-file events.json] [--reason "..."]

`--additional-events-file` (optional) is a JSON file containing a list of
FakeBillingProvider-shaped event payload dicts (see
`app/services/billing/fake_provider.py`'s `normalize_event`) - simulating
whatever real Paddle events would have arrived during the cutover window,
replayed AFTER every Loady subscription's own bootstrap event so
renewals/cancellations/refunds that happen mid-cutover can be proven to
reconcile correctly.

Exit code 0 on success (even with `orphaned_*`/`duplicate_local_reference`/
`failed` rows - those are reported, not fatal); exit code 1 if the tool
itself errors out before producing a report.
"""
from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import create_engine, select

from app.database.db import get_session_factory
from app.database.models import User
from app.services.billing.fake_provider import FakeBillingProvider
from app.services.loady_paddle_reconciliation_service import run_reconciliation


def _get_or_create_reconciliation_actor(session) -> User:
    from app.security.passwords import hash_password
    import secrets

    existing = session.execute(
        select(User).where(User.email == "loady-billing-reconciliation@platform-core.local")
    ).scalars().first()
    if existing is not None:
        return existing
    user = User(
        email="loady-billing-reconciliation@platform-core.local",
        password_hash=hash_password(secrets.token_urlsafe(32)),
        email_verified=True,
    )
    session.add(user)
    session.flush()
    return user


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--loady-database-url", required=True, help="A LOCAL COPY of Loady's commercial database URL - never production.")
    parser.add_argument("--commit", action="store_true", help="Actually persist the reconciliation. Omit for a true dry run.")
    parser.add_argument("--additional-events-file", default=None, help="Optional JSON file of extra synthetic events to replay after bootstrapping.")
    parser.add_argument("--reason", default="Loady billing reconciliation dry run", help="Reason recorded for this run.")
    args = parser.parse_args()

    if "production" in args.loady_database_url.lower():
        print("Refusing to run: --loady-database-url contains the word 'production'.", file=sys.stderr)
        return 1

    additional_events: list[bytes] = []
    if args.additional_events_file:
        with open(args.additional_events_file, "r", encoding="utf-8") as f:
            for event_dict in json.load(f):
                additional_events.append(json.dumps(event_dict).encode("utf-8"))

    loady_engine = create_engine(args.loady_database_url)
    platform_session = get_session_factory()()
    provider = FakeBillingProvider()

    try:
        actor = _get_or_create_reconciliation_actor(platform_session)
        platform_session.commit()

        report = run_reconciliation(
            platform_session, loady_engine, provider, actor=actor,
            additional_events=additional_events, reason=args.reason, dry_run=not args.commit,
        )
        print("=== COMMITTED ===" if args.commit else "=== DRY RUN (nothing was written - pass --commit to persist) ===")

        summary = report.summary()
        print(" ".join(f"{k}={v}" for k, v in summary.items()))
        for label, rows in (
            ("CREATED", report.created), ("UPDATED", report.updated), ("UNCHANGED", report.unchanged),
            ("RECONCILED WITH CHANGE (additional events)", report.reconciled_with_change),
            ("GIFTED - PRESERVED, NOT TOUCHED", report.gifted_preserved),
            ("ORPHANED CUSTOMER REFERENCE", report.orphaned_customer),
            ("ORPHANED SUBSCRIPTION (no global_user_id yet)", report.orphaned_subscription),
            ("DUPLICATE LOCAL REFERENCE", report.duplicate_local_reference),
            ("FAILED", report.failed),
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
