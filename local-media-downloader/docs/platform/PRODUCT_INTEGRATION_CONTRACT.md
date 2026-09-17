# Standard Product OIDC Integration Contract

Mission 17. The fixed, documented contract every product integrates
against — a future product needs only the five values in
`PRODUCT_ONBOARDING.md` Phase C plus this document; it should never need
to read Platform Core's own source to figure out correct behavior.
Cross-references `SSO.md` (the original protocol writeup) and
`ENTITLEMENT_MODEL.md` rather than re-deriving them; this document's job
is to state the contract a product must honor, not re-explain the
mechanism.

## Flow: Authorization Code + PKCE (RFC 6749 §4.1 + RFC 7636)

1. Product generates a PKCE `code_verifier`/`code_challenge` pair (S256
   only — `plain` is rejected outright) and a random `state`.
2. Redirect the user to:
   ```
   GET {PLATFORM_ISSUER}/oauth/authorize
     ?response_type=code
     &client_id={PLATFORM_CLIENT_ID}
     &redirect_uri={PLATFORM_REDIRECT_URI}
     &scope=openid profile
     &state={state}
     &code_challenge={code_challenge}
     &code_challenge_method=S256
   ```
3. Platform Core redirects back to `redirect_uri` with `?code=...&state=...`
   (or, if the user has no central session, first to its own `/login`,
   then back to step 2 automatically).
4. Product's callback verifies `state` matches what it generated, then:
   ```
   POST {PLATFORM_ISSUER}/oauth/token
     grant_type=authorization_code
     client_id={PLATFORM_CLIENT_ID}
     client_secret={PLATFORM_CLIENT_SECRET}
     code={code}
     redirect_uri={PLATFORM_REDIRECT_URI}
     code_verifier={code_verifier}
   ```
   Returns `{access_token, id_token, refresh_token, token_type, expires_in}`.

## `state` and `nonce`

`state` is the product's own CSRF binding for the redirect — generate it,
store it (session/cookie), and reject the callback if it doesn't match.
Platform Core echoes `state` back unmodified; it never inspects or
validates its contents itself, so a missing/mismatched `state` check on
the product's side is a real product-side vulnerability, not one this
service closes for you. There is no separate `nonce` parameter in this
implementation (V1's `id_token` does not carry replay-protection nonces
beyond the authorization code's own single-use/short-TTL properties,
covered below) — do not assume `nonce` validation exists if porting from
a generic OIDC library's default configuration.

## JWKS / issuer / audience validation

- **Issuer**: `{PLATFORM_ISSUER}` exactly — verify against the `iss` claim
  in both the `id_token` and any resource token.
- **Audience**: the `aud` claim equals the product's own
  `PLATFORM_CLIENT_ID` — never accept a token whose `aud` is a different
  client, even if it validates signature-wise (a token minted for Gamey
  must never be accepted by Filey).
- **JWKS**: fetch `{PLATFORM_ISSUER}/.well-known/jwks.json`, cache with a
  reasonable TTL, and re-fetch on a `kid` miss (key rotation). Never
  hardcode a public key — RS256 signing keys are rotatable
  infrastructure-side without every product needing a config change.
- **Algorithm**: `RS256` only — reject any token asserting a different
  `alg`, including `none` (a standard JWT-library-level check; every
  reference client here uses `PyJWT`'s/the JS SDK's built-in algorithm
  allowlist rather than trusting the token's own `alg` header).

## Callback validation

- `redirect_uri` in the authorization request must be an **exact** match
  (not a prefix, not a wildcard) to one registered for the client at
  `PRODUCT_ONBOARDING.md` Phase A/B — Platform Core enforces this
  server-side (`InvalidRedirectUriError`, HTTP 400) regardless of what
  the product sends; a product cannot bypass this by constructing its own
  request differently.
- The authorization `code` is single-use and short-lived
  (`AUTHORIZATION_CODE_TTL_SECONDS`, default 60s) — a product must
  complete the exchange promptly and must not retry a `code` after a
  failed exchange (it will already be consumed or expired).

## Token lifetimes

| Token | Default TTL | Config |
|---|---|---|
| `access_token` (OIDC, per-user) | 15 minutes | `OIDC_ACCESS_TOKEN_TTL_MINUTES` |
| `refresh_token` (OIDC, per-user) | 30 days | `OIDC_REFRESH_TOKEN_TTL_DAYS` |
| `authorization code` | 60 seconds | `AUTHORIZATION_CODE_TTL_SECONDS` |
| service (`client_credentials`) access token | see `service_access_token_ttl_minutes` in `app/config/settings.py` | — |

A product should treat `access_token` as short-lived by design — refresh
proactively (or on 401) rather than caching it for its full nominal TTL,
since a disabled client/product/user invalidates it early regardless of
the token's own unexpired signature (see "Outage / fail-closed behavior"
below).

