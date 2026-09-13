# Grand Admin

A React + TypeScript + Tailwind console (`platform-core/admin-frontend`)
matching Loady's own dark-navy/blue-purple-aqua glass admin aesthetic, in
English and Arabic with full RTL support (mission-brief section 39).

## Navigation (mission-brief section 13)

`Overview | Users | Products | Gifted Access | Audit Logs` - a focused V1
subset of the requested nav (`Entitlements` and `Subscriptions`/`Payments`
are folded into the Users detail view and the Gifted Access page rather
than getting their own top-level tabs, since V1 has no live payment
processor to show a meaningful separate Subscriptions/Payments screen for
- see `BILLING.md`). No fake data anywhere: every page either renders a
real API response or a loading/forbidden/empty state
(`components/ErrorState.tsx` renders a translated "Access denied" screen
for a 403, never a generic crash) - mission-brief section 40.

## Overview (mission-brief section 14)

Five real, non-fabricated numbers: Total Users, Active Users, Products,
Paid Subscribers (`source=paddle` only), Gifted Accounts. A
`revenue_note` explains why revenue isn't shown (see `BILLING.md`) rather
than showing a number that isn't real.

## Unified user profile (mission-brief section 15)

Opening a user (`Users` -> "View") shows, on one screen: email, global
ID (`usr_...`), status, joined date, current roles (with revoke), product
memberships, every entitlement (product/plan/source/status, with a revoke
action per active row), and a grant/change form. This is the single
cross-product view the mission asks for - built from four API calls
(`getUser`, `getUserMemberships`, `getUserEntitlements`, plus the
grant/revoke mutations), all scoped to that one `user_id`.

## Entitlement management (mission-brief section 16)

The grant/change form (product, plan, source, optional reason) calls
`PATCH /api/v1/admin/users/{id}/entitlements`. **Paid-subscription
protection is server-authoritative, not just a disabled button**: if the
target already holds an active `paddle`-sourced entitlement in that
product, the backend returns 403 regardless of what the admin frontend
sent (`routes_admin.py::grant_or_change_entitlement`) -
`tests/test_admin.py::test_paid_entitlement_cannot_be_silently_overwritten_by_gift`
proves this by attempting exactly that attack and asserting it's refused.
The same protection applies to revocation
(`DELETE .../entitlements/{product_id}`).

## Gifted Access (mission-brief section 13/16)

A dedicated read-only page listing every currently-active
`gifted`/`internal`/`promotion` entitlement across the whole ecosystem,
with the user's email, product, plan, granting admin's email, and reason -
built specifically so an operator can audit "everyone who currently has
free access" without paging through every user individually. Confirmed
live against the running Platform Core in a real browser during this
mission (see `SSO.md` §"Live proof").

## Audit Log (mission-brief section 18)

Every privileged action - entitlement grant/change/revoke, role
assign/revoke, user status change, product creation, OAuth client
registration - is recorded via `audit_service.record()` inside the same
DB transaction as the change itself, so an audit row and its effect are
never inconsistent. Fields: `actor_user_id`, `action`, `target_type`,
`target_id`, `product_id` (nullable), `before_state`/`after_state` (small,
specific JSON snapshots - never a raw model dump, so there is no code path
that could leak a password hash or token into the log; see
`tests/test_audit.py::test_audit_log_never_stores_secrets_or_password_hashes`),
`reason`, `created_at`. Append-only - there is no update/delete endpoint,
by construction (`routes_admin.py` never exposes one). Grand Admin's
Audit Logs page and each user's own detail view (filtered to that
`target_id`) both read from the same `GET /api/v1/admin/audit-log`-style
queries.

## Roles (mission-brief section 17, see `RBAC.md`)

Assign/revoke on the user detail panel, `require_super_admin`-gated. A
`support`/`finance` assignment is possible (the role exists) even though
no endpoint yet checks for it specifically - see `RBAC.md`'s "keep V1
focused" note.

## Products (mission-brief section 7)

List + create. Creating a product does not assume there will ever be
exactly ten - the form takes an arbitrary `id`/`name`/`domain`/`status`.
Plans are managed per-product (`POST /api/v1/admin/products/{id}/plans`).

## Design (mission-brief section 39)

Dark navy background with the same aqua-blue-violet gradient tokens as
Loady's brand kit (`--color-surface`, `.glass-panel`, `.btn-gradient` -
`platform-core/admin-frontend/src/index.css`), responsive down to phone
width, `i18next` + `react-i18next` with `en.json`/`ar.json`, `dir="rtl"`
applied to `<html>` when Arabic is active
(`platform-core/admin-frontend/src/i18n/index.ts`, mirroring Loady's own
`src/i18n/index.ts` pattern exactly). Verified with both a Vitest RTL test
(`src/i18n/i18n.test.tsx`) and a live browser session (see `SSO.md`).

## Authorization is two-layer, like Loady's

`ProtectedRoute` (frontend, redirects to `/login` if signed out - a UX
convenience) and `require_global_admin`/`require_super_admin` (backend,
re-resolves the caller from the DB on every request - the check that
actually matters). A normal signed-in user hitting any `/api/v1/admin/*`
endpoint directly gets 403, proven live
(`tests/test_admin.py::test_ordinary_user_denied_overview`) and via a
Vitest test asserting the frontend renders "Access denied" rather than
crashing on that same 403 (`src/pages/Overview.test.tsx`).
