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

from app.database.models import OAuthClient, Plan, Product, ProductMembership
from app.models.enums import MembershipStatus
from app.utils.exceptions import NotFoundError


def list_products(session: Session) -> list[Product]:
    return list(session.execute(select(Product).order_by(Product.id)).scalars().all())


def get_product(session: Session, product_id: str) -> Product:
    product = session.get(Product, product_id)
    if product is None:
        raise NotFoundError(f"Unknown product '{product_id}'.")
    return product


def create_product(
    session: Session, product_id: str, name: str, domain: str, status: str, icon_ref: str | None,
    *, description: str | None = None, is_discoverable: bool = True,
) -> Product:
    product = Product(
        id=product_id, name=name, domain=domain, status=status, icon_ref=icon_ref,
        description=description, is_discoverable=is_discoverable,
    )
    session.add(product)
    session.flush()
    return product


def update_product(
    session: Session, product_id: str,
    *,
    name: str | None = None,
    domain: str | None = None,
    status: str | None = None,
    icon_ref: str | None = ...,
    description: str | None = ...,
    is_discoverable: bool | None = None,
) -> Product:
    """Updates only the fields explicitly supplied - `id` is never one of
    them (mission requirement: product ids are stable/immutable once
    created, since every other table's `product_id` foreign key, and every
    product's own OAuth client/redirect-uri configuration, already
    references it). `icon_ref`/`description` use `...` as their
    "not supplied" sentinel rather than `None`, since `None` is itself a
    valid value a caller may want to explicitly clear."""
    product = get_product(session, product_id)
    if name is not None:
        product.name = name
    if domain is not None:
        product.domain = domain
    if status is not None:
        product.status = status
    if icon_ref is not ...:
        product.icon_ref = icon_ref
    if description is not ...:
        product.description = description
    if is_discoverable is not None:
        product.is_discoverable = is_discoverable
    session.flush()
    return product


def set_product_active(session: Session, product_id: str, is_active: bool) -> Product:
    product = get_product(session, product_id)
    product.is_active = is_active
    session.flush()
    return product


def verify_product(session: Session, product_id: str) -> dict:
    """Read-only onboarding-completeness check (mission 17) - the
    programmatic equivalent of `NEW_PRODUCT_ONBOARDING.md` step 9's manual
    checklist. Never used to gate anything at runtime (a product can be
    fully "live" with `has_free_plan=False` if it's genuinely paid-only) -
    purely informational for an operator running `platform product
    verify`."""
    product = get_product(session, product_id)
    clients = list(
        session.execute(select(OAuthClient).where(OAuthClient.product_id == product_id)).scalars().all()
    )
    plans = list(session.execute(select(Plan).where(Plan.product_id == product_id)).scalars().all())
    active_clients = [c for c in clients if c.is_active]
    has_free_plan = any(p.slug == "free" for p in plans)
    checks = {
        "product_exists": True,
        "product_is_active": product.is_active,
        "has_at_least_one_oauth_client": len(clients) > 0,
        "has_at_least_one_active_oauth_client": len(active_clients) > 0,
        "every_active_client_has_redirect_uris": all(bool(c.redirect_uris) for c in active_clients),
        "has_at_least_one_plan": len(plans) > 0,
    }
    return {
        "product_id": product_id,
        "product_is_active": product.is_active,
        "oauth_client_count": len(clients),
        "active_oauth_client_count": len(active_clients),
        "plan_count": len(plans),
        "has_free_plan": has_free_plan,
        "checks": checks,
    }


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
