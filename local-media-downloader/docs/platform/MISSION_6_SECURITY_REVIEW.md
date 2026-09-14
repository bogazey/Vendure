# Mission 6 Security Review

Scope: everything added in Mission 6 (capability/entitlement engine,
subscriptions, billing abstraction, webhook ingestion/replay, gifted
access v2, bundles, service-to-service auth, outbox/product webhooks, and
the new Grand Admin routes over all of it). V1 surfaces already covered
by `MISSION_5_SECURITY_REVIEW.md` are not re-audited here except where
Mission 6 code touches them.

Method: manual adversarial read of every new/changed file, focused on the
categories mission-brief Phase 50 lists (webhook replay, entitlement
spoofing, payment/gift separation, IDOR, scope escalation, RBAC, secret
leakage), each finding verified against the actual code, not assumed.
Findings below are separated into **fixed** (code changed, regression
test added, full suite re-run passing) and **documented limitation**
(real, but out of scope to fix safely in this mission or requires
infrastructure this mission does not have).

## Fixed

### 1. Unvalidated `(product_id, plan_slug)` passed to the billing provider

`POST /api/v1/billing/checkout` originally forwarded the caller's
`product_id`/`plan_id` straight into `provider.create_checkout` with no
check that the plan exists in Platform Core's own registry. Against
`FakeBillingProvider` this only produced a garbage checkout URL; against
a real provider, checkout amount must be resolved server-side from a
plan Platform Core recognizes, never client-supplied. Fixed: the route
now calls `entitlement_service.get_plan` first and 422s
(`INVALID_PLAN`) on an unknown plan, before any provider call.
Regression tests: `test_billing_checkout_rejects_a_plan_that_does_not_exist`,
`test_billing_checkout_succeeds_against_fake_provider_with_a_real_plan`.

### 2. Outbound webhook config had a schema but no admin API

`OAuthClient.webhook_url`/`webhook_signing_secret` existed as columns but
nothing could set them except direct DB access - meaning outbound
product webhooks (Phase 41) were architecturally present but
operationally dead. Fixed: `POST /api/v1/admin/clients/{client_id}/webhook`
(super-admin only, matches the existing client-registration privilege
level), generates a fresh random signing secret every call (shown once,
never re-retrievable, matching the existing client-secret/rotate-secret
precedent) and audits the change. Regression test:
`test_admin_can_configure_client_webhook_and_it_actually_delivers` - a
full round trip through the real HTTP route, then `deliver_pending`,
verifying the delivered signature.

## Reviewed and found correct (no change needed)

- **Webhook idempotency**: `BillingWebhookEvent(provider, provider_event_id)`
  is a DB-level UNIQUE constraint, not just an application check - the
  `IntegrityError`-catch path in `webhook_service.receive_webhook` was
  exercised with two real concurrent threads against the same SQLite file
  (`test_webhook_concurrency.py`), not just sequential calls, and produced
  exactly one journal row and one `Subscription` row every time (5
  repeated runs, no flakes).
- **Payment/gift separation**: `gift_service.py` has no import of
  `app.services.billing` anywhere - a gift structurally cannot create a
  `PaymentRecord`. Verified by `test_gift_never_creates_a_payment_record`.
  Replaying a `transaction.completed` webhook re-checks
  `(provider, provider_reference)` before inserting - verified by
  `test_transaction_completed_creates_payment_record_once`, which replays
  the same event and asserts the count stays at 1.
- **`custom_data` trust boundary**: a webhook's `custom_data` (used to
  resolve which `user_id`/`product_id`/`plan_slug` a brand-new
  subscription belongs to) is only ever trusted after
  `provider.verify_webhook` succeeds - i.e., it is authentic Paddle-
  echoed data, not a client-supplied header/body field on the inbound
  request. `routes_billing.create_checkout` (the only code that would, in
  a real integration, originate `custom_data`) takes `user_id` from the
  authenticated session (`get_current_user`), never from the request
  body - so a caller cannot inject a different `user_id` into their own
  checkout's `custom_data`.
