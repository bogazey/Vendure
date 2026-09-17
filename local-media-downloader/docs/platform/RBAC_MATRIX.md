# RBAC Matrix

Mission 17. Consolidates `RBAC.md` (the generic role+scope architecture)
with the concrete, tested access matrix as it stands after this mission's
`support`/`finance` enforcement work — `RBAC.md` remains the mechanism
writeup (why exact-scope-only prevents self-escalation); this document is
the reference table of who can do what, and which automated test proves
it.

## Roles and scopes

Five roles (`app/models/enums.py::RoleSlug`), each held at either
`"global"` or `"product:<slug>"` scope:

| Role | Global scope | Product scope |
|---|---|---|
| `super_admin` | Full Grand Admin + role assignment + client registration/secret rotation | N/A — `super_admin` is never product-scoped in this schema |
| `admin` | Full Grand Admin (not roles/clients) | Full catalog/gifts/webhook/client-active-toggle for that one product only |
| `support` | Read subscriptions across every product | Read that one product's subscriptions only |
| `finance` | Read payments + ecosystem-wide revenue metrics | Read that one product's payments + that product's own revenue metrics only |
| `user` | No admin access | No admin access |

**The one rule that matters (mission-brief section 46, unchanged by this
mission)**: every check is an **exact** scope match. `has_role` never
treats `"global"` as implying every `"product:<slug>"`, and never treats
a product scope as implying `"global"`. There is no wildcard and no role
hierarchy beyond what's spelled out in the table above (`admin` is not
"support + finance + more" — it is a structurally separate role assigned
separately; holding `admin` on a product gives that product's catalog/
gift/client capabilities, not the `support`/`finance` routes, though the
`support`/`finance` visibility helpers do also recognize a product's
`admin` as able to see that product's own subscriptions/payments — see
"Visibility resolution" below).

## Endpoint gates (as of this mission)

| Endpoint | Dependency | Who passes |
|---|---|---|
| `GET/POST /admin/products`, `GET/PATCH/verify /admin/products/{id}` | `require_product_admin` / `require_global_admin_or_any_product_admin` | global admin; that product's own admin |
| `POST /admin/products/{id}/active` | `require_global_admin` | global admin only (deliberately higher bar than PATCH — see `PRODUCT_ONBOARDING.md` Phase J) |
| `POST /admin/clients/{id}/active`, `/webhook`, `/post-logout-redirect-uris` | `require_client_admin` | global admin; that client's own product's admin |
| `POST /admin/clients`, `/rotate-secret` | `require_super_admin` | super_admin only |
| `GET /admin/oauth-clients` | `require_global_admin_or_any_product_admin` | global admin (sees all); product-scoped admin (sees own product's clients only) |
| `GET /admin/subscriptions` | `require_global_admin_or_any_product_support` | global admin; global support; that product's admin or support |
| `GET /admin/payments`, `GET /admin/revenue/metrics` | `require_global_admin_or_any_product_finance` | global admin; global finance; that product's admin or finance |
| `GET /admin/revenue/metrics` (no `product_id`, ecosystem-wide) | inline check | global admin or global finance only — never a product-scoped role of any kind |
| `POST /admin/users/{id}/roles` (assign/revoke) | `require_super_admin` | super_admin only |
| Everything else in `routes_admin.py` not listed above | `require_global_admin` (or `require_product_admin`/`require_plan_admin`/`require_price_admin` for catalog resources resolvable to one product) | global admin; that resource's own product's admin |

## Visibility resolution (cross-product listings)

Four listings have no single `product_id` path parameter to gate at the
dependency layer and instead filter rows after the fact:

| Listing | Resolver | `None` return means | Concrete set means |
|---|---|---|---|
| `/admin/products`, `/admin/gifted-access`, `/admin/outbox` | `rbac_service.admin_visible_product_ids` | global admin — unrestricted | the caller's own product-scoped `admin` roles only |
| `/admin/subscriptions` | `rbac_service.support_visible_product_ids` | global admin, or `support` held at `"global"` scope | the caller's own product-scoped `admin` **or** `support` roles |
| `/admin/payments` | `rbac_service.finance_visible_product_ids` | global admin, or `finance` held at `"global"` scope | the caller's own product-scoped `admin` **or** `finance` roles |
| `/admin/revenue/metrics` (with `product_id`) | `rbac_service.is_global_or_product_finance_or_admin` | — (boolean, not a set) | — |

A product-scoped role of any kind (`admin`, `support`, or `finance`)
never resolves to `None` — only a role held at literal scope `"global"`
does. This is what makes "a Gamey support account gains no administrative
access to Loady" true structurally: the resolver has no code path that
returns `None` (unrestricted) for a scope string other than `"global"`.

## The bounded requirement, verified (mission 17's explicit instruction)

> "A Gamey support administrator must not automatically gain
> administrative access to Loady. Test this explicitly."

`tests/test_support_finance_rbac.py` is the real automated matrix, run on
every CI pass:

- `test_gamey_support_cannot_see_loadys_subscriptions` — row-level
  filtering proof on the one listing `support` can reach at all.
- `test_gamey_support_gains_no_administrative_access_to_loady_at_all` —
  Loady's product detail, plans, PATCH, verify, active-toggle, the global
  `/users` listing, `/overview`, `/payments` (finance's territory, not
  support's), and ecosystem-wide `/revenue/metrics` all reject a
  Gamey-scoped `support` account.
- `test_gamey_support_also_gains_no_access_to_gameys_own_admin_surfaces`
  — `support` does not even inherit `admin` capability for its **own**
  product; the roles are structurally separate, not tiers of one ladder.
- `test_gamey_finance_gains_no_administrative_access_to_loady_at_all` /
  `test_finance_role_cannot_mutate_anything` — the equivalent matrix for
  `finance`, including that it cannot reach `support`'s own
  `/subscriptions` listing.
- `test_admin_role_still_works_unaffected_by_the_new_roles` /
  `test_super_admin_still_sees_everything_unaffected` — regression guards
  proving this mission's changes only *added* visibility (to
  `support`/`finance`), never *narrowed* what `admin`/`super_admin`
  already had.

`tests/test_product_scoped_rbac.py` (Mission 6, unchanged by this
mission) remains the equivalent matrix for the `admin` role specifically,
including the IDOR-shaped check (rejecting a direct plan/price/client ID
belonging to another product, not just a `product_id` path parameter).

## Known limitation, stated plainly

`support`/`finance` are read-only by design and were wired into exactly
the listings their names imply (`support` → subscriptions,
`finance` → payments/revenue). Neither role can currently read the
per-user entitlement/membership/audit-log views
(`GET /admin/users/{id}/...`) or the global `/admin/users` listing —
those remain `require_global_admin`-only, deliberately, since `User` has
no `product_id` column to safely filter a product-scoped role's view by
(see `PRODUCT_ONBOARDING.md`'s equivalent limitations list). Extending
either role to user-level views would need that filtering question
answered first, not merely a dependency swap.
