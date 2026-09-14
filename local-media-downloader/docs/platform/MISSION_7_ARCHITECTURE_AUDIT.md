# Mission 7 — Architecture Audit

Branch: `unified-platform-v3`. Base commit: `762213b` (Mission 6 final). This
audit supersedes `V2_ARCHITECTURE_AUDIT.md` (Mission 6, now stale — written
before Account Portal, React SDK, and session revocation were finished) and
corrects claims in `LOADY_IDENTITY_INTEGRATION.md` (written on
`unified-platform-v1`, since contradicted by later code).

**Method**: every classification below was checked against current source,
not inferred from prior mission docs. File:line citations are given so a
future mission can re-verify quickly. Where something could not be verified
without running code (capacity, live Docker builds, test pass counts), it is
marked `NEEDS EXECUTION` and is tracked separately, not asserted here.

## Classification legend

- **central** — Platform Core is the sole source of truth today.
- **product-owned** — Loady correctly owns this; no cutover needed.
- **transitional** — a bridge exists (hybrid/dormant/cache), correctly
  designed to be safe, but cutover is incomplete.
- **must-remove-before-cutover** — Loady logic that duplicates/competes with
  Platform Core and must be retired before GO.
- **acceptable-post-cutover** — Loady logic that can coexist with Platform
  Core indefinitely (product-specific behavior, not identity/billing truth).

## 1. Identity / Auth

| Component | File | Classification |
|---|---|---|
| Central user record, password hashing, OIDC issuance | `platform-core/backend/app/services/auth_service.py` | central |
| Loady's own `User` table (email, password hash) | `backend/app/database/commercial_models.py` | **transitional** |
| Global-user linkage (`global_user_id`) | `backend/app/services/platform_identity_service.py` | central (linkage), transitional (adoption) |
| Live gate wiring | `backend/app/api/routes_platform_auth.py` | transitional |

**Verified behavior**: Loady's platform integration is **dormant by
default** — every code path in `platform_entitlement_service.py` and
`platform_identity_service.py` checks `settings.platform_client_id` first
and no-ops to pure-local behavior when it is unset
(`platform_entitlement_service.py:371-372`). This is the de facto kill
switch today; it is not a named boolean (see §6, Phase 17 gap).

For a `global_user_id`-linked user, Loady still owns and checks its own
password locally — there is **no evidence Loady's login route delegates
password verification to Platform Core**; `global_user_id` links two
independently-authenticating accounts by email match, it does not make
Platform Core authoritative for login itself. Confirmed no dual-write path:
Loady's signup does not call Platform Core's signup endpoint, so identity
mutation is single-writer per side, but **two independent password truths
exist simultaneously for a migrated user** until Loady's local password
column is retired. This is exactly the "no duplicate signup identity path
/ no two competing identity systems" requirement Mission 7 Phase 3 flags —
**not yet satisfied**; classify Loady's local password as
**must-remove-before-cutover**.

