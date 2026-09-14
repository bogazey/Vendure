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

import httpx
from fastapi import APIRouter, HTTPException, Query, Response

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
    http_client: httpx.Client | None = None,
):
    """Returns a FastAPI dependency gating a route on one capability key
    via the service-auth path (mission-brief Phase 27). Fetches a fresh
    service token on every call in this reference implementation -
    caching it for its TTL is a product-side optimization deliberately
    left out of this minimal reference (Phase 55: "the shortest safe
    path," not the most optimized one).

    `http_client` is accepted (and threaded through to both underlying
    `PlatformClient` calls) so a product can supply one long-lived pooled
    `httpx.Client` across requests instead of a fresh one per call - and
    so this dependency is testable against a mock transport without any
    real network access.

    Service-outage behavior (explicitly required to be proven, not just
    implemented): if Platform Core itself is unreachable or errors while
    resolving the service token or the effective-entitlement lookup, this
    raises `503` - it never silently treats "I couldn't check" as "access
    granted," and never as "access denied" either (a `403` would
    incorrectly suggest the user's account lacks the capability, when the
    real cause is Platform Core being down)."""

    def _dependency() -> PlatformUser:
        session = session_lookup()
        if session is None:
            raise HTTPException(status_code=401, detail="Sign in required.")
        try:
            service_token = client.get_service_token(http_client=http_client)
            effective = client.get_effective_entitlements(session.sub, service_token, http_client=http_client)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=503, detail=f"Could not verify entitlements: Platform Core is unreachable ({type(exc).__name__}).")
        if not client.has_capability(effective, key, at_least=at_least):
            raise HTTPException(status_code=403, detail=f"Missing required capability '{key}'.")
        return PlatformUser(sub=session.sub, email=session.email, email_verified=session.email_verified)

    return _dependency


def build_platform_router(
    client: PlatformClient,
    session_lookup: Callable[[], LocalSession | None],
    *,
    product_id: str,
    logout: Callable[[], None] | None = None,
    http_client: httpx.Client | None = None,
) -> APIRouter:
    """Mission 6 continuation: the reference backend implementation of the
    contract `@platform-core/react-client` (`platform-core/sdk/react`)
    expects - `GET {prefix}/session`, `GET {prefix}/entitlements`, and
    `POST {prefix}/logout`. Mount with `app.include_router(build_platform_router(...), prefix="/api/platform")`.

    A product is never required to use this - it's a convenience so a new
    product's backend doesn't have to hand-write these three routes to
    match the React package's contract, exactly the same reasoning as the
    rest of this SDK generalizing `demo-product-a/backend/app.py`'s
    hand-rolled code. `session_lookup` and `logout` are the product's own
    concern, same as every other dependency in this module."""
    router = APIRouter()

    @router.get("/session")
    def get_session() -> dict:
        session = session_lookup()
        if session is None:
            raise HTTPException(status_code=401, detail="Sign in required.")
        return {"user": {"sub": session.sub, "email": session.email, "email_verified": session.email_verified}}

    @router.get("/entitlements")
    def get_entitlements(product_id_param: str | None = Query(default=None, alias="product_id")) -> dict:
        session = session_lookup()
        if session is None:
            raise HTTPException(status_code=401, detail="Sign in required.")
        requested_product_id = product_id_param or product_id
        try:
            service_token = client.get_service_token(http_client=http_client)
            effective = client.get_effective_entitlements(session.sub, service_token, http_client=http_client)
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=503, detail=f"Could not resolve entitlements: Platform Core is unreachable ({type(exc).__name__})."
            ) from exc
        primary = client.primary_source(effective)
        return {
            "product_id": requested_product_id,
            "plan_slug": primary["plan_slug"] if primary else None,
            # Platform Core's service-entitlements endpoint carries slugs,
            # not display names - a product wanting a friendlier label
            # should look it up from its own copy of the catalog, or from
            # `/api/v1/admin/catalog/...` if it's also a Grand Admin caller.
            "plan_name": None,
            "source": primary["kind"] if primary else None,
            "capabilities": effective.get("capabilities", {}),
        }

    @router.post("/logout", status_code=204)
    def post_logout() -> Response:
        if logout is not None:
            logout()
        return Response(status_code=204)

    return router
