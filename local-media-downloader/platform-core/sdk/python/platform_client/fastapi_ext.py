"""FastAPI integration helpers built on `PlatformClient` (mission-brief
Phase 27's `get_current_platform_user`/`require_capability` concepts).

Browser/server split (mission-brief Phase 26): everything in this module
runs on a product's *backend* only. A `PlatformClient` constructed with a
`client_secret` must never be reachable from code that ships to a
browser - nothing here changes that; it only adds FastAPI dependency
wiring on top of the already server-only `PlatformClient` methods.

Session storage is intentionally NOT this SDK's concern (Phase 28:
"respect existing secure-cookie architecture") - `session_lookup` is
supplied by the product itself, reading whatever cookie/session
mechanism it already has (exactly like `demo-product-a/backend/app.py`'s
own `_sessions` dict, or a real product's Redis/DB-backed session store).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from fastapi import HTTPException

from platform_client.client import PlatformClient, PlatformUser


@dataclass
class LocalSession:
    """The minimum shape a product's own session lookup must return -
    not a base class to inherit from, just the fields these dependencies
    need."""

    sub: str
    email: str
    email_verified: bool


def make_get_current_platform_user(session_lookup: Callable[[], LocalSession | None]):
    """Returns a FastAPI dependency: `user: PlatformUser = Depends(make_get_current_platform_user(...))`."""

    def _dependency() -> PlatformUser:
        session = session_lookup()
        if session is None:
            raise HTTPException(status_code=401, detail="Sign in required.")
        return PlatformUser(sub=session.sub, email=session.email, email_verified=session.email_verified)

    return _dependency


def make_require_capability(
    client: PlatformClient,
    session_lookup: Callable[[], LocalSession | None],
    key: str,
    *,
    at_least: int | None = None,
):
    """Returns a FastAPI dependency gating a route on one capability key
    via the service-auth path (mission-brief Phase 27). Fetches a fresh
    service token on every call in this reference implementation -
    caching it for its TTL is a product-side optimization deliberately
    left out of this minimal reference (Phase 55: "the shortest safe
    path," not the most optimized one)."""

    def _dependency() -> PlatformUser:
        session = session_lookup()
        if session is None:
            raise HTTPException(status_code=401, detail="Sign in required.")
        service_token = client.get_service_token()
        effective = client.get_effective_entitlements(session.sub, service_token)
        if not client.has_capability(effective, key, at_least=at_least):
            raise HTTPException(status_code=403, detail=f"Missing required capability '{key}'.")
        return PlatformUser(sub=session.sub, email=session.email, email_verified=session.email_verified)

    return _dependency
