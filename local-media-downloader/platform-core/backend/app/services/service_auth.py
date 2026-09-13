"""Service-to-service (client-credentials) authentication (mission-brief
Phases 36-37).

A registered `OAuthClient` may authenticate as *itself* (no end user
involved at all) once an admin has explicitly created one or more
`ServiceGrant` rows for it - a client with zero grants cannot obtain a
service token no matter how it authenticates (fails closed). Scopes are a
fixed, small, explicitly-enumerated set (`ALLOWED_SERVICE_SCOPES`) rather
than a free-text string a client could invent for itself - this is what
makes "a product server cannot grant itself plans or escalate roles"
(Phase 37) true structurally, not just by convention: there is no scope in
this set that grants a write capability over identity, roles, or
entitlements at all, only read access to a client's own product's data.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import OAuthClient, ServiceGrant, User
from app.models.enums import AuditAction
from app.security import passwords
from app.security.jwt_tokens import create_service_access_token
from app.services import audit_service
from app.utils.exceptions import InsufficientScopeError, InvalidClientError

# Deliberately read-only and product-scoped (Phase 37: no self-plan-grant,
# no role escalation, no cross-product reads without the caller's own
# product_id being the one asked about - enforced in the route layer by
# always scoping to `principal.client.product_id`, exactly like the
# existing `BearerPrincipal` pattern in `api/deps.py`).
ALLOWED_SERVICE_SCOPES = {
    "service:entitlements:read",
    "service:memberships:read",
}


def grant_scope(session: Session, admin: User, client: OAuthClient, scope: str) -> ServiceGrant:
    if scope not in ALLOWED_SERVICE_SCOPES:
        raise InsufficientScopeError(f"'{scope}' is not a recognized service scope.")
    existing = session.execute(
        select(ServiceGrant).where(ServiceGrant.client_id == client.client_id, ServiceGrant.scope == scope)
    ).scalars().first()
    if existing is not None:
        return existing
    grant = ServiceGrant(client_id=client.client_id, scope=scope)
    session.add(grant)
    session.flush()
    audit_service.record(
        session, admin.id, AuditAction.SERVICE_CLIENT_REGISTERED, "oauth_client", client.client_id,
        client.product_id, after_state={"scope": scope},
    )
    return grant


def list_scopes(session: Session, client_id: str) -> list[str]:
    rows = session.execute(select(ServiceGrant).where(ServiceGrant.client_id == client_id)).scalars().all()
    return [row.scope for row in rows]


def rotate_client_secret(session: Session, admin: User, client: OAuthClient) -> str:
    """Secret rotation (Phase 36): the old secret stops verifying the
    instant this commits - there is only ever one live `client_secret_hash`
    per client, so "rotate" is "replace," not "add a second valid secret"
    (a real production rollout would need a brief overlap window; V1
    keeps this simple and documents the limitation in SECURITY.md)."""
    from app.database.models import generate_client_secret

    raw_secret = generate_client_secret()
    client.client_secret_hash = passwords.hash_password(raw_secret)
    session.flush()
    audit_service.record(
        session, admin.id, AuditAction.SERVICE_CLIENT_SECRET_ROTATED, "oauth_client", client.client_id, client.product_id,
    )
    return raw_secret


def issue_service_token(session: Session, client_id: str, client_secret: str) -> tuple[str, list[str]]:
    client = session.get(OAuthClient, client_id)
    if client is None or not client.is_active or client.client_secret_hash is None:
        raise InvalidClientError("Unknown or inactive client.")
    if not passwords.verify_password(client_secret, client.client_secret_hash):
        raise InvalidClientError("Invalid client credentials.")
    scopes = list_scopes(session, client_id)
    if not scopes:
        raise InsufficientScopeError("This client has no service-level grants.")
    return create_service_access_token(client_id, scopes), scopes


def require_scope(granted_scopes: list[str], required: str) -> None:
    if required not in granted_scopes:
        raise InsufficientScopeError(f"This service token is missing required scope '{required}'.")