**Session revocation propagation** (checked in this audit, previously
ambiguous): Platform Core's "sign out everywhere"
(`auth_service.py:153`, `AuditAction.ALL_SESSIONS_REVOKED`) revokes central
refresh tokens and is audited, but **emits no webhook/outbox event** to
Loady (`grep` for outbox/webhook in `auth_service.py` — none). Loady learns
of it only two ways:
1. Its next `/oauth/token` refresh attempt is rejected (immediate, but only
   once Loady's own short-lived access token expires).
2. `revalidate_central_status_if_due()` polls `/api/v1/me/status` on an
   interval (`platform_entitlement_service.py`), but that endpoint reports
   **account status only** (`disabled`/not), not per-session revocation —
   a "sign out everywhere" that leaves the account enabled is invisible to
   this poll entirely.

**Net**: ecosystem-wide sign-out is bounded by Loady's cached
Platform-Core access-token TTL (default `expires_in`, ~900s per
`store_tokens()`), not immediate. This is a reasonable bound for a
non-security-critical read, but Mission 6's commit message ("ecosystem-wide
sign-out foundation, single-session revoke") should not be read as "fully
propagated" — classify as **transitional**, document the ~15-minute bound
explicitly in the cutover runbook, and treat "immediate revocation
propagation" as a CUTOVER-DAY / post-launch hardening item, not a blocker
(disabling a compromised account already works via the same bounded
mechanism).

## 2. Entitlements / Capabilities

| Component | File | Classification |
|---|---|---|
| V2 capability engine (`resolve_effective_entitlements`) | `platform-core/backend/app/services/capability_service.py:297` | central, **not exposed to products** |
| V1 single-row entitlement (`get_active_entitlement`) | `platform-core/backend/app/services/entitlement_service.py` | central, **this is what Loady actually consumes** |
| `/api/v1/entitlements/me` (bearer, product-scoped) | `platform-core/backend/app/api/routes_v1.py:58-70` | wired to V1 model only |
| `/effective-entitlements` (capability engine) | `platform-core/backend/app/api/routes_admin.py:502` | **admin-only**, not bearer/product-callable |
| Loady hybrid resolver | `backend/app/services/platform_entitlement_service.py:280-383` | transitional |
| Loady's local `Subscription`/plan logic | `backend/app/services/plan_policy.py`, `download_gate_service.py` | product-owned today, must shrink |

**Key finding (confirmed by reading both sides of the wire, not just
docs)**: Mission 5 wired Loady's live download gate to call Platform Core
for a **migrated user's plan** (`resolve_effective_plan()`,
`platform_entitlement_service.py:333`, confirmed called from
`routes_downloads.py:128`) — this part is real, live, and fail-closed
(unreachable Platform Core → `Plan.FREE`, never escalates, never hangs
open). **However**, the Platform Core endpoint it calls
(`/api/v1/entitlements/me`) is backed by `entitlement_service.py`'s V1
single `Entitlement` row (`product_id`, `plan_id`, `source`, `status`) —
the same model from Mission 3/4. Mission 6's V2 capability engine
(`capability_service.py`), which merges entitlements across
subscription + gift + bundle + promotion sources into granular
capabilities (daily download limit, max resolution, concurrent jobs, etc. —
exactly what Mission 7 Phase 4 asks for), is **built, tested, but only
reachable through an admin-authenticated endpoint**
(`routes_admin.py:502`, `require_product_admin` dependency). There is no
self-serve, bearer-authenticated `/api/v1/capabilities/me` (or equivalent)
a product's own backend can call for its own signed-in user.

