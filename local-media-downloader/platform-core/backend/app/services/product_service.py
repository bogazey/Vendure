"""Product registry + product membership (mission-brief sections 7-8).

Business logic never assumes exactly ten products — `list_products` simply
returns whatever rows exist, and `touch_membership` (recording that a
global user has actually used a product) works identically for a product
seeded on day one or registered by an admin a year from now.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Product, ProductMembership
from app.models.enums import MembershipStatus
from app.utils.exceptions import NotFoundError


def list_products(session: Session) -> list[Product]:
    return list(session.execute(select(Product).order_by(Product.id)).scalars().all())


def get_product(session: Session, product_id: str) -> Product:
    product = session.get(Product, product_id)
    if product is None:
        raise NotFoundError(f"Unknown product '{product_id}'.")
    return product


def create_product(session: Session, product_id: str, name: str, domain: str, status: str, icon_ref: str | None) -> Product:
    product = Product(id=product_id, name=name, domain=domain, status=status, icon_ref=icon_ref)
    session.add(product)
    session.flush()
    return product


def touch_membership(session: Session, user_id: str, product_id: str) -> ProductMembership:
    """Called only when a global user actually authenticates into a
    product (the OIDC token exchange) — never speculatively, so a global
    account never accumulates memberships in products it has never
    touched (mission-brief section 8)."""
    now = datetime.now(timezone.utc)
    membership = session.execute(
        select(ProductMembership).where(
            ProductMembership.user_id == user_id, ProductMembership.product_id == product_id
        )
    ).scalars().first()
    if membership is None:
        membership = ProductMembership(
            user_id=user_id, product_id=product_id, status=MembershipStatus.ACTIVE.value,
            first_seen_at=now, last_seen_at=now,
        )
        session.add(membership)
    else:
        membership.last_seen_at = now
        membership.status = MembershipStatus.ACTIVE.value
    session.flush()
    return membership


def list_memberships(session: Session, user_id: str) -> list[ProductMembership]:
    return list(
        session.execute(select(ProductMembership).where(ProductMembership.user_id == user_id)).scalars().all()
    )
