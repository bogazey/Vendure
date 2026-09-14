"""Product onboarding CLI (mission-brief Phase 29) - the general tool
`register_demo_clients.py`/`register_loady_client.py` were each one-off,
hard-coded instances of. A developer onboarding a brand-new product runs
this instead of hand-writing a bootstrap script per product.

Idempotent by product slug and by client_id: re-running against an
already-registered product/client reports that and does nothing further
- exactly like `register_demo_clients.py`'s existing precedent, and for
the same reason (a client secret is stored only as an Argon2 hash; a lost
secret means rotating it via the admin API, never re-printing the old
one).

Usage:
    python -m app.scripts.register_product \
        --slug sample-future-product \
        --name "Sample Future Product" \
        --domain sfp.example \
        --redirect-uri https://sfp.example/auth/callback \
        [--redirect-uri https://sfp.example/auth/callback2 ...] \
        [--free-plan-name Free]

The client secret is printed to stdout exactly once, at registration
time. It is never logged (this script uses `print`, not the app's own
`logging_config`, specifically so it is never captured into a log file
the way every other line of application output is) and never stored in
plaintext anywhere.
"""
from __future__ import annotations

import argparse
import secrets
import sys

from sqlalchemy import select

from app.database.db import get_session_factory
from app.database.models import OAuthClient, Product, User
from app.security.passwords import hash_password
from app.services import entitlement_service, oidc_service, product_service
from app.utils.exceptions import AppError

_BOOTSTRAP_ACTOR_EMAIL = "bootstrap@platform-core.local"


def _get_or_create_bootstrap_actor(session) -> User:
    actor = session.execute(select(User).where(User.email == _BOOTSTRAP_ACTOR_EMAIL)).scalars().first()
    if actor is not None:
        return actor
    actor = User(email=_BOOTSTRAP_ACTOR_EMAIL, password_hash=hash_password(secrets.token_urlsafe(32)), email_verified=True)
    session.add(actor)
    session.flush()
    return actor


def register_product(
    *, slug: str, name: str, domain: str, redirect_uris: list[str], free_plan_name: str = "Free"
) -> dict:
    """The importable core of the CLI - `main()` below is just an
    argparse wrapper around this, so the same onboarding logic is
    reusable from a test (`test_register_product_cli.py`) or a future
    admin-UI "onboard a product" action without shelling out."""
    session = get_session_factory()()
    try:
        actor = _get_or_create_bootstrap_actor(session)

        if session.get(Product, slug) is not None:
            raise AppError(f"Product '{slug}' already exists - nothing to do.")

        product = product_service.create_product(session, slug, name, domain, "live", None)
        free_plan = entitlement_service.get_or_create_plan(session, product.id, "free", free_plan_name)

        client_id = f"{slug}-client"
        if session.get(OAuthClient, client_id) is not None:
            raise AppError(f"Client '{client_id}' already exists - nothing to do.")

        _client, raw_secret = oidc_service.register_client(session, actor, client_id, name, product.id, redirect_uris)
        session.commit()
        return {
            "product_id": product.id, "client_id": client_id, "client_secret": raw_secret,
            "free_plan_id": free_plan.id, "free_plan_slug": free_plan.slug,
        }
    finally:
        session.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Register a new product with Platform Core.")
    parser.add_argument("--slug", required=True, help="Short, stable product id, e.g. 'gamey'.")
    parser.add_argument("--name", required=True, help="Human-readable display name.")
    parser.add_argument("--domain", required=True, help="The product's own domain.")
    parser.add_argument("--redirect-uri", dest="redirect_uris", action="append", required=True,
                         help="An OAuth redirect URI this product's OIDC client may use. May be repeated.")
    parser.add_argument("--free-plan-name", default="Free")
    args = parser.parse_args(argv)

    try:
        result = register_product(
            slug=args.slug, name=args.name, domain=args.domain,
            redirect_uris=args.redirect_uris, free_plan_name=args.free_plan_name,
        )
    except AppError as exc:
        print(f"Error: {exc.message}", file=sys.stderr)
        return 1

    print(f"Product '{result['product_id']}' registered with plan '{result['free_plan_slug']}'.")
    print(f"  CLIENT_ID={result['client_id']}")
    print(f"  CLIENT_SECRET={result['client_secret']}")
    print("  (this secret is shown ONCE - store it now; it is never retrievable again)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
