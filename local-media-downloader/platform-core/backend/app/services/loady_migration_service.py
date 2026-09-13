"""Loady -> Platform Core identity migration, dry-run capable.

Reads a LOCAL COPY of Loady's commercial database (never production - the
caller supplies the connection, this module never picks a default) via
plain SQLAlchemy Core table reflection - this module intentionally never
imports Loady's ORM models, since the two services have separate
dependency trees and this script is meant to work against any Loady
database whose schema matches docs/platform/LOADY_MIGRATION_AUDIT.md,
not a specific Python object graph.

Design (mission-brief "Local data migration strategy" + "Idempotency"):

- Two-phase: first resolve/create/link every Loady user's Platform Core
  identity (so every `loady_user_id -> global_user_id` mapping is known),
  THEN process subscriptions/roles/memberships - this lets a gifted
  subscription's `granted_by_admin_id` (itself a Loady user id) resolve to
  that admin's own `global_user_id` regardless of row order.
- Matching is by Loady's own primary key first (via the `global_user_id`
  already written back from a prior run - the actual steady-state
  identity key, per mission-brief), falling back to email ONLY to link a
  Loady user's FIRST migration to an already-existing Platform Core
  account (e.g. one created via a demo product with the same email) -
  never to silently re-link or merge on a later run.
- `source in {paddle, gifted}` is asserted for every subscription row
  read - an unrecognized provider value STOPS that user's migration and
  is reported as `failed`, never guessed.
- Every write goes through the existing, already-idempotent
  `entitlement_service`/`rbac_service`/`product_service`/`audit_service`
  calls - no new idempotency logic invented here.
- `dry_run=True` (the default) runs every read AND every write exactly as
  a real run would (so the report is provably accurate, not a separate
  "preview" code path that could drift from reality), then rolls back
  BOTH the Platform Core session and the Loady connection itself, inside
  this function - a caller cannot half-apply a dry run by forgetting to
  roll back one side, because there is no external step to forget. See
  `app/scripts/loady_migration_dry_run.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import MetaData, Table, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import StatementError
from sqlalchemy.orm import Session

from app.database.models import Product, User
from app.models.enums import AuditAction, EntitlementSource, RoleSlug
from app.services import audit_service, entitlement_service, product_service, rbac_service

LOADY_PRODUCT_ID = "loady"
_ACTIVE_SUBSCRIPTION_STATUSES = {"active", "trialing", "past_due"}
_KNOWN_PROVIDERS = {"paddle": EntitlementSource.PADDLE, "gifted": EntitlementSource.GIFTED}
_LOADY_PLANS = ("free", "pro", "creator")


@dataclass
class MigrationReport:
    created: list[dict] = field(default_factory=list)
    linked: list[dict] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    conflicted: list[dict] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "created": len(self.created),
            "linked": len(self.linked),
            "skipped": len(self.skipped),
            "conflicted": len(self.conflicted),
            "failed": len(self.failed),
        }


def _safe_error_reason(exc: Exception) -> str:
    """A failure reason safe to put in this module's report AND print to
    stdout (see loady_migration_dry_run.py) - `str(exc)` on a SQLAlchemy
    `StatementError` (IntegrityError included) embeds the failing
    statement's BOUND PARAMETERS, which for the phase-1 user-creation
    INSERT includes the migrated user's Argon2 password hash. `.orig` is
    the underlying DBAPI exception's message alone (e.g. sqlite3's
    "UNIQUE constraint failed: ...") - never the statement or its
    parameters."""
    if isinstance(exc, StatementError):
        return f"{type(exc).__name__}: {exc.orig}"
    return f"{type(exc).__name__}: {exc}"


def _reflect_loady_tables(loady_engine: Engine) -> tuple[Table, Table]:
    metadata = MetaData()
    metadata.reflect(bind=loady_engine, only=["users", "subscriptions"])
    return metadata.tables["users"], metadata.tables["subscriptions"]


def _ensure_loady_product_and_plans(platform_session: Session) -> None:
    if platform_session.get(Product, LOADY_PRODUCT_ID) is None:
        product_service.create_product(
            platform_session, LOADY_PRODUCT_ID, "Loady", "loady.cc", "live", None
        )
    for slug in _LOADY_PLANS:
        entitlement_service.get_or_create_plan(platform_session, LOADY_PRODUCT_ID, slug, slug.title())


def run_migration(
    platform_session: Session,
    loady_engine: Engine,
    actor: User,
    reason: str | None = None,
    dry_run: bool = True,
) -> MigrationReport:
    """Runs the full migration against whatever is on the other end of
    `loady_engine` (a local test copy - see module docstring) and
    `platform_session`. Owns the commit/rollback decision for BOTH
    resources itself (`dry_run=True`, the default, rolls both back at the
    end; `dry_run=False` commits both) - a caller cannot "half-apply" a
    dry run by forgetting to roll back one side, because there is no
    external step to forget."""
    report = MigrationReport()
    _ensure_loady_product_and_plans(platform_session)

    users_table, subscriptions_table = _reflect_loady_tables(loady_engine)

    with loady_engine.connect() as loady_conn:
        loady_rows = loady_conn.execute(
            select(users_table).order_by(users_table.c.created_at, users_table.c.id)
        ).mappings().all()

        # Phase 1: resolve every Loady user's Platform Core identity first,
        # so phase 2's admin-attribution lookups always have a complete map.
        loady_id_to_global_id: dict[str, str] = {}
        resolved_rows: list[dict] = []

        for row in loady_rows:
            loady_id = row["id"]
            email = row["email"].strip().lower()
            existing_global_id = row.get("global_user_id")

            try:
                if existing_global_id:
                    platform_user = platform_session.get(User, existing_global_id)
                    if platform_user is None:
                        report.conflicted.append({
                            "loady_user_id": loady_id, "email": email,
                            "reason": f"global_user_id '{existing_global_id}' set on the Loady row but no such Platform Core user exists.",
                        })
                        continue
                    if platform_user.email.strip().lower() != email:
                        report.conflicted.append({
                            "loady_user_id": loady_id, "email": email,
                            "reason": f"global_user_id '{existing_global_id}' is linked to a different email ('{platform_user.email}').",
                        })
                        continue
                    action = "skipped"
                else:
                    platform_user = platform_session.execute(
                        select(User).where(User.email == email)
                    ).scalars().first()
                    if platform_user is None:
                        platform_user = User(
                            email=email,
                            password_hash=row["password_hash"],
                            email_verified=bool(row["email_verified"]),
                            status=row["status"],
                        )
                        platform_session.add(platform_user)
                        platform_session.flush()
                        action = "created"
                    else:
                        # Linking to an already-existing Platform Core account
                        # (e.g. from a demo product) - never overwrite its
                        # existing credential, only record the link.
                        action = "linked"

                loady_id_to_global_id[loady_id] = platform_user.id
                resolved_rows.append({
                    "loady_row": dict(row), "global_id": platform_user.id,
                    "platform_user": platform_user, "action": action,
                })
            except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                report.failed.append({"loady_user_id": loady_id, "email": email, "reason": _safe_error_reason(exc)})

        # Write the mapping back onto the Loady row now that phase 1 is
        # complete for every user (so a later failure in phase 2 for one
        # user never leaves an earlier user's mapping half-written). The
        # connection auto-began a transaction on the SELECT above already -
        # commit/rollback is decided once, at the very end of this
        # function (see the finally-equivalent block below), never here.
        for entry in resolved_rows:
            if entry["action"] in ("created", "linked"):
                loady_conn.execute(
                    users_table.update()
                    .where(users_table.c.id == entry["loady_row"]["id"])
                    .values(global_user_id=entry["global_id"])
                )

        # Phase 2: memberships, roles, entitlements - now that every user
        # in this batch has a resolved global_user_id.
        for entry in resolved_rows:
            loady_row = entry["loady_row"]
            platform_user = entry["platform_user"]
            loady_id = loady_row["id"]
            try:
                product_service.touch_membership(platform_session, platform_user.id, LOADY_PRODUCT_ID)

                if loady_row["role"] == "admin":
                    rbac_service.assign_role(
                        platform_session, platform_user, RoleSlug.ADMIN, "product:loady", granted_by=actor.id
                    )

                sub_row = loady_conn.execute(
                    select(subscriptions_table)
                    .where(subscriptions_table.c.user_id == loady_id)
                ).mappings().all()
                active_sub = next(
                    (s for s in sorted(sub_row, key=lambda s: s.get("updated_at") or "", reverse=True)
                     if s["status"] in _ACTIVE_SUBSCRIPTION_STATUSES),
                    None,
                )

                granting_admin = actor
                if active_sub is None:
                    source, plan_slug, expires_at, ent_reason = EntitlementSource.FREE, "free", None, reason
                else:
                    provider = active_sub["provider"]
                    if provider not in _KNOWN_PROVIDERS:
                        report.failed.append({
                            "loady_user_id": loady_id, "email": loady_row["email"],
                            "reason": f"Unrecognized subscription provider '{provider}' - refusing to guess.",
                        })
                        continue
                    source = _KNOWN_PROVIDERS[provider]
                    plan_slug = active_sub["plan"]
                    expires_at = active_sub.get("current_period_end")
                    ent_reason = reason
                    if source is EntitlementSource.GIFTED:
                        ent_reason = active_sub.get("granted_reason") or reason
                        granted_by_loady_id = active_sub.get("granted_by_admin_id")
                        granted_by_global_id = (
                            loady_id_to_global_id.get(granted_by_loady_id) if granted_by_loady_id else None
                        )
                        if granted_by_global_id:
                            granting_admin = platform_session.get(User, granted_by_global_id) or actor

                entitlement_service.grant_or_change(
                    platform_session,
                    admin=granting_admin,
                    target=platform_user,
                    product_id=LOADY_PRODUCT_ID,
                    plan_slug=plan_slug,
                    source=source,
                    expires_at=_as_utc(expires_at),
                    reason=ent_reason,
                )

                audit_service.record(
                    platform_session, actor.id, AuditAction.LOADY_MIGRATION_IMPORT,
                    "user", platform_user.id, product_id=LOADY_PRODUCT_ID,
                    after_state={
                        "loady_user_id": loady_id, "action": entry["action"],
                        "entitlement_source": source.value, "plan": plan_slug,
                    },
                    reason=reason,
                )

                getattr(report, entry["action"]).append({
                    "loady_user_id": loady_id, "email": loady_row["email"],
                    "global_user_id": platform_user.id, "entitlement_source": source.value, "plan": plan_slug,
                })
            except Exception as exc:  # noqa: BLE001
                report.failed.append({
                    "loady_user_id": loady_id, "email": loady_row["email"], "reason": _safe_error_reason(exc),
                })

        # Finalize both resources together, here, once - never left for an
        # external caller to remember (see the docstring above).
        platform_session.flush()
        if dry_run:
            loady_conn.rollback()
            platform_session.rollback()
        else:
            loady_conn.commit()
            platform_session.commit()

    return report


def _as_utc(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value
