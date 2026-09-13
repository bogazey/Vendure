"""Local-development-only bootstrap: registers Loady as an OIDC client of
Platform Core (mission: "Loady is registered as a Platform Core OAuth
client"). Same idempotent pattern as `register_demo_clients.py`.

Usage: python -m app.scripts.register_loady_client [--redirect-uri URL]

Default redirect URI matches Loady's local dev backend
(`local-media-downloader/backend/app/main.py` binds port 8000).
"""
from __future__ import annotations

import argparse
import secrets

from sqlalchemy import select

from app.database.db import get_session_factory
from app.database.models import OAuthClient, Product, User
from app.security.passwords import hash_password
from app.services import entitlement_service, oidc_service

CLIENT_ID = "loady"
_LOADY_PLANS = ("free", "pro", "creator")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--redirect-uri", default="http://localhost:8000/api/auth/platform/callback",
        help="Exact callback URL Loady's backend will use - must match app/api/routes_platform_auth.py.",
    )
    args = parser.parse_args()

    session = get_session_factory()()
    try:
        actor = session.execute(select(User).where(User.email == "bootstrap@platform-core.local")).scalars().first()
        if actor is None:
            actor = User(
                email="bootstrap@platform-core.local",
                password_hash=hash_password(secrets.token_urlsafe(32)),
                email_verified=True,
            )
            session.add(actor)
            session.flush()

        if session.get(Product, CLIENT_ID) is None:
            session.add(Product(id=CLIENT_ID, name="Loady", domain="loady.cc", status="live"))
            session.flush()
        for slug in _LOADY_PLANS:
            entitlement_service.get_or_create_plan(session, CLIENT_ID, slug, slug.title())

        if session.get(OAuthClient, CLIENT_ID) is not None:
            print(f"{CLIENT_ID}: already registered - client_secret was only ever shown once at registration time.")
            session.commit()
            return

        _client, secret = oidc_service.register_client(
            session, actor, CLIENT_ID, "Loady", CLIENT_ID, [args.redirect_uri]
        )
        session.commit()
        print(f"{CLIENT_ID}: registered.")
        print(f"  PLATFORM_CLIENT_ID={CLIENT_ID}")
        print(f"  PLATFORM_CLIENT_SECRET={secret}")
        print("  (paste into local-media-downloader/backend/.env)")
    finally:
        session.close()


if __name__ == "__main__":
    main()
