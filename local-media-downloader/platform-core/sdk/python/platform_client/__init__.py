"""Platform Client - the reference server-side integration library for
products joining the ecosystem (mission-brief Phases 26-27).

This generalizes the hand-rolled OIDC client code that
`platform-core/demo-product-a/backend/app.py` (and demo-product-b) wrote
by hand: PKCE generation, the authorization redirect, the code exchange,
JWKS-based ID token verification, and entitlement lookup. A future
product should use this library instead of copying that file.

Server-only. Never import this into browser-shipped JavaScript, and
never construct a `PlatformClient` with a `client_secret` anywhere code
reaches a browser - see `fastapi_ext.py`'s module docstring for the
browser/server split.
"""
from __future__ import annotations

from platform_client.client import PlatformClient, PlatformUser, TokenSet
from platform_client.pkce import generate_pkce_pair

__all__ = ["PlatformClient", "PlatformUser", "TokenSet", "generate_pkce_pair"]
