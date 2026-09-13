"""Loady's OIDC *client* adapter against Platform Core's central identity
(docs/platform/LOADY_IDENTITY_INTEGRATION.md). Same real Authorization
Code + PKCE flow already proven end-to-end with demo-product-a/b
(platform-core/demo-product-a/backend/app.py) - this module is Loady's
own copy of that pattern, not a new protocol.

Dormant by default: every function here is only ever called from
`routes_platform_auth.py`, and that router's own endpoints refuse to do
anything (see `_require_configured`) unless `PLATFORM_CLIENT_ID` is set -
so simply not setting it (the default) leaves Loady's existing
authentication completely unaffected, in any environment, including
production, until a deliberate separate decision configures it.
"""
from __future__ import annotations

import base64
import hashlib
import secrets

import httpx
import jwt

from app.config.commercial_settings import get_commercial_settings
from app.config.logging_config import get_logger
from app.utils.exceptions import InvalidTokenError

logger = get_logger("platform_identity")

_jwks_cache: dict | None = None


def is_configured() -> bool:
    settings = get_commercial_settings()
    return bool(settings.platform_client_id and settings.platform_client_secret.get_secret_value())


def _server_base_url() -> str:
    """The base URL Loady's own backend actually connects to for a
    server-to-server call (token exchange, JWKS fetch) - PLATFORM_INTERNAL_BASE_URL
    when set (e.g. a private docker-network address in staging), otherwise
    the same externally reachable platform_auth_base_url used for the
    browser redirect and the id_token issuer check."""
    settings = get_commercial_settings()
    return settings.platform_internal_base_url or settings.platform_auth_base_url


def generate_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:64]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def generate_state() -> str:
    return secrets.token_urlsafe(24)


def build_authorize_url(code_challenge: str, state: str) -> str:
    settings = get_commercial_settings()
    from urllib.parse import urlencode

    params = {
        "response_type": "code",
        "client_id": settings.platform_client_id,
        "redirect_uri": settings.platform_redirect_uri,
        "scope": "openid profile",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{settings.platform_auth_base_url}/oauth/authorize?{urlencode(params)}"


def exchange_code_for_tokens(code: str, code_verifier: str) -> dict:
    """Server-side only - never called from, or exposed to, the browser.
    Raises InvalidTokenError on any failure rather than leaking Platform
    Core's raw error body to the caller."""
    settings = get_commercial_settings()
    try:
        response = httpx.post(
            f"{_server_base_url()}/oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": settings.platform_client_id,
                "client_secret": settings.platform_client_secret.get_secret_value(),
                "code": code,
                "redirect_uri": settings.platform_redirect_uri,
                "code_verifier": code_verifier,
            },
            timeout=10,
        )
    except httpx.HTTPError as exc:
        logger.warning("Platform Core token exchange failed (network): %s", exc)
        raise InvalidTokenError("Could not reach the central identity service.")

    if response.status_code != 200:
        logger.warning("Platform Core token exchange rejected: %s", response.status_code)
        raise InvalidTokenError("Central identity sign-in failed.")
    return response.json()


def _get_jwks() -> dict:
    global _jwks_cache
    if _jwks_cache is None:
        response = httpx.get(f"{_server_base_url()}/.well-known/jwks.json", timeout=10)
        response.raise_for_status()
        _jwks_cache = response.json()
    return _jwks_cache


def verify_id_token(id_token: str) -> dict:
    """Full verification: RS256 signature via Platform Core's own JWKS,
    issuer, audience (Loady's own client_id - never any other product's),
    and expiry. Raises InvalidTokenError on any failure - never returns a
    partially-trusted payload."""
    settings = get_commercial_settings()
    try:
        unverified_header = jwt.get_unverified_header(id_token)
        jwks = _get_jwks()
        key_data = next((k for k in jwks["keys"] if k["kid"] == unverified_header.get("kid")), None)
        if key_data is None:
            raise InvalidTokenError("Unknown signing key.")
        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key_data)
        claims = jwt.decode(
            id_token, public_key, algorithms=["RS256"],
            audience=settings.platform_client_id, issuer=settings.platform_auth_base_url,
        )
    except jwt.PyJWTError as exc:
        logger.warning("Platform Core id_token verification failed: %s", exc)
        raise InvalidTokenError("Central identity token verification failed.")
    return claims
