# Platform Core V2 Architecture

Mission 6's additions to Platform Core, layered on top of the V1
identity/OIDC/RBAC/audit core documented in `ARCHITECTURE.md`,
`IDENTITY.md`, `SSO.md`, `ENTITLEMENTS.md`, `RBAC.md`. See
`V2_ARCHITECTURE_AUDIT.md` for the before-state this was built against,
and `MISSION_6_SECURITY_REVIEW.md` for the security review of everything
below.

## The layering principle

```text
V1 (unchanged behavior)              V2 (additive)
-----------------------              --------------
users, refresh_tokens                (untouched)
oauth_clients, authorization_codes   + ServiceGrant, webhook_url/secret
products, product_memberships        (untouched)
plans                                + entitlement_definitions,
                                        plan_entitlements
entitlements (single mutable row     + subscriptions, subscription_items
  per user+product, source-tagged)   + gifted_access (history)
                                      + bundles, bundle_product_plans,
                                        bundle_access
payment_records (flat)               + ledger columns (tax/fee/net/
                                        refunded/occurred_at/subscription_id)
roles, role_assignments              (untouched)
audit_logs                           (new AuditAction values only)
                                      + billing_webhook_events
                                      + outbox_events
```

Every V1 table keeps its exact V1 behavior. `entitlement_service.
get_active_entitlement` - the one function every existing product
integration calls - is untouched and still answers correctly for the
plain paid/free/gifted case, because every new write path
(`subscription_service`, `gift_service`) keeps it in sync as a fast-path
cache. Nothing new *replaces* it; `capability_service.
resolve_effective_entitlements` is a second, richer read path products
can adopt when they need typed capabilities or multi-source resolution
(paid + gifted + bundle simultaneously), not a required migration.

## New concepts, one paragraph each

- **Capability registry** (`EntitlementDefinition`/`PlanEntitlement`,
  Phases 5-6): a typed, product-scoped capability (boolean/integer/
  string/enum) with a value per plan. See `ENTITLEMENT_ENGINE.md`.
- **Effective entitlement engine** (`capability_service.
  resolve_effective_entitlements`, Phase 7): deterministic resolution
  across every simultaneous access source for a user+product, merging
  capability values with a documented per-type rule and preserving every
  contributing source for audit/history. See `ENTITLEMENT_ENGINE.md`.
- **Subscriptions** (`Subscription`/`SubscriptionItem`, Phase 8):
  provider-neutral recurring-access records, upserted by
  `subscription_service` from normalized webhook events.
- **Billing abstraction** (`app/services/billing`, Phase 9): a
  `BillingProvider` interface; `PaddleBillingProvider` implements only
  the network-free half (webhook verify/normalize); `FakeBillingProvider`
  is the fully-working local/test double. See `BILLING_ARCHITECTURE.md`.
- **Webhook ingestion** (`webhook_service`, Phase 10): DB-unique-
  constraint-backed idempotent processing + admin replay.
- **Payment ledger** (`PaymentRecord` + new columns, Phase 11): still the
  only table any revenue figure may be summed from; only a signature-
  verified `transaction.completed` event ever writes to it.
- **Gifted access v2** (`GiftedAccess`, Phase 13): a dedicated history
  table fixing V1's "re-gift overwrites the prior grant's detail"
  limitation, without changing the legacy cache's shape.
- **Bundles** (`Bundle`/`BundleProductPlan`/`BundleAccess`, Phases 15-16):
  cross-product access grants that expand through the effective
  entitlement engine. See `BUNDLES.md`.
- **Service-to-service auth** (`ServiceGrant` + OAuth `client_credentials`
  grant, Phases 36-37): a product backend authenticating as itself, with
  a closed, read-only scope set. See `SERVICE_AUTH.md`.
- **Outbox / product webhooks** (`OutboxEvent`, Phases 41-43): a DB-backed
  transactional outbox with HMAC-signed delivery. See
  `PRODUCT_WEBHOOKS.md`.

## What Mission 6 did NOT build (see the final report for the complete list)

Account-portal frontend (Phases 2-3, 17-25), the product SDK/client
library and FastAPI/React integration packages (Phases 26-28), the
product-onboarding CLI (Phase 29), the reference product-integration
template (Phase 30), Grand Admin V2's UI layer for any of this (the API
surface exists; no admin-frontend screens were built), product-scoped
RBAC enforcement on the new admin routes (Phase 33/34 - see the security
review), revenue metrics (Phase 12), promotions/trials as their own
model (Phase 14), the account-deletion lifecycle (Phase 39), and full
browser E2E (Phase 52-53) are all **not implemented** in this pass. Each
is either a large, mostly-independent surface (frontend/SDK/CLI) or
depends on the backend foundation this mission prioritized being correct
first.