**Consequence**: today, a Loady user entitled via a *bundle* or a
*promotion/trial* (V2-only concepts) would show as `entitled=False` from
Loady's perspective, because `/entitlements/me` only looks at the single
`Entitlement` row, not the merged V2 sources. This is a real,
must-fix-before-cutover gap, not a documentation staleness issue — classify
**must-remove-before-cutover is the wrong framing here; this is
must-build-before-cutover**: add a bearer-scoped `/api/v1/capabilities/me`
(or extend `/entitlements/me`'s response) backed by
`resolve_effective_entitlements()`, then update Loady's hybrid resolver to
consume it. Tracked as a BLOCKER in the Phase 28 review.

Fail-closed behavior itself (cache TTL, outage handling) is proven correct
by Mission 5's rehearsal and remains valid at the wiring level — it is the
*source data* one layer down (V1 vs V2 model) that needs replacing, not the
hybrid/cache/outage mechanism, which can be reused as-is.

## 3. Billing

| Component | File | Classification |
|---|---|---|
| Loady's live Paddle integration | `backend/app/services/paddle_service.py`, `backend/app/database/commercial_models.py` (`Subscription`) | product-owned today, **target: must-remove-before-cutover** |
| Platform Core `PaddleBillingProvider` | `platform-core/backend/app/services/billing/paddle_provider.py` (per Mission 6 docs) | central, but **not live** — implements only `verify_webhook`/`normalize_event` as pure functions; every other call raises `BillingProviderNotConfiguredError` |
| Platform Core billing ledger/subscriptions | `platform-core/backend/app/services/billing_service.py` (per BILLING_ARCHITECTURE.md) | central, tested only against `FakeBillingProvider` |

**Finding**: these are two live, completely disconnected systems today.
Loady's Paddle webhooks are processed by Loady's own handler and create
Loady's own `Subscription` rows; Platform Core's billing stack has never
processed a real Paddle event and has no record of any existing Loady
subscription, customer ID, or payment. **No migration or reconciliation
tooling exists anywhere in the repo** for billing data (confirmed: no
script under `scripts/` or `platform-core/backend/app/scripts/` references
Paddle subscription migration). This is the single largest unbuilt piece
of Mission 7 — see Phase 5/6 status below.

## 4. Grand Admin / Account Portal / SDKs

All **central**, correctly product-agnostic, no Loady-specific logic found
in `platform-core/admin-frontend` or `platform-core/account-frontend`
beyond the intentional product-onboarding UI. Python SDK
(`platform-core/sdk`) and React SDK are central, general-purpose, used by
the demo products (`demo-product-a`, `demo-product-b`,
`sample-future-product-2`) as proof of product-agnosticism — no changes
needed for Mission 7 beyond whatever `/api/v1/capabilities/me` addition
requires an SDK method.

## 5. Infrastructure

| Component | File | Classification |
|---|---|---|
| Loady production compose | `compose.production.yml` | product-owned, **does not include Platform Core at all** — confirmed by direct read: services are `reverse-proxy`, `backend`, `postgres` only |
| Platform Core staging compose | `platform-core/compose.staging.yml` | central, never merged into a combined production-shape file |
| Maintenance mode | `backend/app/config/commercial_settings.py:44` (`MAINTENANCE_MODE`, default `false`) | product-owned, real, proven live in Mission 5 rehearsal |
| Preflight script | `scripts/platform/preflight-production-migration.sh` | central-adjacent tooling, functional, missing several Mission-7-specific checks (capacity, port conflicts, debug-mode exposure — see Phase 26) |
| Backup scripts | `scripts/platform/backup-before-platform-migration.sh`, `verify-backup-restorable.sh` | functional, unencrypted, no off-site target — BLOCKER carried from Mission 5 |

**No combined production Compose file exists** — this is Mission 7 Phase
18's core deliverable and is entirely unbuilt. See
`MISSION_7_PRODUCTION_TOPOLOGY.md` for the target shape.

## 6. Feature flags

Only two real flags exist in code today:
- `MAINTENANCE_MODE` (`backend/app/config/commercial_settings.py:44`) — real, tested.
- Implicit dormancy via empty `PLATFORM_CLIENT_ID`
  (`platform_entitlement_service.py:371`,
  `platform_identity_service.py` equivalent) — functions as a kill switch
  but is not a named, documented boolean with its own startup-visibility
  line or test suite, as Mission 7 Phase 17 requires.

`PLATFORM_AUTH_ENABLED`, `PLATFORM_ENTITLEMENTS_ENABLED`,
`PLATFORM_BILLING_ENABLED` as named, independently-testable flags: **not
started**. Building these is Mission 7 Phase 17's deliverable — see
separate tracking; implementation should wrap (not replace) the existing
`platform_client_id`-dormancy behavior so nothing already proven has to be
re-proven, and should reject the unsafe combination
`PLATFORM_ENTITLEMENTS_ENABLED=true` with `PLATFORM_AUTH_ENABLED=false`
(entitlements without identity linkage is meaningless).

## Summary table (Mission 7 classification of every audited dependency)

| Dependency | Classification |
|---|---|
| Loady local password truth | must-remove-before-cutover |
| Loady local single-row plan gate for non-migrated users | acceptable-post-cutover (Free-tier/never-linked users have nothing to migrate) |
| V1 `/entitlements/me` as sole product-facing entitlement source | must-build-before-cutover (replace/extend with V2 capability data) |
| Loady's live Paddle integration | must-remove-before-cutover (after Platform Core billing goes live + reconciled) |
| Platform Core `PaddleBillingProvider` | must-build-before-cutover (currently non-functional beyond pure functions) |
| Ecosystem-wide sign-out (bounded, ~15 min) | acceptable-post-cutover (documented bound, not a blocker) |
| Combined production Compose | must-build-before-cutover |
| Named feature flags (`PLATFORM_*_ENABLED`) | must-build-before-cutover |
| Backup encryption/off-site/retention | must-build-before-cutover (BLOCKER, carried from Mission 5) |
| Real TLS certificate | CUTOVER-DAY CHECK (needs a real domain, not a code change) |
| Grand Admin, Account Portal, SDKs | central, no changes needed |
