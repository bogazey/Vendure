"""The operator-facing `platform product ...` / `platform oauth-client
...` CLI (mission 17: multi-product expansion prep, task "product
onboarding CLI workflow"). A thin wrapper over the same service-layer
functions the Grand Admin API routes call (`product_service`,
`oidc_service`, `service_auth`) - never a second implementation of any
business rule, so CLI and API behavior can never drift apart.

`register_product.py` remains the dedicated "create a brand new product +
its first client + a free plan in one step" tool and is reused here as
`platform product create`, rather than duplicated. This module adds what
that one didn't cover: inspecting/updating/verifying an existing product,
and the OAuth-client lifecycle actions (create/rotate-secret/disable/
enable) - the GENUINE gaps this mission's own audit found (see
docs/platform/PRODUCT_ONBOARDING.md).

A secret is printed to stdout exactly once, via plain `print` (never the
app's `logging_config`, so it can never land in a log file) - the same
posture `register_product.py` already established.

Usage:
    python -m app.scripts.platform_cli product create --slug gamey --name Gamey \\
        --domain gamey.example --redirect-uri https://gamey.example/callback
    python -m app.scripts.platform_cli product inspect --slug gamey
    python -m app.scripts.platform_cli product update --slug gamey --name "Gamey Renamed"
    python -m app.scripts.platform_cli product verify --slug gamey
    python -m app.scripts.platform_cli product enable --slug gamey
    python -m app.scripts.platform_cli product disable --slug gamey

    python -m app.scripts.platform_cli oauth-client create --client-id gamey-web \\
        --name "Gamey Web" --product gamey --redirect-uri https://gamey.example/callback
    python -m app.scripts.platform_cli oauth-client rotate-secret --client-id gamey-web
    python -m app.scripts.platform_cli oauth-client disable --client-id gamey-web
    python -m app.scripts.platform_cli oauth-client enable --client-id gamey-web

Exit codes: 0 success, 1 the requested resource/action failed (a normal
`AppError` - not found, already exists, etc.), 2 bad usage.
"""
from __future__ import annotations

import argparse
import json
import secrets
import sys

from sqlalchemy import select

from app.database.db import get_session_factory
from app.database.models import User
from app.scripts.register_product import register_product as _register_product_and_first_client
from app.security.passwords import hash_password
from app.services import oidc_service, product_service, service_auth
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


# --- product subcommands -----------------------------------------------------

def _cmd_product_create(args: argparse.Namespace) -> int:
    result = _register_product_and_first_client(
        slug=args.slug, name=args.name, domain=args.domain,
        redirect_uris=args.redirect_uris, free_plan_name=args.free_plan_name,
    )
    print(f"Product '{result['product_id']}' registered with plan '{result['free_plan_slug']}'.")
    print(f"  CLIENT_ID={result['client_id']}")
    print(f"  CLIENT_SECRET={result['client_secret']}")
    print("  (this secret is shown ONCE - store it now; it is never retrievable again)")
    return 0


def _cmd_product_inspect(args: argparse.Namespace) -> int:
    session = get_session_factory()()
    try:
        product = product_service.get_product(session, args.slug)
        out = {
            "id": product.id, "name": product.name, "domain": product.domain, "status": product.status,
            "is_active": product.is_active, "is_discoverable": product.is_discoverable,
            "icon_ref": product.icon_ref, "description": product.description,
            "created_at": product.created_at.isoformat(), "updated_at": product.updated_at.isoformat(),
        }
        print(json.dumps(out, indent=2))
        return 0
    finally:
        session.close()


def _cmd_product_verify(args: argparse.Namespace) -> int:
    session = get_session_factory()()
    try:
        report = product_service.verify_product(session, args.slug)
        print(json.dumps(report, indent=2))
        return 0 if all(report["checks"].values()) else 1
    finally:
        session.close()


def _cmd_product_update(args: argparse.Namespace) -> int:
    session = get_session_factory()()
    try:
        kwargs: dict = {}
        if args.name is not None:
            kwargs["name"] = args.name
        if args.domain is not None:
            kwargs["domain"] = args.domain
        if args.status is not None:
            kwargs["status"] = args.status
        if args.icon_ref is not None:
            kwargs["icon_ref"] = args.icon_ref
        if args.description is not None:
            kwargs["description"] = args.description
        product = product_service.update_product(session, args.slug, **kwargs)
        session.commit()
        print(f"Product '{product.id}' updated.")
        return 0
    finally:
        session.close()


def _cmd_product_set_active(args: argparse.Namespace, is_active: bool) -> int:
    session = get_session_factory()()
    try:
        product = product_service.set_product_active(session, args.slug, is_active)
        session.commit()
        print(f"Product '{product.id}' is now {'active' if is_active else 'disabled'}.")
        return 0
    finally:
        session.close()


# --- oauth-client subcommands ------------------------------------------------

