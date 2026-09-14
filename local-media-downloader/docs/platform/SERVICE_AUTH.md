# Service-to-Service Authentication

`app/services/service_auth.py`, `app/api/routes_service.py`. Mission-brief
Phases 36-37.

## Why this exists

Before Mission 6, a product's *backend* had no way to call Platform Core
except by holding one of its own users' OIDC bearer tokens - there was no
concept of a product server authenticating as itself. This is the
client-credentials half of OAuth (RFC 6749 §4.4), the standards-based
choice mission-brief Phase 36 asked for ("keep secrets server-side,
support rotation").

## Fails closed by construction

```text
OAuthClient  (already exists from V1 - client_id + client_secret_hash)
  |
  +-- ServiceGrant (client_id, scope)   <- an admin must create at least one
```

A client with zero `ServiceGrant` rows cannot obtain a service token no
matter how correctly it authenticates - `issue_service_token` raises
`InsufficientScopeError` if `list_scopes` comes back empty. There is no
"default" or "implicit" scope.

## The scope set is closed and read-only

```python
ALLOWED_SERVICE_SCOPES = {
    "service:entitlements:read",
    "service:memberships:read",
}
```

This is the entire enforcement mechanism for mission-brief Phase 37's "a
product backend cannot grant itself plans or escalate roles": there is no
scope string in this set that authorizes a write to anything. Adding a
future write-capable service scope is a deliberate, reviewable code
change to this set, never a value an admin can type into a free-text
field.

## Token shape

`create_service_access_token` (`app/security/jwt_tokens.py`) mints an
RS256 JWT with `type="service_access"`, `aud=sub=client_id` (no end
user), `scope` = the space-joined granted scopes. `introspect_service_
access_token` verifies signature/issuer/type exactly like the existing
session/OIDC token functions - a service token can never be replayed
against a route expecting a session or OIDC token because those check
`type` explicitly too.

## Route wiring

```text
POST /oauth/token  grant_type=client_credentials, client_id, client_secret
  -> {access_token, token_type: Bearer, scope, expires_in}

GET /api/v1/service/entitlements/{user_id}   [service:entitlements:read]
GET /api/v1/service/memberships/{user_id}    [service:memberships:read]
```

Both routes are scoped to `principal.client.product_id` - there is no
parameter through which a service caller can ask about a different
product (verified by
`test_service_entitlements_route_is_scoped_to_callers_own_product`: a
user with paid access in two products, queried by product A's service
client, only ever returns product A's data).

## Secret rotation

`rotate_client_secret` / `POST /api/v1/admin/clients/{id}/rotate-secret`
(super-admin only) replaces `client_secret_hash` in place - there is only
ever one live secret per client (no overlap window in V1; see
`MISSION_6_SECURITY_REVIEW.md` for why this is an accepted V1
simplification). The old secret stops verifying the instant this
commits, verified by `test_rotated_secret_invalidates_the_old_one`.

## What is NOT built

- No mTLS option (the mission brief said client-credentials was
  sufficient for "the simplest strong option" in V1).
- No per-scope rate limiting or usage metering on service tokens.
- No admin UI for managing `ServiceGrant` rows (the API exists:
  `POST/GET /api/v1/admin/clients/{client_id}/service-grants`).
