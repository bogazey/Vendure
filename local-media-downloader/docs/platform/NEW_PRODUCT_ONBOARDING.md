# New Product Onboarding

Mission-brief Phases 29-30, 53, 55. This is the real path exercised in
this mission, not a hypothetical one - every step below was executed by
`platform-core/sdk/python/tests/test_live_server_onboarding.py` and
`platform-core/backend/tests/test_register_product_cli.py` against a real
running Platform Core instance in this session.

## The shortest safe path (Phase 55)

1. **Register the product.**
   ```bash
   python -m app.scripts.register_product \
     --slug my-product --name "My Product" --domain my-product.example \
     --redirect-uri https://my-product.example/auth/callback
   ```
   Creates the `Product` row, an initial `free` `Plan`, and a registered
   `OAuthClient` with a generated `client_id`/`client_secret`. The secret
   is printed once, to stdout only - never logged, never stored in
   plaintext (see `app/scripts/register_product.py`'s docstring).
2. **Install the SDK**: `pip install -e platform-core/sdk/python` (or
   vendor it - it has two dependencies, `httpx` and `pyjwt[crypto]`).
3. **Configure the callback**: point your product's own `/auth/callback`
   route at `PlatformClient.exchange_code`.
4. **Authenticate users**: `PlatformClient.authorize_url` +
   `generate_pkce_pair` for the redirect; `exchange_code` +
   `verify_id_token` on the callback.
5. **Retrieve entitlements**: `get_my_entitlement` (user-facing, the
   product's own bearer token) for the simple case, or
   `get_service_token` + `get_effective_entitlements` (Phase 36/37,
   server-to-server) for the richer multi-source/typed-capability view.
6. **Protect a backend capability**: `PlatformClient.has_capability` on
   whatever `get_effective_entitlements` returned, or
   `fastapi_ext.make_require_capability` as a route dependency if the
   product is FastAPI-based.
7. **Verify local session**: the product's own session mechanism (this
   SDK does not prescribe one - see `PRODUCT_SDK.md`).
8. **Define product-specific capabilities** (optional, only once the
   product has more than a flat free/paid split):
   `capability_service.define_capability` +
   `capability_service.set_plan_entitlement` per plan (currently only
   reachable via direct service calls or the Grand Admin API
   `POST /api/v1/admin/products/{id}/capabilities` - no CLI/UI for this
   step yet, see "What is NOT built").
9. **Test it** - exactly as this mission did: sign up a real user, run
   the real authorization flow, verify the real JWKS-signed ID token.

## What this proves (Phase 53's actual bar)

Mission-brief Phase 53: *"If onboarding a new product still requires
extensive copy/paste changes across Platform Core source, the
architecture is not finished."* `register_product` and `PlatformClient`
together onboarded a synthetic "Sample Future Product" in
`test_live_server_onboarding.py` using **zero** product-specific code in
`platform-core/backend` - no new route, no new `if product_id ==
"sample-future-product"` branch anywhere. Every function used
(`product_service.create_product`, `entitlement_service.get_or_create_plan`,
`capability_service.define_capability`/`set_plan_entitlement`,
`oidc_service.register_client`, `service_auth.grant_scope`) is the exact
same generic function every other product (Loady included) goes through.

## What is NOT built (be precise about the bar not fully cleared)

- **No CLI/admin-UI step for defining capabilities** - step 8 above still
  requires either a direct Python call or the raw Grand Admin JSON API;
  `register_product` only creates the initial `free` plan with zero
  capabilities attached. A fuller CLI (`register_product --capability
  key:type:value ...`) would close this.
- **No "reference product template" repository/scaffold** (Phase 30) -
  what exists is a *test* that builds one in-memory
  (`sample_future_product` fixture in `test_live_server_onboarding.py`),
  not a cloneable starter project a real developer would `git clone`.
- **Loady itself was not re-onboarded through this path** - Loady's
  integration predates Mission 6 and uses its own hand-rolled client code
  from Mission 3/4, not this SDK. Migrating Loady onto `platform_client`
  is future work, not attempted here (and would touch Loady's own
  codebase, which this mission's Phase 56 rule keeps out of scope for
  anything resembling a production change).
- **No onboarding step for outbound webhooks** - a new product wanting to
  receive signed `entitlement.changed` events still needs a separate
  admin call (`POST /api/v1/admin/clients/{client_id}/webhook`, see
  `PRODUCT_WEBHOOKS.md`), not folded into `register_product`.