- **Service-to-service scope escalation**: `ALLOWED_SERVICE_SCOPES` is a
  closed, hard-coded set with exactly two read-only scopes
  (`service:entitlements:read`, `service:memberships:read`) - there is no
  scope string a client could be granted that mutates a plan, role, or
  entitlement, so "a product server cannot grant itself plans or escalate
  roles" (Phase 37) holds structurally, not by convention. Verified by
  `test_unrecognized_scope_rejected` and
  `test_service_route_requires_correct_scope`.
- **Product isolation on service routes**: `/api/v1/service/*` always
  scopes to `principal.client.product_id` - there is no path/query
  parameter accepting a different product. Verified by
  `test_service_entitlements_route_is_scoped_to_callers_own_product`
  (a user with paid access in two products; the calling client only ever
  sees its own product's result).
- **Secret rotation**: `rotate_client_secret` replaces
  `client_secret_hash` in place; the old raw secret immediately stops
  verifying. Verified by `test_rotated_secret_invalidates_the_old_one`.
- **JWKS/JWT**: no changes to signing/verification logic; the new
  `service_access` token type reuses the same RS256 signer, pins
  `iss`, and is a distinct `type` claim from `session_access`/
  `oidc_access` so a service token can never be replayed against a
  user-facing route expecting one of those types (every existing
  decode function checks `payload.get("type")` explicitly).
- **RBAC on all new admin routes**: every new Grand Admin endpoint
  carries `require_global_admin` or `require_super_admin` (client/service-
  grant/webhook-config/secret-rotation endpoints use the stricter
  super-admin level, matching existing client-registration precedent).

## Documented limitations (not fixed - real, but out of scope here)

1. **Product-scoped admin (Phase 33/34) is not implemented for the new
   Mission 6 admin surface.** Every new admin route (`capabilities`,
   `gifts`, `bundles`, `subscriptions`, `payments`, `billing/webhooks`,
   `service-grants`) requires global admin/super-admin - there is no
   product-scoped ("a Loady admin can manage Loady's plans but not
   Gamey's") enforcement on any of it yet, even though the underlying
   `RoleAssignment(scope="product:<slug>")` primitive already exists from
   V1 and is reusable. Designing which of these operations should even be
   product-scopable (a global capability registry arguably shouldn't be
   product-admin-editable at all) needs its own design pass before being
   implemented - marked NOT DONE rather than half-built.
2. **Billing-webhook rate limiting is not signature-aware.**
   `billing_webhook_limiter` is keyed per-provider-name and applied before
   signature verification, so an attacker sending invalid-signature
   requests to `/api/v1/billing/webhooks/paddle` consumes the same budget
   a real Paddle retry burst would need. A real deployment should add
   Paddle's documented static webhook source-IP allowlist at the reverse
   proxy layer before going live; this mission does not have (and should
   not fabricate) that IP list.
3. **`OAuthClient.webhook_signing_secret` is stored in plaintext**, unlike
   every credential this codebase otherwise hashes - it must be, since
   Platform Core needs the raw value again to sign outgoing deliveries
   (unlike a login credential, which only ever needs to be verified, never
   re-produced). Needs a secrets manager (e.g., sealed/encrypted-at-rest
   column key) before any real deployment; explicitly out of scope for
   this mission's local/test architecture.
4. **Webhook-driven entitlement syncs attribute the audit actor as the
   affected user themselves**, not a distinct "system" principal, because
   `entitlement_service.grant_or_change`/`revoke` require a `User` actor
   and there is no system-principal concept in this schema yet
   (`subscription_service._sync_legacy_entitlement`). This is a real audit-
   trail precision gap for Phase 40 ("audit v2") to close, not a security
   hole (the affected user cannot forge this - it only ever fires from
   already-signature-verified webhook processing) - flagged for accuracy,
   not fixed.
5. **Paddle price-to-plan resolution is unimplemented (by design)** -
   `PaddleBillingProvider.create_checkout`/`get_subscription`/etc. all
   raise `BillingProviderNotConfiguredError`. This means the "amount
   charged must be resolved server-side from plan, never client-supplied"
   principle (finding #1 above) is asserted in code but not yet exercised
   against a real Paddle price catalog - correctly reported as UNTESTED
   against a live provider in the Mission 6 final report, not claimed as
   verified.
