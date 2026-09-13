"""Idempotent seeding of the small, static `roles` reference table — these
are fixed application config (five well-known role slugs), not user/business
data, so seeding them on every startup (unlike products/plans/admins, which
are explicit CLI-only actions — see `app/scripts/`) is safe and standard.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.database.models import Role
from app.models.enums import RoleSlug

_ROLE_NAMES = {
    RoleSlug.SUPER_ADMIN: "Super Admin",
    RoleSlug.ADMIN: "Admin",
    RoleSlug.SUPPORT: "Support",
    RoleSlug.FINANCE: "Finance",
    RoleSlug.USER: "User",
}


def ensure_roles(session: Session) -> None:
    for slug, name in _ROLE_NAMES.items():
        if session.get(Role, slug.value) is None:
            session.add(Role(slug=slug.value, name=name))
    session.commit()
