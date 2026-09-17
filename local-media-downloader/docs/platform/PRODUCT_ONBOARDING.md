# Product Onboarding (Phased Procedure)

Mission 17 (multi-product expansion prep). This is the phase-gated
procedure a future "connect Gamey to Platform Core" request should follow
end to end, without reverse-engineering how Loady or the demo products
were wired up. It **supersedes** `NEW_PRODUCT_ONBOARDING.md` as the
authoritative onboarding reference — that document remains for its
specific historical evidence (it records exactly what
`test_live_server_onboarding.py` and `test_register_product_cli.py`
proved against a real running instance in Mission 6) but this document is
what to actually follow. Every command below is real and already exists;
nothing in this document describes work that still needs to be built.

**Explicit non-goal**: this document does not itself onboard Gamey,
Filey, or any other real product. Following it is future work, gated on
separate approval per the standing production-safety rule (see
`PRODUCTION_SAFETY.md`-equivalent constraints in the mission brief this
document was written under).

## Phase A — Register the product

```bash
python -m app.scripts.platform_cli product create \
  --slug gamey --name "Gamey" --domain gamey.example \
  --redirect-uri https://gamey.example/auth/callback \
  [--redirect-uri https://gamey.example/auth/callback2 ...] \
  [--free-plan-name Free]
```

Creates the `Product` row (`status=live`, `is_active=true` by default),
an initial `free` `Plan`, and a registered `OAuthClient`
(`client_id = "<slug>-client"`). **The client secret is printed to
stdout exactly once** — store it immediately; there is no endpoint or
CLI command that can ever retrieve it again (only rotate it, which
invalidates the old one).

Alternative: the Grand Admin UI's "Add Product" flow
(`POST /api/v1/admin/products/onboard`, super_admin only) does the same
two things (product + first client) in one authenticated web action
instead of a CLI run against the production host.

Idempotency: re-running `product create` with the same `--slug` fails
loudly (`AppError`, exit code 1) rather than silently creating a partial
second registration.

## Phase B — OAuth client configuration

If the product needs more than one client (e.g. a web app and a mobile
app), or needs to change its redirect URIs after creation, register an
additional client or contact a super_admin to add redirect URIs at
registration time — redirect URIs are not currently independently
patchable after client creation; get the full list right at Phase A/B,
or register a second client with a corrected list rather than editing.

```bash
python -m app.scripts.platform_cli oauth-client create \
  --client-id gamey-mobile --name "Gamey Mobile" \
  --product gamey --redirect-uri gamey://auth/callback
```

If the product needs RP-Initiated Logout (recommended — see
`PRODUCT_INTEGRATION_CONTRACT.md` §Logout), register its post-logout
redirect target(s) via the admin API (no CLI wrapper yet — see
"Known limitations" below):

```bash
curl -X POST https://id.<platform-domain>/api/v1/admin/clients/gamey-client/post-logout-redirect-uris \
  -H "Content-Type: application/json" --cookie <admin-session-cookie> \
  -d '{"post_logout_redirect_uris": ["https://gamey.example/logged-out"]}'
```

## Phase C — Product environment

Every downstream product needs exactly these values, and nothing else,
to integrate (see `PRODUCT_INTEGRATION_CONTRACT.md` for what each is
used for):

| Value | Source |
|---|---|
| `PLATFORM_ISSUER` | Platform Core's `PLATFORM_AUTH_BASE_URL` (e.g. `https://id.loady.cc`) |
| `PLATFORM_CLIENT_ID` | The `client_id` from Phase A/B |
| `PLATFORM_CLIENT_SECRET` | The secret printed once in Phase A/B |
| `PLATFORM_REDIRECT_URI` | Exactly one of the URIs registered in Phase A/B |
| `PLATFORM_JWKS_URL` | `<PLATFORM_ISSUER>/.well-known/jwks.json` (public, no secret) |

No product needs its own copy of `WEBHOOK_SECRET_ENCRYPTION_KEY` or any
other Platform Core internal secret — those stay entirely on the
Platform Core side. If the product opts into outbound webhooks (Phase F
below), Platform Core generates and shows that product's webhook signing
secret once, separately, at `POST /clients/{id}/webhook` time.

## Phase D — Auth integration

Implement (or reuse, see below) the standard OIDC Authorization Code +
PKCE flow against the contract in `PRODUCT_INTEGRATION_CONTRACT.md`.
Two working reference implementations already exist in this repository:

