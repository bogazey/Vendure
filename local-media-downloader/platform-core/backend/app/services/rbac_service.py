"""Generic role + scope RBAC (mission-brief section 17). A scope is either
the literal string "global" or "product:<slug>" — `has_role` checks both
an exact-scope match and, for a global check, whether the user holds the
role globally; a product-scoped admin never automatically gains global
admin (mission-brief section 46: "no product can grant itself global admin
privileges" — enforced simply by never checking anything but the exact
scope requested, plus "global" as its own distinct scope, never a
wildcard)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import RoleAssignment, User
from app.models.enums import GLOBAL_SCOPE, RoleSlug, product_scope


def assign_role(session: Session, user: User, role_slug: RoleSlug, scope: str, granted_by: str | None) -> RoleAssignment:
    existing = session.execute(
        select(RoleAssignment).where(
            RoleAssignment.user_id == user.id,
            RoleAssignment.role_slug == role_slug.value,
            RoleAssignment.scope == scope,
        )
    ).scalars().first()
    if existing is not None:
        return existing
    assignment = RoleAssignment(user_id=user.id, role_slug=role_slug.value, scope=scope, granted_by=granted_by)
    session.add(assignment)
    session.flush()
    return assignment


def revoke_role(session: Session, user_id: str, role_slug: RoleSlug, scope: str) -> bool:
    existing = session.execute(
        select(RoleAssignment).where(
            RoleAssignment.user_id == user_id,
            RoleAssignment.role_slug == role_slug.value,
            RoleAssignment.scope == scope,
        )
    ).scalars().first()
    if existing is None:
        return False
    session.delete(existing)
    return True


def list_roles(session: Session, user_id: str) -> list[RoleAssignment]:
    return list(session.execute(select(RoleAssignment).where(RoleAssignment.user_id == user_id)).scalars().all())


def has_role(session: Session, user_id: str, role_slug: RoleSlug, scope: str = GLOBAL_SCOPE) -> bool:
    return (
        session.execute(
            select(RoleAssignment).where(
                RoleAssignment.user_id == user_id,
                RoleAssignment.role_slug == role_slug.value,
                RoleAssignment.scope == scope,
            )
        ).scalars().first()
        is not None
    )


def is_super_admin(session: Session, user_id: str) -> bool:
    return has_role(session, user_id, RoleSlug.SUPER_ADMIN, GLOBAL_SCOPE)


def is_global_admin(session: Session, user_id: str) -> bool:
    """True for `super_admin` or `admin` at global scope — either can use
    the Grand Admin console; only `super_admin` can additionally manage
    roles/clients (see `deps.require_super_admin`)."""
    return is_super_admin(session, user_id) or has_role(session, user_id, RoleSlug.ADMIN, GLOBAL_SCOPE)


def is_product_admin(session: Session, user_id: str, product_id: str) -> bool:
    """Mission 6 continuation (Product-Scoped RBAC): true only for
    `admin` explicitly scoped to THIS product (`RoleAssignment.scope ==
    "product:<product_id>"`) - never for a role scoped to a different
    product, and never implied by holding the `admin` role at global
    scope (that's `is_global_admin`, checked separately by every caller
    of `deps.require_product_admin`). This is the one function that
    decides whether a "Loady admin" may touch Loady's own catalog - it
    has no code path that can return True for any other product_id."""
    return has_role(session, user_id, RoleSlug.ADMIN, product_scope(product_id))


def is_global_or_product_admin(session: Session, user_id: str, product_id: str) -> bool:
    return is_global_admin(session, user_id) or is_product_admin(session, user_id, product_id)


def admin_visible_product_ids(session: Session, user_id: str) -> set[str] | None:
    """`None` means "no restriction" (global admin - sees every product's
    rows in a cross-product listing endpoint). A concrete (possibly
    empty) set means the caller only holds product-scoped `admin` roles
    and a cross-product listing (gifts, subscriptions, payments, webhook
    events, outbox) must filter to only those - this is what keeps a
    Loady-scoped admin from seeing Gamey's rows in an endpoint that has
    no product_id path parameter to gate at the dependency level."""
    if is_global_admin(session, user_id):
        return None
    rows = session.execute(
        select(RoleAssignment).where(
            RoleAssignment.user_id == user_id, RoleAssignment.role_slug == RoleSlug.ADMIN.value,
            RoleAssignment.scope.like("product:%"),
        )
    ).scalars().all()
    return {row.scope.removeprefix("product:") for row in rows}
