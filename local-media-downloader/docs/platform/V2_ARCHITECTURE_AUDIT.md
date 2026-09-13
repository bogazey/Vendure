# Platform Core V2 — Architecture Audit

Phase 1 of Mission 6. Written after reading Platform Core's actual code
(`platform-core/backend/app/**`), the Mission 3/4/5 docs
(`docs/platform/IDENTITY.md`, `SSO.md`, `ENTITLEMENTS.md`, `BILLING.md`,
`RBAC.md`, `GRAND_ADMIN.md`, `SESSION_REVOCATION.md`), Loady's existing
commercial stack (`backend/app/services/paddle_service.py`,
`paddle_client.py`, `gift_subscription_service.py`,
`commercial_models.py`), and the Mission 5 migration/rollback docs. This
is a factual snapshot, not aspirational — every claim below was checked
against the file it describes.

## 1. What already exists (reusable, do not rewrite)

| Area | File(s) | Verdict |
|---|---|---|
| Global identity (`User`, immutable `id`, mutable `email`) | `database/models.py` | Solid. Keep as-is. |
| Central sessions (`RefreshToken`, hashed, revocable) | `database/models.py`, `auth_service.py` | Solid. No "sign out all" endpoint yet (§4 below). |
| OIDC/OAuth SSO for products (PKCE, exact-match redirect URIs, hashed codes/secrets) | `oidc_service.py`, `routes_oauth.py` | Solid, standards-based. Client-credentials (service-to-service) grant does **not** exist yet — only the authorization-code grant. |
| Product registry + membership | `product_service.py` | Solid, already data-driven (no hard-coded product list). |
| Generic `Entitlement` (source-tagged, product-scoped plan) | `entitlement_service.py` | Solid design, but **single mutable row per (user, product)** — `grant_or_change` overwrites the row in place. Confirmed at `entitlement_service.py:105-172`: this was a deliberate mission-5 fix for migration idempotency, but it means **prior grant history only survives in `AuditLog`, not as first-class rows**. V2 must not lose this idempotency property while adding richer gifted/subscription history. |
| RBAC (`Role`/`RoleAssignment`, scope = `"global"` or `"product:<slug>"`) | `rbac_service.py` | Solid, already generic — no per-product enum needed for new products. |
| Audit log | `audit_service.py`, `AuditLog` | Solid, append-only, before/after JSON. |
| Grand Admin (overview/users/roles/products/plans/gifted/clients/audit) | `routes_admin.py`, `admin-frontend/` | Solid for what it covers. No billing/subscription/bundle/session/capability surface at all (never built — confirmed by grep, zero matches for "subscription" or "bundle" in `platform-core/backend`). |
| `Plan` (product-scoped, `(product_id, slug)` unique) | `database/models.py` | Correct shape, but **no capability data attached** — a plan is just a name. Every "what can Pro do" answer today would have to be hard-coded in product code, exactly what mission-brief Phase 5/6 forbids. |
| `PaymentRecord` | `database/models.py` | Exists as a schema boundary only (`BILLING.md` says so explicitly) — **zero real rows are ever written to it in V1**, no processor is wired in. Correctly generic (`provider` free-text). No subscription concept above it (flat one-time-payment shape only — no recurring period, no cancel-at-period-end). |
| Loady's real billing stack (separate codebase, `backend/app/services/paddle_service.py` etc.) | `backend/` (Loady) | This is the only *working, tested* billing code in the whole repo. `paddle_service.verify_webhook_signature` (HMAC-SHA256 over `f"{ts}:{raw_body}"`, `Paddle-Signature: ts=..;h1=..`) is correct and reusable as-is. Loady's `Subscription`, `gift_subscription_service.py`, and Paddle webhook handling are the reference implementation to generalize — **not migrated onto Platform Core**, confirmed still true by `ENTITLEMENTS.md`'s own "Gifted / internal access supersedes nothing yet" section. |

## 2. Confirmed gaps (what Mission 6 must build)

