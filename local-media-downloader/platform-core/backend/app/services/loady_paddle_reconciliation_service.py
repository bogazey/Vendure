"""Loady -> Platform Core Paddle billing reconciliation (Mission 8: Billing
Ownership Transition).

Reads a LOCAL COPY of Loady's commercial database (never production - the
caller supplies the connection, this module never picks a default), via
plain SQLAlchemy Core table reflection - exactly the same pattern as
`loady_migration_service.py` (Mission 3), and for the same reason: this
module never imports Loady's ORM, so it works against any Loady database
whose schema matches docs/platform/LOADY_MIGRATION_AUDIT.md, not a
specific Python object graph.

Design (see docs/platform/BILLING_OWNERSHIP_TRANSITION.md and
PADDLE_RECONCILIATION_STRATEGY.md for the full rationale):

- Read-only on the Loady side. Unlike the identity migration, this module
  never writes anything back to Loady's database - a paid Loady
  subscription's local row is the STARTING point for a "bootstrap" webhook
  event, never mutated itself.
- Reconciliation is "just" event replay: a Loady subscription's current
  local snapshot becomes one bootstrap `subscription.*`-shaped event
  (timestamped at that row's own `updated_at`), fed through the exact same
  `webhook_service.receive_webhook` pipeline a real live webhook uses -
  idempotency, out-of-order protection, and refund/chargeback handling are
  therefore not reimplemented here, they are INHERITED. Any additional
  synthetic events (a later real Paddle event that happened during the
  cutover window) are replayed the same way, in delivery order - the
  pipeline's own `occurred_at` guard decides what actually wins.
- Requires `User.global_user_id` to already be set (Mission 3's identity
  migration is a hard prerequisite) - a paid subscription for an
  unmigrated Loady user is reported `orphaned_subscription`, never
  guessed at.
- Never touches a Loady subscription with `provider="gifted"` - those are
  Mission 3's `loady_migration_service.py`'s job (identity + entitlement
  import), not a billing-provider concern. Reported for visibility only
  (`gifted_preserved`), to make the financial separation this mission
  requires provable in the report, not just asserted.
- `dry_run=True` (the default) performs every read AND every write exactly
  as a real run would, then rolls back the Platform Core session - a
  caller cannot half-apply a dry run.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import MetaData, Table, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import StatementError
from sqlalchemy.orm import Session

from app.database.models import BillingWebhookEvent, Subscription, User
from app.services import subscription_service, webhook_service
from app.services.billing.base import BillingProvider

LOADY_PRODUCT_ID = "loady"
_RECONCILABLE_PROVIDER = "paddle"


@dataclass
class ReconciliationReport:
    created: list[dict] = field(default_factory=list)
    updated: list[dict] = field(default_factory=list)
    unchanged: list[dict] = field(default_factory=list)
    reconciled_with_change: list[dict] = field(default_factory=list)
    gifted_preserved: list[dict] = field(default_factory=list)
    orphaned_customer: list[dict] = field(default_factory=list)
    orphaned_subscription: list[dict] = field(default_factory=list)
    duplicate_local_reference: list[dict] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)
    additional_events_processed: list[dict] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "created": len(self.created),
            "updated": len(self.updated),
            "unchanged": len(self.unchanged),
            "reconciled_with_change": len(self.reconciled_with_change),
            "gifted_preserved": len(self.gifted_preserved),
            "orphaned_customer": len(self.orphaned_customer),
            "orphaned_subscription": len(self.orphaned_subscription),
            "duplicate_local_reference": len(self.duplicate_local_reference),
            "failed": len(self.failed),
            "additional_events_processed": len(self.additional_events_processed),
        }


def _reflect_loady_tables(loady_engine: Engine) -> tuple[Table, Table]:
    metadata = MetaData()
    metadata.reflect(bind=loady_engine, only=["users", "subscriptions"])
    return metadata.tables["users"], metadata.tables["subscriptions"]


def _as_utc(value) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def _bootstrap_event_body(sub_row: dict, global_user_id: str) -> bytes:
    """One `subscription.*`-shaped payload built directly from a Loady
    subscription row's OWN current snapshot - `FakeBillingProvider`'s
    payload shape (see its `normalize_event`), since a local dry-run never
    calls a real Paddle endpoint and this is what proves the reconciliation
    pipeline end-to-end without one. A real cutover would use
    `PaddleBillingProvider` fed real historical webhook payloads instead
    (see PADDLE_LIVE_INPUTS_REQUIRED.md) - the reconciliation ALGORITHM
    below is identical either way, only the provider/payload shape
    changes."""
    payload = {
        "event_id": f"bootstrap_{sub_row['id']}",
        "event_type": "subscription.created",
        "occurred_at": _as_utc(sub_row["updated_at"]).isoformat(),
        "subscription_ref": sub_row["provider_subscription_id"],
        "customer_ref": sub_row["provider_customer_id"] or f"unknown_customer_{sub_row['user_id']}",
        "status": sub_row["status"],
        "custom_data": {"user_id": global_user_id, "product_id": LOADY_PRODUCT_ID, "plan_slug": sub_row["plan"]},
    }
    if sub_row.get("current_period_start"):
        payload["current_period_start"] = _as_utc(sub_row["current_period_start"]).isoformat()
    if sub_row.get("current_period_end"):
        payload["current_period_end"] = _as_utc(sub_row["current_period_end"]).isoformat()
    if sub_row.get("cancel_at_period_end") is not None:
        payload["cancel_at_period_end"] = bool(sub_row["cancel_at_period_end"])
    return json.dumps(payload).encode("utf-8")


def _safe_error_reason(exc: Exception) -> str:
    """Mirrors `loady_migration_service._safe_error_reason` (Mission 3,
    same finding): `str(exc)` on a SQLAlchemy `StatementError` embeds the
    failing statement's BOUND PARAMETERS, which could include anything a
    write in this module's call chain touches. `.orig` is the underlying
    DBAPI exception's own message alone - never the statement or its
    parameters - so this report (printed verbatim by the CLI) can never
    leak one, regardless of what future write path might raise here."""
    if isinstance(exc, StatementError):
        return f"{type(exc).__name__}: {exc.orig}"
    return f"{type(exc).__name__}: {exc}"


def _already_journaled(session: Session, provider_name: str, event_id: str) -> BillingWebhookEvent | None:
    """A pre-check, not a reliance on `webhook_service.receive_webhook`'s
    own internal duplicate handling - that internal path calls
    `session.rollback()` on an `IntegrityError`, which is safe for a
    single, request-scoped session (production's real usage) but would
    silently discard every OTHER subscription's unflushed, uncommitted
    work already accumulated earlier in this SAME reconciliation run
    (this module deliberately shares one session/transaction across many
    events - see `run_reconciliation`'s own docstring on dry-run
    semantics). Checking first, and simply not calling `receive_webhook`
    again for an event this run has already seen, avoids ever exercising
    that internal rollback path at all."""
    return session.execute(
        select(BillingWebhookEvent).where(
            BillingWebhookEvent.provider == provider_name,
            BillingWebhookEvent.provider_event_id == event_id,
        )
    ).scalars().first()


def _sign(provider: BillingProvider, body: bytes) -> dict[str, str]:
    """`FakeBillingProvider` exposes a `sign()` test helper;
    `PaddleBillingProvider` has no such thing (a real cutover would carry
    genuine `Paddle-Signature` headers from Paddle itself, never generated
    locally) - this reconciliation module only ever drives
    `FakeBillingProvider` for its own bootstrap events, so this is safe."""
    sign = getattr(provider, "sign", None)
    if sign is None:
        raise TypeError(
            f"{type(provider).__name__} cannot locally sign a bootstrap event - "
            "reconciliation bootstrap events are only ever run through FakeBillingProvider."
        )
    return {"fake-signature": sign(body)}


def run_reconciliation(
    platform_session: Session,
    loady_engine: Engine,
    provider: BillingProvider,
    actor: User,
    additional_events: list[bytes] | None = None,
    reason: str | None = None,
    dry_run: bool = True,
) -> ReconciliationReport:
    """Reconciles every Loady user's PAID (provider="paddle") subscription
    into Platform Core's billing engine. `additional_events` are extra raw
    webhook bodies (in delivery order - may be duplicated/out-of-order/
    delayed relative to their own `occurred_at`) replayed AFTER every
    Loady subscription's bootstrap event, so a synthetic "what happened at
    Paddle during the cutover window" stream can be layered on top and
    proven to reconcile correctly against the bootstrapped state."""
    report = ReconciliationReport()
    users_table, subs_table = _reflect_loady_tables(loady_engine)

    with loady_engine.connect() as loady_conn:
        rows = loady_conn.execute(
            select(users_table).order_by(users_table.c.created_at, users_table.c.id)
        ).mappings().all()

        for user_row in rows:
            loady_user_id = user_row["id"]
            global_user_id = user_row.get("global_user_id")
            email = user_row["email"]

            sub_rows = loady_conn.execute(
                select(subs_table).where(subs_table.c.user_id == loady_user_id)
            ).mappings().all()
            if not sub_rows:
                continue

            paid_rows = [r for r in sub_rows if r["provider"] == _RECONCILABLE_PROVIDER]
            gifted_rows = [r for r in sub_rows if r["provider"] != _RECONCILABLE_PROVIDER]

            for gifted in gifted_rows:
                report.gifted_preserved.append({
                    "loady_user_id": loady_user_id, "email": email,
                    "plan": gifted["plan"], "status": gifted["status"],
                    "also_has_paid_subscription": len(paid_rows) > 0,
                    "note": (
                        "financially separate - never touched by billing reconciliation; "
                        "identity/entitlement import is loady_migration_service.py's job (Mission 3)"
                        + (". A paid subscription also exists and takes precedence for entitlement." if paid_rows else "")
                    ),
                })

            refs = [r["provider_subscription_id"] for r in paid_rows if r["provider_subscription_id"]]
            if len(refs) != len(set(refs)):
                report.duplicate_local_reference.append({
                    "loady_user_id": loady_user_id, "email": email, "duplicate_refs": refs,
                    "reason": "more than one local Subscription row shares the same provider_subscription_id - "
                              "refusing to guess which is authoritative.",
                })
                continue

            for sub_row in paid_rows:
                sub_ref = sub_row["provider_subscription_id"]
                if not sub_ref:
                    if sub_row["provider_customer_id"]:
                        report.orphaned_customer.append({
                            "loady_user_id": loady_user_id, "email": email,
                            "provider_customer_id": sub_row["provider_customer_id"],
                            "reason": "a Paddle customer reference exists with no subscription reference - "
                                      "nothing to reconcile (e.g. checkout started, never completed).",
                        })
                    continue

                if not global_user_id:
                    report.orphaned_subscription.append({
                        "loady_user_id": loady_user_id, "email": email, "provider_subscription_id": sub_ref,
                        "reason": "this Loady user has a real paid subscription but no global_user_id yet - "
                                  "run the identity migration (Mission 3) first.",
                    })
                    continue

                pre_existing = subscription_service.get_subscription_by_ref(platform_session, provider.name, sub_ref)
                pre_status = pre_existing.status if pre_existing else None
                pre_period_end = pre_existing.current_period_end if pre_existing else None

                bootstrap_event_id = f"bootstrap_{sub_row['id']}"
                already = _already_journaled(platform_session, provider.name, bootstrap_event_id)
                try:
                    if already is not None:
                        journal = already
                    else:
                        body = _bootstrap_event_body(dict(sub_row), global_user_id)
                        headers = _sign(provider, body)
                        journal = webhook_service.receive_webhook(platform_session, provider, body, headers)
                except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                    report.failed.append({
                        "loady_user_id": loady_user_id, "email": email, "provider_subscription_id": sub_ref,
                        "reason": _safe_error_reason(exc),
                    })
                    continue

                if journal.status == "failed":
                    report.failed.append({
                        "loady_user_id": loady_user_id, "email": email, "provider_subscription_id": sub_ref,
                        "reason": journal.failure_reason,
                    })
                    continue

                entry = {
                    "loady_user_id": loady_user_id, "email": email, "global_user_id": global_user_id,
                    "provider_subscription_id": sub_ref, "plan": sub_row["plan"], "status": sub_row["status"],
                }
                if pre_existing is None:
                    report.created.append(entry)
                elif pre_status != sub_row["status"] or pre_period_end != pre_existing.current_period_end:
                    report.updated.append(entry)
                else:
                    report.unchanged.append(entry)

        for body in additional_events or []:
            try:
                headers = _sign(provider, body)
            except TypeError as exc:
                report.failed.append({"reason": str(exc)})
                continue

            # Snapshot pre-state so a status/period CHANGE caused by this
            # additional event (e.g. a renewal or cancellation that
            # happened during the cutover window) is visible in the
            # report as `reconciled_with_change`, distinct from a routine
            # duplicate/no-op replay.
            try:
                parsed = json.loads(body)
            except ValueError:
                parsed = {}
            sub_ref = parsed.get("subscription_ref")
            pre = subscription_service.get_subscription_by_ref(platform_session, provider.name, sub_ref) if sub_ref else None
            pre_status, pre_period_end = (pre.status, pre.current_period_end) if pre else (None, None)

            try:
                already = _already_journaled(platform_session, provider.name, parsed.get("event_id", "")) if parsed.get("event_id") else None
                journal = already if already is not None else webhook_service.receive_webhook(platform_session, provider, body, headers)
            except Exception as exc:  # noqa: BLE001
                report.failed.append({"reason": _safe_error_reason(exc), "raw_event": body.decode("utf-8", "replace")[:200]})
                continue

            post = subscription_service.get_subscription_by_ref(platform_session, provider.name, sub_ref) if sub_ref else None
            changed = post is not None and (post.status != pre_status or post.current_period_end != pre_period_end)
            record = {
                "provider_subscription_id": sub_ref, "event_status": journal.status,
                "event_type": journal.event_type,
                "before": {"status": pre_status, "current_period_end": str(pre_period_end)},
                "after": {"status": post.status if post else None, "current_period_end": str(post.current_period_end) if post else None},
            }
            report.additional_events_processed.append(record)
            if changed:
                report.reconciled_with_change.append(record)

        if dry_run:
            platform_session.rollback()
        else:
            platform_session.commit()

    return report
