# Mission 6 Continuation — Security Review Round 2

Full review repeated after the continuation's implementation (Product
Subscription Manager, product-scoped RBAC, promotions/trials, revenue
metrics, account closure, email change, encrypted webhook secrets,
Grand Admin V2 UI, Account Portal), per the explicit review checklist.
Each area below states what was checked and the actual code path
verified against - not a generic checklist tick.

## Finding fixed

### Product-scoped RBAC widened who could fabricate a "paid" entitlement

Making `PATCH /api/v1/admin/users/{id}/entitlements` product-scoped (so a
per-product admin can manage their own product's gifts/entitlements
without needing global admin) had a side effect: it also let that same
product-scoped admin set `source=paddle` or `source=lifetime` for their
own product - i.e., mark an entitlement as revenue-sourced with no real
`PaymentRecord` behind it. This can't fabricate actual currency (only
`PaymentRecord` is ever summed - see `BILLING.md`), but several report
queries filter on `Entitlement.source == "paddle"` for "paid subscriber"
counts, which this would have inflated.

**Fixed**: `grant_or_change_entitlement` now requires a global admin
specifically for `paddle`/`lifetime` sources, regardless of product
scope; every other source (gifted/promotion/trial/internal/free/bundle)
remains available to a product-scoped admin for their own product.
Regression tests: `test_product_scoped_admin_cannot_fabricate_a_paddle_sourced_entitlement`,
`test_product_scoped_admin_can_still_grant_gifted_via_the_same_route` (no
regression on the legitimate case), `test_global_admin_can_still_grant_paddle_sourced_entitlements`.

## Reviewed and confirmed correct (no change needed)

- **Plan manipulation**: `catalog_service.update_plan` only accepts a
  fixed field set (`_MUTABLE_PLAN_FIELDS`) that excludes `product_id` and
  `slug` - a plan can never be moved to a different product or have its
  identity changed through the update API. Verified by
  `test_update_plan_rejects_unknown_field`.
- **Price manipulation / historical-price mutation**: grepped
  `catalog_service.py` for every write to `Price` - `create_price` (new
  row only), `retire_price` (`is_active`/`retired_at` only),
  `update_price_visibility` (`is_public` only). No function anywhere
  mutates `amount_cents`/`currency`/`interval`/`provider_price_id` on an
  existing row. Verified end-to-end by the mandatory E2E catalog test's
  own "historical price preservation" proof (retiring a $4.99 price and
  creating a $5.99 one leaves the original row's amount untouched).
- **Billing provider IDs**: `provider_price_id` is admin-supplied free
  text, stored via parameterized queries throughout (no raw SQL
  interpolation anywhere in this codebase) - no injection surface.
- **Gift abuse**: `gift_service.grant_gift` now checks
  `plan.gifted_eligible` (a plan can opt out of gifting entirely) in
  addition to the pre-existing paid-precedence guard; `revoke_gift`'s
  product-scope check (added this continuation) was verified adversarially.
- **Bundle escalation**: bundle creation/product-mapping/access-granting
  routes were deliberately left global-admin-only (not product-scoped) -
  a bundle spans multiple products by definition, so no single product's
  admin should be able to create or modify one. Confirmed unchanged in
  `routes_admin.py`.
- **Subscription migration (plan upgrade/downgrade)**:
  `subscription_service.upsert_subscription`'s plan-change branch
  re-resolves `plan_version_id` from the NEW plan's current version, never
  reuses the old subscription's stale version - verified by the plan
  versioning test suite's upgrade/downgrade coverage.
- **Account portal IDOR**: `routes_account.py`'s closure
  confirm/cancel check `request.user_id != user.id` → 404 (not 403, to
  avoid confirming the request's existence to a caller who doesn't own
  it) - verified by `test_cannot_confirm_someone_elses_closure_request`.
  `/api/v1/auth/sessions/{id}` scopes by `(id, user_id)` together in one
  query (from the prior session, re-verified unchanged).
- **Email-change takeover**: `confirm_email_change` re-checks the email
  collision AT CONFIRMATION time (not just at request time) - so if
  someone else legitimately registers the target address between a
  change request and its confirmation, the stale confirmation correctly
  fails rather than silently taking over the now-real account. Verified
  by `test_cannot_confirm_into_an_email_already_taken_by_someone_else`.
- **Service authentication**: unaffected by this continuation's changes;
  `require_client_admin` is a NEW, separate gate for webhook-config/
  service-grant management, not a change to how a service token itself is
  issued or verified.
- **Webhook spoofing/replay**: unaffected except the rate-limit hardening
  already reviewed in this continuation's earlier security note; re-
  verified functioning against real PostgreSQL concurrency in
  `MISSION_6_POSTGRESQL_VALIDATION.md`.
- **Encrypted webhook secrets**: AES-256-GCM, fail-closed outside
  development, DB-level check that the stored column never contains the
  raw secret - `test_secret_encryption.py` (13 tests, ported test-for-test
  from Loady's own reviewed pattern).
- **Frontend token handling**: grepped both `admin-frontend/src` and
  `account-frontend/src` for `localStorage`/`sessionStorage` - the only
  use in either app is the UI language preference (`grand-admin-language`/
  `account-portal-language`), never a token, session id, or credential.
  Every API call uses `credentials: "include"` against httpOnly cookies
  set by the backend; no fetched token is ever stored in JavaScript-
  accessible storage.
- **Admin privilege escalation**: `POST/DELETE /api/v1/admin/users/{id}/roles`
  remains `require_super_admin`-only, unconditionally - re-verified
  adversarially (`test_loady_admin_cannot_assign_global_roles_to_self_or_anyone`,
  `test_loady_admin_cannot_assign_themselves_admin_on_gamey_either`).

## New, unrelated bug found and fixed during this pass

**CORS allowlist was missing the new Account Portal's dev port.**
`app/main.py`'s CORS middleware allowlisted `5273` (admin-frontend) but
not `5274` (the new account-frontend) - every authenticated fetch from
the Account Portal would have been silently blocked by the browser
(no `Access-Control-Allow-Origin` match) despite the backend itself
working correctly. Caught while preparing the browser E2E run, before
any user ever hit it. Fixed by adding `5274` to the allowlist alongside
`5273`, following the exact same pattern.

## Documented limitations (not fixed - real, out of scope for this pass)

Carried forward from the prior round (`MISSION_6_SECURITY_REVIEW.md`),
still true: no client-secret rotation for product-scoped admins (super-
admin-only by design), billing-webhook rate limiting is provider-keyed
rather than IP-aware (mitigated this continuation via the invalid-
signature budget split, not eliminated), and system-driven entitlement
syncs still attribute the audit actor as the affected user rather than a
distinct system principal.

New this continuation:

- **No distinct "finance" scope per product** - the RBAC model has global
  `finance`/`support` roles (from V1) but no product-scoped equivalent;
  the paddle/lifetime-source restriction above is a coarse fix (global-
  admin-only) rather than a proper "product finance" role, because
  building that role properly is a larger design task than this pass's
  remaining scope. Tracked for a future pass.
- **Grand Admin's per-user detail views** (`get_user`, `get_user_
  memberships`, `get_user_entitlements`, `get_user_audit_log`) remain
  global-admin-only, not extended to product-scoped admins at all in this
  pass - a conservative choice (fails closed), not a vulnerability, but
  means a product-scoped admin cannot yet see even their own product's
  slice of a user's profile through those specific routes (they can via
  the product-scoped catalog/gift/effective-entitlement routes instead).
