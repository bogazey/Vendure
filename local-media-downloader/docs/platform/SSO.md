# Single Sign-On (OIDC-style Authorization Code + PKCE)

Standards-based, not a custom protocol (mission-brief sections 5/38): the
flow is RFC 6749 (OAuth 2.0 Authorization Code Grant) + RFC 7636 (PKCE),
with an `id_token` and `/oauth/userinfo`/`/.well-known/*` endpoints in the
shape OpenID Connect expects. A real OIDC client library only needs the
`authorization_endpoint`, `token_endpoint`, `jwks_uri`, and standard JWT
validation to integrate - nothing here is bespoke wire format.

## Conceptual flow (mission-brief section 5, realized exactly)

```text
User opens demo-b (any product)
        |
demo-b needs authentication -> GET /auth/login
        |
demo-b redirects to Platform Core: GET /oauth/authorize?...&code_challenge=...
        |
Platform Core: does the browser have a valid plat_session_access/refresh
cookie already?
   NO  -> redirect to the hosted /login page, user authenticates,
          browser is bounced back to the SAME /oauth/authorize URL
   YES -> skip straight through, no password re-entry
        |
Platform Core issues a single-use Authorization Code, redirects to
demo-b's redirect_uri?code=...&state=...
        |
demo-b's BACKEND (never its frontend) exchanges the code at
POST /oauth/token with its own client_secret + the PKCE code_verifier
        |
demo-b gets back {access_token, id_token, refresh_token}, verifies the
id_token's RS256 signature against Platform Core's own JWKS, and
establishes ITS OWN local session cookie
```

This is exactly what was built and proven live (see the "Live proof"
section below) - not a description of an aspirational design.

## Endpoints (`app/api/routes_oauth.py`, `routes_pages.py`)

| Endpoint | Purpose |
|---|---|
| `GET /oauth/authorize` | Browser-facing. Validates `client_id`/`redirect_uri`/PKCE, then either redirects to `/login` (no session) or issues a code and redirects to the client's `redirect_uri` (session present). |
| `GET /login`, `GET /signup` | The hosted central-identity pages (plain server-rendered HTML + vanilla JS - no SPA needed for two forms). Preserve the pending `?next=` authorize request across a login/signup detour. |
| `POST /oauth/token` | Server-to-server only. `grant_type=authorization_code` (the main exchange) or `grant_type=refresh_token` (silent renewal, no user interaction). |
| `GET /oauth/userinfo` | Bearer-authenticated. Returns `sub`/`email`/`email_verified` for the token's subject. |
| `GET /.well-known/jwks.json` | The public signing key, standard JWK Set format. Never contains private material - see `IDENTITY.md`'s "what products never receive". |
| `GET /.well-known/openid-configuration` | Standard OIDC discovery document. |

## Client registration (mission-brief section 25)

`OAuthClient` rows are registered per product/service - `client_id`,
`client_secret_hash` (Argon2, same as a user password, never stored
plaintext after registration), an exact-match `redirect_uris` allowlist,
and an optional `product_id`. There is no single shared API key across
products; each client's credential is independently revocable (set
`is_active=false` - no such endpoint exists yet in V1, but the column is
there and every check already reads it). Registration itself is
`require_super_admin`-only (`POST /api/v1/admin/clients`) or via the
local-dev-only `app/scripts/register_demo_clients.py` script used to
bootstrap `demo-a`/`demo-b` for this mission's own acceptance tests.

## PKCE, tokens, and keys

- **PKCE**: `S256` only - `plain` is never accepted
  (`app/security/pkce.py`). `/oauth/authorize` rejects any other
  `code_challenge_method` outright.
- **RS256 throughout** (`app/security/jwt_keys.py`,
  `app/security/jwt_tokens.py`) via PyJWT + the `cryptography` library -
  no hand-rolled crypto (mission-brief section 38). A 2048-bit RSA
  keypair is generated on first run if `data/jwt_signing_key.pem` doesn't
  exist yet (analogous to Loady's `SECRET_KEY` falling back to a randomly
  generated value, never a fixed "dev" constant); a real deployment should
  provision this file out of band instead.
- **Two kinds of JWT**: the central-session access token (`aud:
  "platform-core-session"`, verified by `decode_session_access_token`) and
  OIDC tokens minted to a specific client (`aud: <client_id>`, verified by
  `decode_oidc_access_token` when a *third-party resource server* is
  checking, or `introspect_oidc_access_token` when Platform Core's own
  `/api/v1/entitlements/me` is the one checking - see the docstring on
  that function for why the distinction matters). `iss`, `aud`, `sub`,
  `exp` are always present and always checked; `sub` is always the
  immutable global user id, never the email.

## Threat model (mission-brief section 24), one row per named threat

