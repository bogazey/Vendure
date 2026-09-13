# Entitlements

## One generic representation, regardless of source

`app/database/models.py::Entitlement` is the single representation for
every access path a user can have in a product - paid, gifted, trial,
promo, lifetime, or bundle-derived - distinguished **only** by `source`,
never by which code path or table wrote it (mission-brief section 9):

```text
entitlements
  id
  user_id        -> users.id            (the global user)
  product_id     -> products.id         (which product)
  plan_id        -> plans.id            (product-scoped plan, see below)
  source         free|paddle|gifted|promotion|trial|internal|lifetime|bundle
  status         active|expired|revoked
  starts_at / expires_at (nullable = never expires)
  granted_by     -> users.id (nullable) (which admin, for gifted/internal)
  reason         (nullable, admin note)
```

## Product-scoped plans (mission-brief section 9)

`Plan` is `(product_id, slug)` unique - `loady/free` and `demo-a/free` are
two distinct rows with two distinct ids. Nothing assumes every product has
the same plan set; `entitlement_service.get_plan` raises `InvalidPlanError`
(422) if an admin tries to grant a plan slug that product doesn't have.

## The one function every product calls

```python
entitlement_service.get_active_entitlement(session, user_id, product_id) -> Entitlement | None
```

This is deliberately the *only* place "is this user entitled right now"
is answered. It structurally excludes:

- **Wrong product** - the query is scoped by `product_id`; a Loady
  entitlement is invisible when asked about `product_id="demo-b"`
  (`tests/test_entitlements.py::test_wrong_product_denied`).
- **Expired** - `expires_at` is checked against "now" every call, not
  cached (`test_expired_entitlement_denied`); a `None` `expires_at` means
  "never expires" (used for `lifetime` and most `paddle`/`gifted` grants).
- **Revoked** - `status != "active"` is excluded outright.

Products never see a raw `Entitlement` row - they call
`GET /api/v1/entitlements/me` with their bearer access token (see
`SSO.md`), which internally calls exactly this function scoped to the
calling client's own `product_id` (`routes_v1.py::
my_entitlement_for_calling_product`) - so a product literally cannot ask
about another product's entitlement even if it wanted to; there's no
parameter for it.

## Grant / change / revoke (`entitlement_service.grant_or_change` / `revoke`)

Both are the implementation behind Grand Admin's entitlement control
(`GRAND_ADMIN.md`). A grant to a product a user is already entitled in
**updates the same row** (never creates a second active entitlement per
product) and is audited as `entitlement_changed`/`gifted_access_changed`
rather than a fresh grant; a genuinely new grant is audited as
`entitlement_granted`/`gifted_access_granted`. Which audit action fires is
decided purely by `source` (`_GIFTED_SOURCES = {gifted, internal,
promotion}`) - see `RBAC.md`/`GRAND_ADMIN.md` for the paid-precedence rule
that blocks this function from ever silently overwriting a `paddle`-sourced
row.

## Bundles (mission-brief section 12) - the data model, not the checkout

No public bundle checkout was built in V1 (explicitly out of scope). What
*was* built so bundles can be added later without redesigning identity:
nothing in `Entitlement` assumes a 1:1 relationship with a payment. A
future "Creator Suite" bundle purchase would:

1. Write one `PaymentRecord` (see `BILLING.md`) for the bundle purchase.
2. Call `entitlement_service.grant_or_change` once per product the bundle
   includes (Loady Creator, Filey Pro, Pixly Pro, ...), each with
   `source=EntitlementSource.BUNDLE`.

No schema change is required for that - `BUNDLE` already exists as a
enum value precisely so this path is ready without redesigning anything.

## Gifted / internal access supersedes nothing yet (mission-brief section 10)

Loady's own `gift_subscription_service.py` is **not migrated or touched**
by this mission (see `LOADY_MIGRATION.md`) - it continues operating
exactly as before, on Loady's own `Subscription.provider` column. Platform
Core's `Entitlement.source in {gifted, internal, promotion}` is the
generic version future products should use directly rather than
reinventing Loady's pattern per-product; migrating Loady's existing gifted
subscriptions onto this table is explicitly future work, planned but not
executed (`LOADY_MIGRATION.md` §"Gifted subscriptions").