1. **No capability/entitlement-definition registry.** `Plan` has no attached data — nothing prevents "every entitlement hard-coded in Python conditionals" (mission-brief Phase 6's explicit anti-pattern), because there's no typed model to hang capability values on yet.
2. **No effective-entitlement resolution across multiple simultaneous sources.** Today `get_active_entitlement` returns exactly one row — there is no concept of "paid Pro + gifted Creator, resolve to Creator, keep both for history," because there is only ever one live row per `(user, product)`.
3. **No provider-neutral `Subscription` model.** `PaymentRecord` is a flat one-time-payment record; there's no period/cancellation/renewal shape at all in Platform Core.
4. **No billing provider abstraction.** Zero billing interface exists in `platform-core`; Loady's Paddle code is real but product-specific and un-generalized.
5. **No webhook idempotency/replay infrastructure.** Nothing in `platform-core` receives webhooks at all yet.
6. **No dedicated Gifted-Access history table.** Gifted access is just `Entitlement.source in {gifted, internal, promotion}` on the single mutable row — a re-gift overwrites the prior gift's detail (expiry, reason) with no first-class historical record (only the generic `AuditLog` before/after snapshot survives).
7. **No bundle model at all** — `EntitlementSource.BUNDLE` exists as an enum value only; `ENTITLEMENTS.md` itself says "not the checkout... no schema change... for that" — meaning the actual `Bundle`/`BundleProductPlan` tables were never created.
8. **No service-to-service (server-to-server) authentication** distinct from the user-facing OIDC authorization-code grant — a product backend today has no way to call an internal/service-scoped Platform Core API except by holding a user's own bearer token.
9. **No outbound webhook/event delivery to products** (no outbox table, no signed event delivery) — products would have to poll.
10. **No account-portal frontend at all** — only `admin-frontend` (Grand Admin) exists; there is no end-user identity/billing/session self-service UI.
11. **No SDK/client library** for future products — the two demo products (`demo-product-a`, `demo-product-b`) each hand-roll their own OIDC client code; there is no shared package.
12. **No product-onboarding CLI** — `register_demo_clients.py`/`register_loady_client.py` are one-off scripts, not a general `register_product` tool.
13. **Ecosystem-wide logout is unimplemented** — confirmed by `docs/platform/SESSION_REVOCATION.md`'s own scope note (single-session revocation exists; no cross-session "epoch" concept in the schema).

## 3. Design principle carried forward into V2

Every V2 addition below is **additive**, not a replacement:

- The existing `Entitlement` table keeps its current single-mutable-row-per-`(user,product)` behavior untouched — every existing caller (`GET /api/v1/entitlements/me`, Loady's OIDC integration, `test_loady_migration.py`, `test_cross_product.py`) keeps working unmodified. This directly satisfies mission-brief Phase 46 ("Mission 5 Loady migration must remain valid... do not break existing Loady OIDC integration").
- New tables (`Subscription`, `GiftedAccess`, `Bundle`/`BundleAccess`, `EntitlementDefinition`/`PlanEntitlement`, `BillingWebhookEvent`, `OutboxEvent`, service-credential fields on `OAuthClient`) sit *alongside* it. A new `capability_service.resolve_effective_entitlements()` reads all of them and additionally keeps the legacy `Entitlement` row in sync (so old and new code paths agree on "is this user entitled" for the plain paid/free/gifted case), while only the new function exposes the richer multi-source, typed-capability view.
- `PaymentRecord` gets additive nullable columns (tax/fee/net/refunded/subscription reference) rather than a parallel ledger table, per "do not rewrite working systems unnecessarily."

## 4. Technical debt / risks flagged for V2 (and how V2 addresses or defers them)

- **Single-mutable-row Entitlement** loses gift-history detail on re-grant → addressed by new `GiftedAccess` (append-only-by-convention: revoke sets `status`, a new grant is a new row) as the historical/detail table, `Entitlement` remains the fast current-state cache kept in sync.
- **No enum-value ordering for capabilities** → V2 typed capability values (boolean/integer/string+allowed-values) explicitly document a *declared* precedence/merge rule per type (max for integer, OR for boolean, highest-precedence-source wins for string/enum) rather than an implicit one — see `ENTITLEMENT_ENGINE.md`.
- **`cookie_domain`/`platform_auth_base_url` already configurable, not hard-coded** — good, no change needed for multi-product rollout.
- **No rate limit on the future webhook endpoint** — V2's webhook route must not share the interactive `admin_mutation_limiter` (a burst of legitimate provider retries would be throttled); a separate, generous limiter is used instead.
- **SQLite dev / Postgres prod split already exists** (`database/db.py`) — V2 migration is written against the same Alembic chain and is exercised against SQLite in CI-equivalent test runs here; a real Postgres run is explicitly called out as **UNTESTED** in the final report if it isn't actually executed against Postgres in this session.
- **Docker/prod images, `compose.production.yml`, live Paddle, and the VPS are explicitly out of scope** (mission-brief Phase 56) — none of this audit or the implementation that follows touches them.

## 5. Scope decision for this mission run

Given the size of the full 57-phase brief, this pass prioritizes, in order:
backend data model + migration → effective-entitlement/capability engine →
billing/subscription/webhook/gift/bundle architecture → service-auth →
outbox → targeted tests and security review → a working slice of Grand
Admin surfacing the new data → focused docs. Account-portal frontend,
full SDK packages, the onboarding CLI, and full browser E2E are addressed
only as time/budget allow after the above is solid; anything not reached
is reported as **NOT DONE** (not attempted) and anything not actually
executed is reported as **UNTESTED** in the Mission 6 final report —
never inferred or assumed passing.