def _cmd_client_create(args: argparse.Namespace) -> int:
    session = get_session_factory()()
    try:
        actor = _get_or_create_bootstrap_actor(session)
        _client, raw_secret = oidc_service.register_client(
            session, actor, args.client_id, args.name, args.product, args.redirect_uris,
        )
        session.commit()
        print(f"Client '{args.client_id}' registered.")
        print(f"  CLIENT_SECRET={raw_secret}")
        print("  (this secret is shown ONCE - store it now; it is never retrievable again)")
        return 0
    finally:
        session.close()


def _cmd_client_rotate_secret(args: argparse.Namespace) -> int:
    session = get_session_factory()()
    try:
        actor = _get_or_create_bootstrap_actor(session)
        client = oidc_service.get_client(session, args.client_id)
        if client is None:
            raise AppError(f"Client '{args.client_id}' not found.")
        raw_secret = service_auth.rotate_client_secret(session, actor, client)
        session.commit()
        print(f"Client '{args.client_id}' secret rotated.")
        print(f"  CLIENT_SECRET={raw_secret}")
        print("  (this secret is shown ONCE - store it now; it is never retrievable again)")
        return 0
    finally:
        session.close()


def _cmd_client_set_active(args: argparse.Namespace, is_active: bool) -> int:
    session = get_session_factory()()
    try:
        actor = _get_or_create_bootstrap_actor(session)
        client = oidc_service.get_client(session, args.client_id)
        if client is None:
            raise AppError(f"Client '{args.client_id}' not found.")
        service_auth.set_client_active(session, actor, client, is_active)
        session.commit()
        print(f"Client '{args.client_id}' is now {'active' if is_active else 'disabled'}.")
        return 0
    finally:
        session.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="platform", description="Platform Core operator CLI.")
    subparsers = parser.add_subparsers(dest="resource", required=True)

    product = subparsers.add_parser("product", help="Manage the product registry.")
    product_sub = product.add_subparsers(dest="action", required=True)

    p_create = product_sub.add_parser("create", help="Register a new product + its first OAuth client + a free plan.")
    p_create.add_argument("--slug", required=True)
    p_create.add_argument("--name", required=True)
    p_create.add_argument("--domain", required=True)
    p_create.add_argument("--redirect-uri", dest="redirect_uris", action="append", required=True)
    p_create.add_argument("--free-plan-name", default="Free")
    p_create.set_defaults(func=_cmd_product_create)

    p_inspect = product_sub.add_parser("inspect", help="Print a product's current registry row as JSON.")
    p_inspect.add_argument("--slug", required=True)
    p_inspect.set_defaults(func=_cmd_product_inspect)

    p_verify = product_sub.add_parser("verify", help="Run the onboarding-completeness checklist for a product.")
    p_verify.add_argument("--slug", required=True)
    p_verify.set_defaults(func=_cmd_product_verify)

    p_update = product_sub.add_parser("update", help="Update one or more fields of an existing product.")
    p_update.add_argument("--slug", required=True)
    p_update.add_argument("--name", default=None)
    p_update.add_argument("--domain", default=None)
    p_update.add_argument("--status", default=None, choices=["planned", "building", "live", "retired"])
    p_update.add_argument("--icon-ref", dest="icon_ref", default=None)
    p_update.add_argument("--description", default=None)
    p_update.set_defaults(func=_cmd_product_update)

    p_enable = product_sub.add_parser("enable", help="Re-activate a disabled product.")
    p_enable.add_argument("--slug", required=True)
    p_enable.set_defaults(func=lambda a: _cmd_product_set_active(a, True))

    p_disable = product_sub.add_parser("disable", help="Disable a product - blocks sign-in through ALL its clients.")
    p_disable.add_argument("--slug", required=True)
    p_disable.set_defaults(func=lambda a: _cmd_product_set_active(a, False))

    oauth_client = subparsers.add_parser("oauth-client", help="Manage OAuth clients.")
    client_sub = oauth_client.add_subparsers(dest="action", required=True)

    c_create = client_sub.add_parser("create", help="Register a new OAuth client for a product.")
    c_create.add_argument("--client-id", required=True)
    c_create.add_argument("--name", required=True)
    c_create.add_argument("--product", required=True, help="The owning product's slug.")
    c_create.add_argument("--redirect-uri", dest="redirect_uris", action="append", required=True)
    c_create.set_defaults(func=_cmd_client_create)

    c_rotate = client_sub.add_parser("rotate-secret", help="Rotate a client's secret (old secret stops working immediately).")
    c_rotate.add_argument("--client-id", required=True)
    c_rotate.set_defaults(func=_cmd_client_rotate_secret)

    c_enable = client_sub.add_parser("enable", help="Re-activate a disabled OAuth client.")
    c_enable.add_argument("--client-id", required=True)
    c_enable.set_defaults(func=lambda a: _cmd_client_set_active(a, True))

    c_disable = client_sub.add_parser("disable", help="Disable an OAuth client - blocks sign-in/refresh through it.")
    c_disable.add_argument("--client-id", required=True)
    c_disable.set_defaults(func=lambda a: _cmd_client_set_active(a, False))

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except AppError as exc:
        print(f"Error: {exc.message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
