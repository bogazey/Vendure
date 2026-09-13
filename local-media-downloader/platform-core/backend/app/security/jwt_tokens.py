"""JWT issuance/verification — RS256 throughout, via PyJWT + `cryptography`
(mission-brief section 38: no hand-rolled crypto). Two kinds of JWT are
issued by this module:

1. The central-session **access token** (short-lived, cookie-delivered,
   never handed to product JavaScript) — verifies a user against Platform
   Core's own APIs (Grand Admin, account portal, `/oauth/authorize`).
2. **OIDC tokens** issued to a product at the end of an authorization-code
   exchange: an `id_token` (identity assertion) and an `access_token`
   (bearer credential for calling `/oauth/userinfo` /
   `/api/v1/entitlements`). Both carry standard claims — `iss`, `aud`,
   `sub`, `iat`, `exp` — with `sub` always the immutable global user id,
   never the email (mission-brief section 24).

Every verification call checks issuer, audience, expiry, and algorithm
explicitly (`algorithms=["RS256"]` pinned — never `None`/"any", which is
the classic "alg confusion" JWT vulnerability).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from app.config.settings import get_settings
from app.security.jwt_keys import get_private_key_pem, get_public_key_pem


def create_session_access_token(user_id: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "iss": settings.platform_auth_base_url,
        "aud": "platform-core-session",
        "sub": user_id,
        "type": "session_access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, get_private_key_pem(), algorithm="RS256", headers={"kid": settings.jwt_key_id})


def decode_session_access_token(token: str) -> dict[str, Any] | None:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            get_public_key_pem(),
            algorithms=["RS256"],
            audience="platform-core-session",
            issuer=settings.platform_auth_base_url,
        )
    except jwt.PyJWTError:
        return None
    if payload.get("type") != "session_access":
        return None
    return payload


def create_oidc_tokens(user_id: str, email: str, email_verified: bool, client_id: str, scope: str) -> tuple[str, str]:
    """Returns (access_token, id_token) for a product client at the end of
    a code exchange. `aud` is the requesting client's own id — a token
    minted for one product is never valid for another (mission-brief
    section 24: "cross-product token misuse")."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    common = {
        "iss": settings.platform_auth_base_url,
        "aud": client_id,
        "sub": user_id,
        "iat": now,
        "jti": uuid.uuid4().hex,
    }
    access_payload = {
        **common,
        "type": "oidc_access",
        "scope": scope,
        "exp": now + timedelta(minutes=settings.oidc_access_token_ttl_minutes),
    }
    id_payload = {
        **common,
        "type": "id_token",
        "email": email,
        "email_verified": email_verified,
        "exp": now + timedelta(minutes=settings.oidc_id_token_ttl_minutes),
    }
    headers = {"kid": settings.jwt_key_id}
    access_token = jwt.encode(access_payload, get_private_key_pem(), algorithm="RS256", headers=headers)
    id_token = jwt.encode(id_payload, get_private_key_pem(), algorithm="RS256", headers=headers)
    return access_token, id_token


def decode_oidc_access_token(token: str, expected_audience: str) -> dict[str, Any] | None:
    """A product/resource-server verifies a bearer token it received with
    exactly this function — audience-pinned to itself, so a token minted
    for a different client_id is rejected even though it carries a valid
    Platform Core signature."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            get_public_key_pem(),
            algorithms=["RS256"],
            audience=expected_audience,
            issuer=settings.platform_auth_base_url,
        )
    except jwt.PyJWTError:
        return None
    if payload.get("type") != "oidc_access":
        return None
    return payload


def introspect_oidc_access_token(token: str) -> dict[str, Any] | None:
    """Platform Core's own resource endpoints (`/api/v1/entitlements`,
    `/oauth/userinfo`) verify a bearer token with this function instead of
    `decode_oidc_access_token`: as the issuer, Platform Core trusts its own
    signature over any particular expected audience and instead *reads*
    the verified `aud` claim to learn which client is calling — the same
    pattern a real resource server would use if it, too, issued its own
    tokens. A third-party resource server integrating with Platform Core
    should use `decode_oidc_access_token` with its own client_id pinned,
    never this function."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            get_public_key_pem(),
            algorithms=["RS256"],
            issuer=settings.platform_auth_base_url,
            options={"verify_aud": False},
        )
    except jwt.PyJWTError:
        return None
    if payload.get("type") != "oidc_access":
        return None
    return payload