## Refresh rotation + reuse protection

`POST /oauth/token` with `grant_type=refresh_token` issues a fresh
`access_token` bound to the same client/user/scope. The refresh token
itself is stored only as a SHA-256 hash server-side (never plaintext,
mirroring every other token in this schema) and is rejected outright once
revoked or expired — there is currently no separate "one-time rotation
with reuse-detection" scheme layered on top of the OIDC refresh token the
way the *central session* refresh token (Loady/account-portal login) has;
treat a leaked OIDC refresh token as live until its natural TTL or an
explicit client-secret rotation, and store it with the same care as the
client secret itself.

## Central logout / logout-all

- **This product's own local session**: the product's own responsibility
  — Platform Core has no visibility into it.
- **Platform Core's central session** (the cookie set at
  `id.<platform-domain>` when the user authenticated): end it via
  `GET {PLATFORM_ISSUER}/oauth/logout` — a real navigation (not an XHR;
  it needs to reach the browser's cookie for that domain), optionally
  with `?client_id={PLATFORM_CLIENT_ID}&post_logout_redirect_uri={URI}`
  to send the user back afterward. `post_logout_redirect_uri` must be
  pre-registered (`PRODUCT_ONBOARDING.md` Phase B) — an unregistered one
  is rejected (HTTP 400, not a redirect to it) for the same open-redirect
  reason `redirect_uri` is validated at `/oauth/authorize`.
- **"Logout everywhere"**: the account portal's own "sign out all
  devices" (`POST /api/v1/auth/logout-all`) bumps `User.security_epoch`,
  which immediately invalidates every still-unexpired central `session_access`
  cookie across every product's silent-SSO check — it does **not**
  retroactively revoke already-issued per-product `access_token`s (those
  still expire naturally per the table above). A product wanting
  "logout-all takes effect immediately for me too" should keep its own
  access-token TTL short and re-validate against Platform Core rather
  than trusting a cached token for its full nominal lifetime.

## Disabled user handling

A `User.status != "active"` is rejected at every point that matters:
`/oauth/authorize` (redirects to login, which itself rejects a disabled
account's credentials), `/oauth/token` (`InvalidGrantError` on both
`authorization_code` and `refresh_token` grants — see
`oidc_service.exchange_authorization_code`/`refresh_oidc_token`), and
bearer-token resolution (`api/deps.py::get_bearer_principal` —
`AuthError`, "This account is no longer active"). A product does not need
to separately re-check `User.status` itself; it is structurally
impossible to obtain or refresh a token for a disabled account through
this service.

## Entitlement revalidation

Entitlement state can change between token refreshes (a subscription
lapses, a gift is revoked, an admin disables the account). A product
should re-fetch `GET /api/v1/entitlements/me` (or the effective-entitlement
service call) at a cadence appropriate to the feature being gated — never
cache an entitlement decision for the full session duration for anything
that materially matters (e.g. a paid download limit). See
`ENTITLEMENT_MODEL.md` for exactly what "active right now" means.

## Outage / fail-closed behavior

If Platform Core is unreachable (network partition, deploy in progress,
`/ready` failing) or a product/client has been administratively disabled:

- **New sign-in**: fails outright — `/oauth/authorize`/`/oauth/token`
  cannot succeed against an unreachable service by definition, and a
  disabled client/product returns `InvalidClientError` (HTTP 400)
  deliberately, not a silent bypass.
- **Already-authenticated users**: continue to work until their
  `access_token` naturally expires (15 minutes by default) — a product
  should design its own UX for "re-authentication temporarily
  unavailable" for that window, never invent a local fallback identity or
  grant entitlements without a valid, freshly-verified token.
- **This is fail-closed by construction, not by product-side discipline**:
  there is no code path in `oidc_service`/`api/deps.py` that grants a
  token, refreshes a token, or accepts a bearer token when the
  client/product is inactive or the user is disabled — a product cannot
  accidentally build a bypass by mishandling an error response, because
  there is no success response to mishandle in that case.

## What a product does NOT need

- A copy of any Platform Core signing key, database credential, or
  internal secret.
- Its own user table keyed by email — `global_user_id` (the OIDC `sub`
  claim) is the only identity key a product should persist; email is
  mutable and Platform Core reserves the right to change it without
  notice to any individual product.
- Custom protocol work — every step above is standard OIDC Authorization
  Code + PKCE against a real `/.well-known/openid-configuration`
  document; a generic, unmodified OIDC client library should work against
  this service (see `SSO.md` for the full discovery document contents).
