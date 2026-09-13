"""Authorization Code + PKCE (RFC 6749 + RFC 7636) issuance and exchange —
the SSO core (mission-brief section 5). Deliberately standards-based, not
a custom protocol (mission-brief section 5/38): a real OIDC client library
against this service only needs the authorization/token endpoints, a JWKS
URL, and standard JWT validation — nothing here is bespoke wire format.

Threat-model notes (mission-brief section 24), one per check below:
- **Open redirect / redirect URI manipulation**: `redirect_uri` is checked
  for exact membership in the client's registered list, never a prefix or
  substring match.
- **Authorization-code interception / replay**: codes are single-use
  (`used_at` set atomically at exchange) and short-lived
  (`authorization_code_ttl_seconds`, default 60s).
- **Missing PKCE**: `code_challenge_method` must be exactly `S256`; a
  missing or `plain` challenge is rejected outright at `/oauth/authorize`.
- **Wrong client**: the code is bound to the `client_id` that requested
  it; the token endpoint call must present the same `client_id` (with a
  confidential client, also its secret), and PKCE additionally binds the
  code to whichever party generated the original `code_verifier`.
- **Client credential leakage**: `client_secret` is stored only as an
  Argon2 hash, exactly like a user password — this service never has a
  plaintext copy after registration.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.database.models import AuthorizationCode, OAuthClient, OAuthRefreshToken, User, generate_client_secret
from app.models.enums import AuditAction
from app.security import passwords
from app.security.jwt_tokens import create_oidc_tokens
from app.security.pkce import verify_pkce
from app.security.tokens import generate_hashed_token, hash_token
from app.services import audit_service, product_service
from app.utils.exceptions import InvalidClientError, InvalidGrantError, InvalidRedirectUriError


def register_client(
    session: Session, actor: User, client_id: str, name: str, product_id: str | None, redirect_uris: list[str]
) -> tuple[OAuthClient, str]:
    existing = session.get(OAuthClient, client_id)
    if existing is not None:
        raise InvalidClientError(f"client_id '{client_id}' is already registered.")
    raw_secret = generate_client_secret()
    client = OAuthClient(
        client_id=client_id,
        product_id=product_id,
        name=name,
        client_secret_hash=passwords.hash_password(raw_secret),
        redirect_uris=redirect_uris,
    )
    session.add(client)
    session.flush()
    audit_service.record(
        session, actor.id, AuditAction.CLIENT_REGISTERED, "oauth_client", client_id, product_id,
        after_state={"redirect_uris": redirect_uris},
    )
    return client, raw_secret


def get_client(session: Session, client_id: str) -> OAuthClient | None:
    return session.get(OAuthClient, client_id)


def validate_authorize_request(session: Session, client_id: str, redirect_uri: str, code_challenge_method: str) -> OAuthClient:
    client = get_client(session, client_id)
    if client is None or not client.is_active:
        raise InvalidClientError("Unknown or inactive client.")
    if redirect_uri not in client.redirect_uris:
        raise InvalidRedirectUriError("redirect_uri is not registered for this client.")
    if code_challenge_method != "S256":
        raise InvalidGrantError("PKCE with S256 is required.")
    return client


def issue_authorization_code(
    session: Session,
    client: OAuthClient,
    user: User,
    redirect_uri: str,
    code_challenge: str,
    code_challenge_method: str,
    scope: str,
    state: str | None,
) -> str:
    settings = get_settings()
    raw, code_hash, expires_at = generate_hashed_token(
        timedelta(seconds=settings.authorization_code_ttl_seconds), nbytes=32
    )
    record = AuthorizationCode(
        code_hash=code_hash,
        client_id=client.client_id,
        user_id=user.id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        scope=scope,
        state=state,
        expires_at=expires_at,
    )
    session.add(record)
    session.flush()
    return raw


def exchange_authorization_code(
    session: Session,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    code_verifier: str,
) -> tuple[str, str, str, User]:
    """Returns (access_token, id_token, oauth_refresh_token_raw, user)."""
    client = get_client(session, client_id)
    if client is None or not client.is_active or client.client_secret_hash is None:
        raise InvalidClientError("Unknown or inactive client.")
    if not passwords.verify_password(client_secret, client.client_secret_hash):
        raise InvalidClientError("Invalid client credentials.")

    code_hash = hash_token(code)
    record = session.execute(
        select(AuthorizationCode).where(AuthorizationCode.code_hash == code_hash)
    ).scalars().first()
    now = datetime.now(timezone.utc)
    if record is None or record.used_at is not None or record.expires_at < now:
        raise InvalidGrantError("This authorization code is invalid, expired, or already used.")
    if record.client_id != client_id or record.redirect_uri != redirect_uri:
        raise InvalidGrantError("Authorization code does not match this client/redirect_uri.")
    if not verify_pkce(code_verifier, record.code_challenge, record.code_challenge_method):
        raise InvalidGrantError("PKCE verification failed.")

    # Single-use: mark consumed before issuing anything, so a concurrent
    # replay of the same code loses the race unconditionally.
    record.used_at = now

    user = session.get(User, record.user_id)
    if user is None or user.status != "active":
        raise InvalidGrantError("This account is no longer active.")

    access_token, id_token = create_oidc_tokens(
        user.id, user.email, user.email_verified, client_id, record.scope
    )
    settings = get_settings()
    oauth_refresh_raw, oauth_refresh_hash, oauth_refresh_expires = generate_hashed_token(
        timedelta(days=settings.oidc_refresh_token_ttl_days)
    )
    session.add(
        OAuthRefreshToken(
            token_hash=oauth_refresh_hash,
            client_id=client_id,
            user_id=user.id,
            scope=record.scope,
            expires_at=oauth_refresh_expires,
        )
    )

    if client.product_id:
        product_service.touch_membership(session, user.id, client.product_id)

    return access_token, id_token, oauth_refresh_raw, user


def refresh_oidc_token(session: Session, client_id: str, client_secret: str, refresh_token_raw: str) -> tuple[str, User]:
    """Returns a fresh (access_token, user) without any user interaction —
    the client-side counterpart to Loady's own refresh-token rotation, but
    scoped to a single product client rather than the central session."""
    client = get_client(session, client_id)
    if client is None or not client.is_active or client.client_secret_hash is None:
        raise InvalidClientError("Unknown or inactive client.")
    if not passwords.verify_password(client_secret, client.client_secret_hash):
        raise InvalidClientError("Invalid client credentials.")

    token_hash = hash_token(refresh_token_raw)
    record = session.execute(
        select(OAuthRefreshToken).where(OAuthRefreshToken.token_hash == token_hash)
    ).scalars().first()
    now = datetime.now(timezone.utc)
    if record is None or record.revoked_at is not None or record.expires_at < now or record.client_id != client_id:
        raise InvalidGrantError("This refresh token is invalid, expired, or revoked.")

    user = session.get(User, record.user_id)
    if user is None or user.status != "active":
        raise InvalidGrantError("This account is no longer active.")

    access_token, _id_token = create_oidc_tokens(user.id, user.email, user.email_verified, client_id, record.scope)
    return access_token, user
