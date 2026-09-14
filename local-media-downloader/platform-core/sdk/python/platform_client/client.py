"""`PlatformClient` - one instance per product backend process.

Every network-calling method accepts an optional `http_client` (an
`httpx.Client`) purely for testability (a test can inject a client
pointed at an in-process ASGI transport, or a stub) - production code
can simply omit it and a short-lived real `httpx.Client()` is used.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from jwt import PyJWKClient


@dataclass
class TokenSet:
    access_token: str
    id_token: str
    refresh_token: str | None
    expires_in: int


@dataclass
class PlatformUser:
    """The verified identity behind an ID token - `sub` is the immutable
    global_user_id, never the email (mission-brief section 4/24)."""

    sub: str
    email: str
    email_verified: bool


class PlatformClientError(RuntimeError):
    pass


class PlatformClient:
    def __init__(
        self,
        *,
        base_url: str,
        client_id: str,
        client_secret: str | None = None,
        redirect_uri: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self._jwks_client = PyJWKClient(f"{self.base_url}/.well-known/jwks.json")

    # --- Browser-facing half: build the redirect, nothing secret here ---

    def authorize_url(
        self, *, state: str, code_challenge: str, redirect_uri: str | None = None, scope: str = "openid profile"
    ) -> str:
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri or self.redirect_uri,
            "scope": scope,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{self.base_url}/oauth/authorize?{urlencode(params)}"

    # --- Server-only half: everything below needs client_secret or a bearer token ---

    def exchange_code(
        self, *, code: str, code_verifier: str, redirect_uri: str | None = None, http_client: httpx.Client | None = None
    ) -> TokenSet:
        if self.client_secret is None:
            raise PlatformClientError("exchange_code requires a client_secret - never call this from browser code.")
        client = http_client or httpx.Client()
        response = client.post(
            f"{self.base_url}/oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "redirect_uri": redirect_uri or self.redirect_uri,
                "code_verifier": code_verifier,
            },
            timeout=5,
        )
        response.raise_for_status()
        body = response.json()
        return TokenSet(
            access_token=body["access_token"], id_token=body["id_token"],
            refresh_token=body.get("refresh_token"), expires_in=body.get("expires_in", 0),
        )

    def verify_id_token(self, id_token: str) -> PlatformUser:
        """Signature/issuer/audience-verified - never decode an ID token
        without this (mission-brief section 24: audience pinning)."""
        signing_key = self._jwks_client.get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token, signing_key.key, algorithms=["RS256"], audience=self.client_id, issuer=self.base_url
        )
        return PlatformUser(sub=claims["sub"], email=claims["email"], email_verified=claims.get("email_verified", False))

    def get_my_entitlement(self, access_token: str, http_client: httpx.Client | None = None) -> dict[str, Any]:
        """Calls `GET /api/v1/entitlements/me` with the USER's own bearer
        access token - scoped by Platform Core to this client's own
        product_id, never another product's (see `SSO.md`)."""
        client = http_client or httpx.Client()
        response = client.get(
            f"{self.base_url}/api/v1/entitlements/me", headers={"Authorization": f"Bearer {access_token}"}, timeout=5
        )
        response.raise_for_status()
        return response.json()

    def get_service_token(self, http_client: httpx.Client | None = None) -> str:
        """Client-credentials grant (mission-brief Phase 36) - this
        product's backend authenticating as ITSELF, no end user involved.
        Requires this client to have been granted at least one
        `ServiceGrant` scope by a Platform Core admin first."""
        if self.client_secret is None:
            raise PlatformClientError("get_service_token requires a client_secret.")
        client = http_client or httpx.Client()
        response = client.post(
            f"{self.base_url}/oauth/token",
            data={"grant_type": "client_credentials", "client_id": self.client_id, "client_secret": self.client_secret},
            timeout=5,
        )
        response.raise_for_status()
        return response.json()["access_token"]

    def get_effective_entitlements(
        self, user_id: str, service_token: str, http_client: httpx.Client | None = None
    ) -> dict[str, Any]:
        """Calls `GET /api/v1/service/entitlements/{user_id}` - requires
        the `service:entitlements:read` scope. Returns the full
        multi-source-resolved capability map (`ENTITLEMENT_ENGINE.md`),
        not just a single plan slug."""
        client = http_client or httpx.Client()
        response = client.get(
            f"{self.base_url}/api/v1/service/entitlements/{user_id}",
            headers={"Authorization": f"Bearer {service_token}"}, timeout=5,
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def has_capability(effective_entitlements: dict[str, Any], key: str, *, at_least: int | None = None) -> bool:
        """A small, deliberately dumb helper over the raw capability map
        - `at_least` only makes sense for an integer capability, and `-1`
        (`capability_service.UNLIMITED`) always satisfies any `at_least`.
        Does not itself call the network - pass it the dict
        `get_effective_entitlements` already returned."""
        capabilities = effective_entitlements.get("capabilities", {})
        if key not in capabilities:
            return False
        value = capabilities[key]
        if isinstance(value, bool):
            return value
        if at_least is not None and isinstance(value, int):
            return value == -1 or value >= at_least
        return bool(value)
