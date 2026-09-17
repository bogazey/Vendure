# Entitlement Model

Mission 17. Consolidates `ENTITLEMENTS.md` (the generic `Entitlement`
table + `get_active_entitlement`) and `ENTITLEMENT_ENGINE.md` (the typed
capability registry + multi-source resolution) into one reference for
"how does a product decide what a user can do," plus this mission's own
explicit invariant checks. Both source documents remain for their deeper
mechanism detail; this document is the single entry point.

## The core objects

```text
Plan               (product_id, slug) unique — "loady/free" ≠ "gamey/free"
PlanVersion        immutable published capability snapshot of a plan
Price              append-only; editing a price retires + recreates, never mutates in place
Entitlement        the generic access record — see below
PaymentRecord      the ONLY table ever summed into revenue (never Entitlement)
```

## `Entitlement` — one generic table, distinguished only by `source`

```text
entitlements
  id
  user_id      -> users.id       (the global user, never a per-product user record)
  product_id   -> products.id
  plan_id      -> plans.id       (product-scoped plan)
  source       free|paddle|gifted|promotion|trial|internal|lifetime|bundle
  status       active|expired|revoked
  starts_at / expires_at         (null expires_at = never expires)
  granted_by   -> users.id (nullable, which admin, for gifted/internal/promotion)
  reason       (nullable, admin note)
```

**`source` alone decides revenue eligibility.** `PaymentRecord` (not
`Entitlement`) is the only table Platform Core's revenue metrics ever sum
(`revenue_service.compute_metrics` queries `PaymentRecord`/`Subscription`/
`Price` exclusively, never `Entitlement`) — a `gifted`, `internal`, or
`promotion` entitlement structurally cannot inflate a revenue figure,
because the code path that computes revenue never reads the table those
sources live in. `tests/test_gifted_and_free_never_count_as_revenue` and
`test_metrics_scoped_by_product_never_leak_across_products` verify this
directly.

## The one function every product's simple case calls

```python
entitlement_service.get_active_entitlement(session, user_id, product_id) -> Entitlement | None
```

Structurally excludes wrong-product (scoped by `product_id` — a Loady
entitlement is invisible when asked about `product_id="gamey"`), expired
(`expires_at` checked against "now" on every call, never cached), and
revoked (`status != "active"`) rows. A product never queries a raw
`Entitlement` row directly — it calls `GET /api/v1/entitlements/me` with
its own bearer token, which is scoped server-side to the calling client's
own `product_id`; there is no parameter by which a product could ask
about another product's entitlement even if it wanted to.

## Effective entitlement resolution (the richer, typed case)

```python
capability_service.resolve_effective_entitlements(session, user_id, product_id, now=None)
  -> EffectiveEntitlementResult(product_id, capabilities: dict, sources: list[EffectiveSource])
```

For a product with more than a flat free/paid split, this merges every
currently-contributing grant from four independent sources — the legacy
`Entitlement` row, active `Subscription`s (including "entitled through
period end" on a `canceled`-but-not-yet-ended subscription),
`GiftedAccess`, and `BundleAccess` — into one typed capability map
(`boolean` capabilities OR together; numeric/enum capabilities take the
most generous contributing value). Every contributing source is retained
in `.sources` for audit/history, never collapsed down to just the winner.
See `ENTITLEMENT_ENGINE.md` for the full per-type merge table and the
capability registry (`entitlement_definitions`/`plan_entitlements`) that
makes a new capability a data change, never a code change.

## Grant / change / revoke

`entitlement_service.grant_or_change`/`revoke` are the implementation
behind Grand Admin's entitlement controls. A grant to a product a user is
already entitled in **updates the same row** — never a second active
entitlement per product — and is audited as `entitlement_changed` (or
`gifted_access_changed`) rather than a fresh grant when one already
existed; which audit action fires is decided purely by `source`
(`_GIFTED_SOURCES = {gifted, internal, promotion}`). A `paddle`-sourced
row is never silently overwritten by a gift grant — see `RBAC.md`/
`GRAND_ADMIN.md` for the paid-precedence rule.

## PAYMENT != ENTITLEMENT (mission 17's explicit invariant, re-verified)

Stated as plainly as the mission brief itself states it: **a payment
record and an entitlement record are never the same fact, and neither
implies the other structurally.** Concretely:

- Granting a `gifted`/`internal`/`promotion` entitlement creates **zero**
  `PaymentRecord` rows — nothing in `gift_service`/`entitlement_service`'s
  grant path ever touches `payment_records`.
- A `PaymentRecord` existing does not by itself grant access — only
  `entitlement_service`/the webhook-driven subscription path actually
  creating/updating an `Entitlement`/`Subscription` row does that; the two
  are written by separate, independently-callable code paths.
- Revenue metrics (`revenue_service.compute_metrics`) never join against
  `Entitlement` at all — the query surface literally does not include the
  table gifted/internal/promotion access lives in, which is a stronger
  guarantee than "we remembered to filter by source" (there is no filter
  to forget).

## Cross-product accounts (global identity)

`global_user_id` (`User.id`, e.g. `usr_<uuid>`) is the sole, immutable
cross-product identity key — never email (mutable, and never assumed
unique across a user's lifetime the way the id is). `ProductMembership`
records that a global user has actually authenticated into a given
product (written only at OIDC token exchange, never speculatively) —
never a duplicate Platform-Core-level user row per product. A user's
entitlements across every product they've touched are all rows in the
same `entitlements` table, keyed by the same `user_id`, distinguished by
`product_id` — this is what makes "show me every product this user has a
subscription to" a single filtered query, not a fan-out across
per-product identity stores.

## Known limitations, stated plainly

- No separate reuse-detection scheme on the OIDC refresh token beyond the
  central session refresh token's own rotation (see
  `PRODUCT_INTEGRATION_CONTRACT.md` §"Refresh rotation + reuse
  protection").
- Loady's own pre-existing gifted-subscription mechanism
  (`gift_subscription_service.py`) is not migrated onto this generic
  `Entitlement`/`source=gifted` model — it continues operating on Loady's
  own `Subscription.provider` column, unchanged by this or any prior
  platform mission (`LOADY_MIGRATION.md` §"Gifted subscriptions" tracks
  this as explicit future work).
- Bundle checkout (a real purchase flow that grants several products at
  once) has no public checkout UI in V1 — only the data model
  (`BundleProductPlan`, `BundleAccess`, `source=BUNDLE`) exists, ready for
  a future checkout flow without a schema change.