| Threat | Mitigation |
|---|---|
| Authorization-code interception | Single-use (`used_at` set atomically, before any token is issued - a concurrent replay loses the race), short-lived (60s default, `authorization_code_ttl_seconds`). |
| Missing PKCE | Not optional - `/oauth/authorize` requires `code_challenge_method=S256` or refuses the request outright. |
| CSRF / state | `state` is opaque to Platform Core, stored on the `AuthorizationCode` row and echoed back verbatim on the redirect to the client - the client is responsible for verifying it matches what it generated (demo-a/demo-b both do this: `app.py::auth_callback` checks `state == pkce_state`). |
| Open redirect | `redirect_uri` is checked for **exact** membership in the client's registered list, never a prefix/substring match (`oidc_service.validate_authorize_request`). A validation failure renders a local error page, **never** a redirect - so an unvalidated `redirect_uri` can never be used to bounce the browser anywhere. |
| Redirect URI manipulation | Same exact-match check as above. |
| Token leakage | Access/refresh tokens for the central session are httpOnly cookies, never in a URL or readable by JS; OIDC tokens are returned only in a same-origin-to-the-client-backend `POST /oauth/token` JSON body, never as a URL fragment/query param. |
| Refresh-token replay | Central-session refresh tokens rotate on every use (old one revoked, new one issued) - Loady's exact pattern. OIDC refresh tokens are scoped to one `client_id` and can't be replayed against another client. |
| Session fixation | A new session is always issued fresh on login/signup; nothing accepts a pre-existing session id from the client. |
| Weak signing keys | RS256 with a 2048-bit key via `cryptography`, never HS256 with a guessable/short secret for anything cross-service. |
| Cross-product token misuse | `aud` is the requesting client's own id - a token minted for `demo-a` fails `decode_oidc_access_token(token, expected_audience="demo-b")` even though the signature itself is valid (`tests/test_sso.py::test_access_token_audience_is_pinned_to_client`). |

## Service-to-service auth (mission-brief section 25)

A product's *backend* authenticates to Platform Core with its own
`client_id`/`client_secret` at the token endpoint - never a shared secret,
never committed to git (`demo-product-a/backend/.env.example` /
`.env` - the latter is gitignored, see `LOCAL_DEVELOPMENT.md`). Calling
`/api/v1/entitlements/me` afterward uses the bearer access token, which
itself encodes which client is calling (`aud`) - Platform Core never has
to be told "I am demo-a" out of band on that call; the token proves it.

## Live proof (not a description of intended behavior - what was actually run)

1. **Cross-process, real network, no mocks**
   (`tests/test_cross_product.py`, and independently re-verified against
   three separately running `uvicorn` processes on ports 8100/9301/9302
   with a plain `httpx` script following real redirects): one signup, two
   independent OIDC exchanges, one `sub` shared by both, `/api/v1/
   entitlements/me` correctly isolated per product.
2. **A real Chromium browser** (Playwright, the environment's
   pre-installed browser at `/opt/pw-browsers/chromium`): opened
   demo-a signed out, clicked through to the hosted `/signup` page,
   created an account, landed back on demo-a's dashboard with the correct
   `sub`, then opened demo-b in the **same** browser context and reached
   its dashboard with **zero** further authentication - true silent SSO,
   the same `sub` both places, no second account created. Screenshots
   were sent alongside this mission's report.
3. **Grand Admin, same live stack**: signed in as a real `super_admin`
   account, granted a gifted entitlement to the browser-test user via the
   real `PATCH /api/v1/admin/users/{id}/entitlements` endpoint, and
   confirmed - in the same browser session, against the same running
   Platform Core - that Gifted Access, Audit Log, and Users search all
   reflected it immediately.

### A bug the browser found

The first browser run failed: after signup, the page redirected to
Platform Core's bare `/` (a 404) instead of back through
`/oauth/authorize`. Root cause: `routes_pages.py`'s `/login` and `/signup`
pages embedded the validated `next` path into an `<a href="/signup?next=
{next}">` switch-link using `html.escape()` - which escapes `<`/`>`/`"`
for HTML safety but does **not** URL-encode `&`/`=`/`?`. Since `next`
itself is a full query string
(`/oauth/authorize?response_type=code&client_id=...&code_challenge=...`),
the raw `&` characters were reparsed by the browser as *this page's own*
query string, silently truncating `next` down to just
`/oauth/authorize?response_type=code` by the time the user reached
`/signup`. A network-level `httpx` test never caught this because it
never renders the HTML or resolves relative links the way a browser does.

Fixed by using `urllib.parse.quote()` for the `href` embedding and
`json.dumps()` for the inline-`<script>` JS-string embedding - two
different escaping rules for two different embedding contexts, now with a
regression test (`tests/test_pages.py`) that specifically asserts the
`next` value round-trips through the switch-link unmutated. This is
exactly the kind of bug the mission's "run the SSO flow through a real
browser, don't just claim it" instruction exists to catch.
