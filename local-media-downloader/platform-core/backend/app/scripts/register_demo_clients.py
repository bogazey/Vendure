"""Local-development-only bootstrap: registers the two demo OIDC clients
(`demo-a`, `demo-b`) used by `platform-core/demo-product-a` and
`demo-product-b` to prove cross-product SSO (mission-brief section 30).

Idempotent: re-running after the clients already exist reports that and
does nothing further (client secrets are never stored in plaintext, so a
lost secret means re-registering under a new client_id, exactly like any
real OAuth provider).

Usage: python -m app.scripts.register_demo_clients
"""
from __future__ import annotations

import secrets

from sqlalchemy import select

from app.database.db import get_session_factory
from app.database.models import OAuthClient, Product, User
from app.security.passwords import hash_password
from app.services import entitlement_service, oidc_service

_DEMOS = [
    ("demo-a", "Demo Product A", "http://localhost:9301/auth/callback"),
    ("demo-b", "Demo Product B", "http://localhost:9302/auth/callback"),
]


def main() -> None:
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

        for client_id, name, redirect_uri in _DEMOS:
            if session.get(Product, client_id) is None:
                session.add(Product(id=client_id, name=name, domain=f"{client_id}.local", status="live"))
                session.flush()
            entitlement_service.get_or_create_plan(session, client_id, "pro", "Pro")

            if session.get(OAuthClient, client_id) is not None:
                print(f"{client_id}: already registered - client_secret was only ever shown once at registration time.")
                continue

            _client, secret = oidc_service.register_client(session, actor, client_id, name, client_id, [redirect_uri])
            session.commit()
            print(f"{client_id}: registered.")
            print(f"  DEMO_CLIENT_ID={client_id}")
            print(f"  DEMO_CLIENT_SECRET={secret}")
            print(f"  (paste into platform-core/{client_id.replace('demo-', 'demo-product-')}/backend/.env)")
    finally:
        session.close()


if __name__ == "__main__":
    main()
