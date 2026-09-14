# Product SDK (`platform_client`)

`platform-core/sdk/python/platform_client/`. Mission-brief Phases 26-28.

## What it replaces

`platform-core/demo-product-a/backend/app.py` (and demo-product-b, an
identical copy) hand-rolled PKCE generation, the authorization redirect,
the token exchange, JWKS-based ID token verification, and the
entitlement lookup - about 90 lines a future product would otherwise
copy-paste and maintain independently. `platform_client.PlatformClient`
is that same logic, generalized into a reusable library. **The demo
products themselves were not refactored to use it** in this mission (see
"What is NOT built" below) - the SDK was instead proven against a brand
new product built for exactly that purpose (see
`NEW_PRODUCT_ONBOARDING.md`).

## API surface

```python
from platform_client import PlatformClient, generate_pkce_pair

client = PlatformClient(
    base_url="https://auth.example.com",
    client_id="my-product-client",
    client_secret="...",              # server-side only - never in browser code
    redirect_uri="https://my-product.example.com/auth/callback",
)

# Browser-facing half - no secret involved:
verifier, challenge = generate_pkce_pair()
url = client.authorize_url(state=state, code_challenge=challenge)

# Server-only half:
tokens = client.exchange_code(code=code, code_verifier=verifier)
user = client.verify_id_token(tokens.id_token)          # PlatformUser(sub, email, email_verified)
entitlement = client.get_my_entitlement(tokens.access_token)

service_token = client.get_service_token()               # client_credentials grant
effective = client.get_effective_entitlements(user.sub, service_token)
client.has_capability(effective, "download.max_resolution", at_least=720)
```

`fastapi_ext.py` adds two dependency factories on top of this:
`make_get_current_platform_user(session_lookup)` and
`make_require_capability(client, session_lookup, key, at_least=None)` -
`session_lookup` is supplied by the product itself, since this SDK
deliberately does not assume any particular session-storage mechanism
(mission-brief Phase 28: "respect existing secure-cookie architecture").

## What was actually verified

- **Unit tests** (`test_pkce_and_client_unit.py`, 10 tests, no network):
  PKCE math, that `authorize_url` never contains the client secret,
  that secret-requiring methods refuse to run without one, the
  boolean/integer/unlimited-sentinel rules of `has_capability`, and
  request-shape assertions against an `httpx.MockTransport`.
- **A full live-server integration test**
  (`test_live_server_onboarding.py`): starts the real Platform Core
  FastAPI app via `uvicorn` on a real local TCP port, then drives the
  entire flow as a real client would - signup, the real authorization
  redirect, a real token exchange, a **real** JWKS fetch and RS256
  signature verification (the one step that specifically needs a live
  server, since `PyJWKClient` makes its own HTTP request and cannot be
  redirected to an in-process ASGI transport), a real client-credentials
  service token, and a real effective-entitlement lookup. Run 4 times in
  this session with no flakes. See `NEW_PRODUCT_ONBOARDING.md` for what
  this proves about onboarding.

## What is NOT built

- **The demo products were not migrated onto this SDK.** They continue
  to hand-roll the same logic this SDK generalizes - refactoring them
  was judged higher-risk than building a fresh, purpose-built proof
  product, since the demo apps have no automated test coverage of their
  own to catch a regression from an in-place refactor within this
  session.
- **No React/browser package** (Phase 28's `AuthProvider`/
  `usePlatformUser`/`useEntitlements`/`RequireAuth`) - not started.
- **No token/entitlement caching** - every `PlatformClient` call that
  hits the network does so fresh; a real product would want to cache a
  service token for its TTL and/or cache `get_effective_entitlements`
  behind the short-TTL-plus-signed-invalidation scheme
  `ENTITLEMENT_ENGINE.md`'s "What is NOT built" section describes.
- **Not published anywhere** - `pyproject.toml` exists so the package is
  installable (`pip install -e platform-core/sdk/python`), but nothing
  was published to an internal or public package index.
