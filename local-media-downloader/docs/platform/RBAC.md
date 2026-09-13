# RBAC: generic role + scope

Mission-brief section 17 asks for "generic role + scope architecture
rather than hard-coded per-product roles" - realized as one table:

```text
role_assignments
  user_id     -> users.id
  role_slug   -> roles.slug     (super_admin | admin | support | finance | user)
  scope       "global"  OR  "product:<slug>"    (e.g. "product:loady")
  granted_by  -> users.id (nullable)
```

`Role` itself is a tiny, static reference table (five rows, seeded
idempotently on every startup by `app/database/seed_roles.py` - safe
because these are fixed application config, not user/business data,
unlike products/plans/admins which are explicit CLI-only actions).

## The one rule that matters: no self-escalation (mission-brief section 46)

`rbac_service.has_role(session, user_id, role, scope)` checks the
**exact** scope requested - there is no wildcard, no "global implies every
product scope" shortcut, and no "a product scope implies global" shortcut
either. Concretely:

- `is_global_admin()` = `has_role(ADMIN, "global")` OR
  `has_role(SUPER_ADMIN, "global")`.
- A user with `role=admin, scope="product:loady"` fails
  `is_global_admin()` outright and gets **403** from every Grand Admin
  endpoint (`require_global_admin`) -
  `tests/test_admin.py::test_product_scoped_role_does_not_grant_global_admin`
  proves this directly, live, over HTTP.
- There is no code path anywhere that grants a role to yourself via the
  API - `POST /api/v1/admin/users/{id}/roles` is `require_super_admin`,
  and nothing about calling it with your own `user_id` changes that check.

## Two tiers inside Grand Admin

- **`require_global_admin`** (role `admin` or `super_admin`, scope
  `"global"`): can use the console - Overview, Users, Products, Gifted
  Access, Audit Log, and can grant/change/revoke entitlements.
- **`require_super_admin`** (role `super_admin`, scope `"global"` only):
  additionally can assign/revoke roles and register OAuth clients
  (service-to-service credentials). A plain `admin` cannot create another
  admin or a super_admin - `tests/test_admin.py::
  test_global_admin_cannot_assign_roles_only_super_admin_can`.

Bootstrapping the very first `super_admin` has **no HTTP path at all**
(mirroring Loady's `promote_admin` script exactly) -
`app/scripts/promote_super_admin.py <email>` is CLI-only,
existing-user-only, idempotent.

## `support` and `finance` (mission-brief section 17)

Seeded as roles with no endpoints gated behind them yet in V1 - deliberate
scope control (mission-brief section 45: "keep V1 focused"). The
generic `scope` design means adding, say, a `finance`-only view of
`PaymentRecord` later is a new `Depends(require_role(FINANCE, "global"))`
dependency, not a schema change.
