# Bundles

`app/services/bundle_service.py`. Mission-brief Phases 15-16.

## Model

```text
bundles                    bundle_product_plans          bundle_access
  id                         id                             id
  slug (unique)               bundle_id -> bundles.id        user_id -> users.id
  name                        product_id -> products.id      bundle_id -> bundles.id
  status  active|archived     plan_id -> plans.id             source        paddle|gifted|internal|...
                               UNIQUE(bundle_id, product_id)   subscription_id (nullable)
                                                                status        active|expired|revoked
                                                                starts_at / expires_at
```

A bundle grants **at most one plan per product** (`UNIQUE(bundle_id,
product_id)` - a V1 simplification; a bundle wanting to grant two
different plans of the same product isn't a real scenario worth
modeling). No commercial pricing is attached to a bundle anywhere in this
schema - this is purely the access-grant architecture the mission brief
asked for ("do NOT create real commercial pricing unless configured").

## How a bundle actually grants access

`bundle_service` never writes to `Entitlement`, `Subscription`, or
`GiftedAccess` - it only manages `BundleAccess` rows. The *expansion*
into per-product capabilities happens entirely inside
`capability_service.resolve_effective_entitlements` (see
`ENTITLEMENT_ENGINE.md`): for every active `BundleAccess` a user holds,
it looks up that bundle's `BundleProductPlan` row for the specific
product being asked about and folds that plan's capabilities into the
merge, tagged as an `EffectiveSource(kind="bundle", ...)`.

This is what makes the Phase 16 lifecycle guarantee hold structurally,
not just by testing: since `bundle_service` has no code path that reads
or writes `Subscription`/`GiftedAccess`/`Entitlement` at all, there is no
way granting, upgrading, or expiring a bundle can touch an independent
per-product subscription or gift. Verified by
`test_bundles.py::test_bundle_expiry_does_not_touch_independent_subscription`
- a user with both a real paid `Entitlement` and an expiring
`BundleAccess` for the same product/plan keeps the paid one untouched
after `bundle_service.expire_bundle_accesses` runs.

## Lifecycle operations

- `create_bundle` / `add_product_plan` - admin-only setup.
- `grant_bundle_access(source, expires_at=None, subscription_id=None)` -
  idempotent per `(user, bundle)`: re-granting updates the existing row
  in place (same precedent as `entitlement_service.grant_or_change`),
  audited as a "changed" event when it reactivates/upgrades an existing
  row.
- `revoke_bundle_access` / `expire_bundle_accesses` (the latter a
  sweep, safe to call from anywhere - like
  `gift_service.sync_expired_gifts`, correctness never depends on it
  having run, since `resolve_effective_entitlements` independently checks
  `expires_at` at read time).

## What is NOT built

- No public bundle checkout/pricing UI (explicitly out of scope, per the
  mission brief).
- No `BundleVersion` concept (the mission brief said "if necessary" - V1
  plan/product membership within a bundle can only be changed by an
  admin editing `BundleProductPlan` directly; there is no versioned
  history of what a bundle used to include).
- No Grand Admin UI screen (the admin API exists:
  `GET/POST /api/v1/admin/bundles`, `POST .../products`,
  `POST /api/v1/admin/users/{id}/bundles/{bundle_id}/access`).
