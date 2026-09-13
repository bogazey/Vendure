"""Server-side, authoritative entitlement retrieval from Platform Core
(docs/platform/LOADY_IDENTITY_INTEGRATION.md).

SCOPING DECISION - read before wiring this into anything else: this
module is a proven CAPABILITY, not yet a replacement for Loady's existing
`entitlement_service`/`plan_policy`/`download_gate_service`, which
continue to gate every real download exactly as before. Swapping the live
gate to call Platform Core on every request is deliberately left as
future work (see LOADY_PRODUCTION_MIGRATION_PLAN.md's remaining
blockers) - it is a hot-path change with real availability risk (Platform
Core being briefly unreachable must never mean Loady's own paying users
can't download), and the mission this was built under explicitly
prioritizes not breaking existing behavior over completing every
architectural step in one pass. What IS proven here, with tests, is that
Loady's backend CAN correctly retrieve and validate the authoritative
entitlement server-side, never trusting anything the browser claims.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

from app.config.commercial_settings import get_commercial_settings
from app.config.logging_config import get_logger
from app.database.commercial_models import PlatformOidcToken, User

logger = get_logger("platform_entitlement")


def store_tokens(session: Session, user: User, access_token: str, refresh_token: str, expires_in: int) -> None:
    record = session.get(PlatformOidcToken, user.id)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    if record is None:
        record = PlatformOidcToken(
            user_id=user.id, refresh_token=refresh_token,
            access_token=access_token, access_token_expires_at=expires_at,
        )
        session.add(record)
    else:
        record.refresh_token = refresh_token
        record.access_token = access_token
        record.access_token_expires_at = expires_at


def _refresh_access_token(record: PlatformOidcToken) -> str | None:
    settings = get_commercial_settings()
    try:
        response = httpx.post(
            f"{settings.platform_auth_base_url}/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": settings.platform_client_id,
                "client_secret": settings.platform_client_secret.get_secret_value(),
                "refresh_token": record.refresh_token,
            },
            timeout=10,
        )
    except httpx.HTTPError as exc:
        logger.warning("Platform Core token refresh failed (network): %s", exc)
        return None
    if response.status_code != 200:
        logger.warning("Platform Core token refresh rejected: %s", response.status_code)
        return None
    body = response.json()
    record.access_token = body["access_token"]
    record.access_token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=body.get("expires_in", 900))
    return record.access_token


def get_authoritative_entitlement(session: Session, user: User) -> dict | None:
    """Returns Platform Core's authoritative view of this user's `loady`
    entitlement (`{"entitled": bool, "entitlement": {...} | None}`), or
    `None` if this account has no linked central-identity session at all
    (never yet signed in through Platform Core, or the integration isn't
    configured) - callers must treat `None` as "unknown," never as "not
    entitled."""
    settings = get_commercial_settings()
    if not settings.platform_client_id:
        return None

    record = session.get(PlatformOidcToken, user.id)
    if record is None:
        return None

    access_token = record.access_token
    now = datetime.now(timezone.utc)
    if not access_token or record.access_token_expires_at is None or record.access_token_expires_at <= now:
        access_token = _refresh_access_token(record)
        if access_token is None:
            return None

    try:
        response = httpx.get(
            f"{settings.platform_api_base_url}/api/v1/entitlements/me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
    except httpx.HTTPError as exc:
        logger.warning("Platform Core entitlement lookup failed (network): %s", exc)
        return None

    if response.status_code == 401:
        # The cached access token was rejected outright (e.g. Platform
        # Core restarted with a new signing key) - one retry after a
        # forced refresh, never a silent loop.
        access_token = _refresh_access_token(record)
        if access_token is None:
            return None
        try:
            response = httpx.get(
                f"{settings.platform_api_base_url}/api/v1/entitlements/me",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
        except httpx.HTTPError:
            return None

    if response.status_code != 200:
        logger.warning("Platform Core entitlement lookup returned %s", response.status_code)
        return None
    return response.json()
