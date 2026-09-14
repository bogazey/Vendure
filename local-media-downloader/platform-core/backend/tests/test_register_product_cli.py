"""Mission 6 (Phase 29, and half of Phase 53): the product-onboarding CLI.
`register_product` is exercised as a plain function call here (the same
code `main()`'s argparse wrapper calls) - `main()` itself is a thin CLI
shim over it and is not separately re-tested."""
from __future__ import annotations

from app.database.models import OAuthClient, Plan, Product
from app.scripts.register_product import register_product
from app.security import passwords
from app.utils.exceptions import AppError


def test_register_product_creates_product_plan_and_client(db_session):
    result = register_product(
        slug="cli-product-a", name="CLI Product A", domain="cli-a.example",
        redirect_uris=["https://cli-a.example/callback"],
    )
    assert result["client_id"] == "cli-product-a-client"
    assert result["client_secret"]

    product = db_session.get(Product, "cli-product-a")
    assert product is not None
    assert product.status == "live"

    plan = db_session.get(Plan, result["free_plan_id"])
    assert plan.slug == "free"

    client = db_session.get(OAuthClient, "cli-product-a-client")
    assert client is not None
    assert client.redirect_uris == ["https://cli-a.example/callback"]
    # The secret is never stored in plaintext - only its hash.
    assert passwords.verify_password(result["client_secret"], client.client_secret_hash)


def test_register_product_is_idempotent_refuses_a_second_registration(db_session):
    register_product(slug="cli-product-b", name="CLI Product B", domain="cli-b.example", redirect_uris=["https://cli-b.example/cb"])
    try:
        register_product(slug="cli-product-b", name="CLI Product B Again", domain="cli-b.example", redirect_uris=["https://cli-b.example/cb"])
        assert False, "expected AppError on re-registration"
    except AppError as exc:
        assert "already exists" in exc.message


def test_registered_product_requires_no_platform_core_source_change_to_use(db_session):
    """The mission-brief Phase 53 bar: onboarding must not require
    editing Platform Core source. This test proves it by using ONLY the
    generic services every other product uses (product_service,
    entitlement_service, capability_service) against the CLI-created
    product - nothing here is a special case for 'cli-product-c'."""
    from app.services import capability_service, entitlement_service, product_service
    from app.models.enums import CapabilityValueType

    result = register_product(slug="cli-product-c", name="CLI Product C", domain="cli-c.example", redirect_uris=["https://cli-c.example/cb"])

    products = product_service.list_products(db_session)
    assert any(p.id == "cli-product-c" for p in products)

    plan = db_session.get(Plan, result["free_plan_id"])
    capability_service.define_capability(db_session, "cli-product-c", "widgets.max", CapabilityValueType.INTEGER)
    capability_service.set_plan_entitlement(db_session, plan, "widgets.max", 5)
    db_session.commit()

    assert capability_service.get_plan_capabilities(db_session, plan.id) == {"widgets.max": 5}