- `platform-core/demo-product-a` / `demo-product-b` — hand-rolled Python
  (Flask-style) OIDC client: PKCE generation, `/auth/login`,
  `/auth/callback`, JWKS-based `PyJWKClient` verification, local session,
  `/logout`.
- `platform-core/sample-future-product-2` — the more idiomatic path,
  using the published SDKs: `platform_client.fastapi_ext.build_platform_router`
  (Python/FastAPI) and `@platform-core/react-client` (React), documented
  in `PRODUCT_SDK.md`. **This is the canonical reference integration** —
  prefer it over hand-rolling the flow demo-a/b show, unless the target
  product's stack genuinely cannot use either SDK.

## Phase E — Entitlement integration

Call `GET /api/v1/entitlements/me` with the product's own bearer access
token for the simple "is this user entitled" check, or
`get_service_token` + `GET /api/v1/service/entitlements/effective` for
the richer typed-capability view (`ENTITLEMENT_MODEL.md`
§"Effective entitlement resolution"). Gate features on capability
values (`capabilities["download.max_resolution"] >= N`), never on plan
slug string comparisons — this is what lets an admin introduce new plans
later with zero product-side code changes.

If the product has its own plan-specific capabilities (not just a flat
free/paid split), define them once via
`POST /api/v1/admin/products/{id}/capabilities` (no CLI yet — see
"Known limitations").

## Phase F — Admin integration (optional)

- Outbound webhooks (`entitlement.changed` events):
  `POST /api/v1/admin/clients/{client_id}/webhook` — see
  `PRODUCT_WEBHOOKS.md`.
- Service-to-service read scopes (a product's own backend reading its
  entitlements/memberships without a per-user token):
  `POST /api/v1/admin/clients/{client_id}/service-grants`.

## Phase G — Tests

At minimum, before calling a product "connected":

1. A real signup + login + authorization-code exchange against a real
   (not mocked) running Platform Core instance — `test_sso.py` and
   `sample-future-product-2`'s own tests are the pattern to copy.
2. Entitlement retrieval for a free-tier user (returns `free`) and a
   gifted/admin-granted user (returns the granted plan) — never assume a
   payment exists to test entitlement plumbing.
3. Disabled-user handling — a user whose `User.status != "active"` must
   be rejected at both the OIDC token exchange and the bearer-token
   resolution path (already covered generically by
   `test_sso.py`/`api/deps.py`, but re-verify for the new client).
4. RBAC isolation if the new product gets its own product-scoped admins
   — mirror `test_product_scoped_rbac.py`/`test_support_finance_rbac.py`'s
   structure exactly (see `RBAC_MATRIX.md`).

## Phase H — Staging

Run every step above against a Platform Core instance the new product's
own staging environment can actually reach, with real (non-production)
values in every row of the Phase C table. Confirm the product's own
staging login round-trips before touching production DNS/config.

## Phase I — Production activation

Only once H is fully green: register the production client
(Phase A/B, against the production Platform Core instance), roll the
production Phase C values into the product's own production
configuration, and flip Cloudflare/DNS/whatever the product's own
deployment needs — **entirely within that product's own infrastructure**,
never Platform Core's. Registering a new client never requires touching
Platform Core's own deployment, migrating any existing product's data, or
restarting Platform Core.

## Phase J — Rollback

- **Client-level, reversible, seconds**: disable the product's OAuth
  client(s) (`POST /api/v1/admin/clients/{id}/active` with
  `is_active: false`, or `platform oauth-client disable --client-id ...`)
  — blocks new sign-in and token refresh through that client immediately,
  without touching the product's own database or any other product.
- **Product-level, reversible, seconds**: disable the whole product
  (`POST /api/v1/admin/products/{id}/active`, global-admin only) — blocks
  every one of that product's clients at once (see
  `PRODUCT_INTEGRATION_CONTRACT.md` §"Outage / fail-closed behavior" for
  what this looks like from the product's side).
- Neither action deletes any data, revokes already-issued access tokens
  before their natural expiry (bounded by `OIDC_ACCESS_TOKEN_TTL_MINUTES`,
  15 minutes by default), or affects any other product.

## Known limitations (stated plainly)

- No CLI for defining product-specific capabilities (Phase E) — direct
  API/service call only.
- No CLI for setting post-logout-redirect-URIs (Phase B) — direct admin
  API call only (`POST /clients/{id}/post-logout-redirect-uris`).
- No cloneable "starter repo" scaffold — `sample-future-product-2` is a
  reference to copy from, not a `git clone && rename` template generator.
- Redirect URIs cannot be edited on an existing client after creation
  (only a brand-new client can be registered with a corrected list).
