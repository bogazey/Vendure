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
mechanism). This bound is specifically about a *product's* (Loady's)
cached OIDC access token — Platform Core has no control over when Loady's
own code re-checks it, unlike the finding below.

**RESOLVED this mission — a real gap found by actually running the
browser E2E, not by re-reading docs**: unlike the cross-product case
above, Platform Core's own single-session revoke ("sign out this device,"
Account Portal → Sessions page) was NOT actually immediate for its own
first-party `session_access` cookie, despite the UI presenting it as an
immediate action and despite the sign-out-*everywhere* path already being
provably immediate via the `security_epoch` claim. `revoke_session` only
ever revoked the `RefreshToken` row; the target device's already-issued
access-token cookie kept authenticating for up to
`access_token_ttl_minutes` (default 15) regardless. Since Platform Core
owns both token issuance and verification here (no other team's code to
touch, unlike the OIDC-access-token case), this was fixed rather than
just documented as a bound: `session_access` gained an optional `"sid"`
claim (the owning `RefreshToken.id`), checked in `get_optional_user`
alongside the existing epoch check. See `docs/platform/SESSION_SECURITY.md`
"Single-session revoke (Phase 21)" for the detail and
`test_http_revoke_single_session_immediately_rejects_that_devices_still_unexpired_cookie`
for the regression test. Single-session revoke is now genuinely
immediate, matching sign-out-everywhere.

## 2. Entitlements / Capabilities

**RESOLVED this mission** (was the Phase 28 BLOCKER below — kept for the
historical record, since a future mission re-verifying this section
should be able to see exactly what changed and why):

| Component | File | Classification |
|---|---|---|
| V2 capability engine (`resolve_effective_entitlements`) | `platform-core/backend/app/services/capability_service.py:297` | central, **now exposed to products via `/api/v1/capabilities/me`** |
| V1 single-row entitlement (`get_active_entitlement`) | `platform-core/backend/app/services/entitlement_service.py` | central, still Loady's primary/fast-path source |
| `/api/v1/entitlements/me` (bearer, product-scoped) | `platform-core/backend/app/api/routes_v1.py` | wired to V1 model only, unchanged |
| `/api/v1/capabilities/me` (bearer, product-scoped) | `platform-core/backend/app/api/routes_v1.py` | **new**: self-serve bearer route onto the V2 merge engine, same product-scoping guarantee as `/entitlements/me` |
| `/effective-entitlements` (capability engine) | `platform-core/backend/app/api/routes_admin.py:502` | admin-only, unchanged, now shares its response shape (incl. `rank`) with the bearer route |
| Loady hybrid resolver | `backend/app/services/platform_entitlement_service.py` | transitional, **now consults `/capabilities/me` as a fallback** when `/entitlements/me` says not-entitled |
| Loady's local `Subscription`/plan logic | `backend/app/services/plan_policy.py`, `download_gate_service.py` | product-owned today, must shrink — unchanged by this fix |

**What was fixed**: `/api/v1/entitlements/me` only ever looked at the
single legacy `Entitlement` row, so a user entitled via a *bundle* or a
*promotion/trial* (V2-only concepts) showed as `entitled=False` to their
own product. Added `/api/v1/capabilities/me`, backed directly by
`resolve_effective_entitlements()`, with the exact same per-product
bearer-scoping guarantee `/entitlements/me` already had (a client with no
`product_id` gets nothing; every other client only ever sees its own
product's merged capabilities). `EffectiveSource` gained a `rank` field
(the same tie-break rank `_merge_capabilities` already used internally
for STRING/ENUM capabilities) so a bearer caller with no "winning plan"
concept of its own — like Loady — can pick the highest-ranked
contributing source's `plan_slug` without duplicating Platform Core's
internal ranking table on the product side.

Loady's `get_authoritative_entitlement` now calls `/capabilities/me` as
an **additive-only** fallback: only when `/entitlements/me` says
`entitled=False` does it check `/capabilities/me`, and only a `true`
there can turn the answer into `entitled=True` — it can never turn an
already-`true` answer false, so it cannot weaken the existing fail-closed
guarantee (unreachable/erroring `/capabilities/me` is swallowed and
treated as "no V2 data available," falling back to the legacy answer,
never raised). Fail-closed behavior itself (cache TTL, outage handling,
`Plan.FREE` on any doubt) is unchanged — proven correct by Mission 5's
rehearsal and still valid at the wiring level; only the *source data* one
layer down was extended, not the hybrid/cache/outage mechanism.

Test coverage: `platform-core/backend/tests/test_capabilities_me.py`
(the exact gap — bundle-only access invisible to `/entitlements/me`,
visible and correctly product-scoped via `/capabilities/me`),
`test_capability_engine.py`'s rank assertion, and
`backend/tests/test_platform_capabilities_fallback.py` (Loady-side:
the actual HTTP-calling fallback logic, including "never calls
`/capabilities/me` when already entitled" and "network failure never
raises, falls back to the legacy answer").

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
| Backup scripts | `scripts/platform/backup-before-platform-migration.sh`, `verify-backup-restorable.sh` | **RESOLVED this mission**: encryption-at-rest, file permissions, retention pruning all added and verified end-to-end against the real staging containers. Off-site push mechanism built and verified with a local stand-in; a real remote destination is not configured anywhere — the one open item, see `docs/platform/PLATFORM_BACKUP_RESTORE.md` "Mission 7 additions" |

**Combined production Compose (Phase 18): PARTIALLY RESOLVED.**
`compose.rc.yml` (added at the Mission 7 checkpoint, before this
continuation) exists and is real — 7 services, resource limits,
healthchecks, `restart: unless-stopped`, `cap_drop`/`read_only` hardening,
correct `depends_on: condition: service_healthy` ordering. This
continuation found it referenced two files that didn't exist
(`.env.rc.example` and `platform-core/.env.production.example`), which
would have blocked anyone from ever actually running it — both added.
`docker compose -f compose.rc.yml config` (structural + variable
interpolation validation, no build, no containers started) now passes
clean.

**NOT executed, and deliberately not attempted this session — CUTOVER-DAY
/ NEXT-SESSION CHECK, not silently assumed working:** this session found
`docker ps` showing what appears to be a live, real Loady stack already
bound to host port 80 (`loady-reverse-proxy-1`) alongside a staging stack
on 8090/8091/8443, on the same machine this repo lives on. A real build+
run rehearsal of `compose.rc.yml` (Mission 7 Phase 19's "full production-
like local rehearsal") means building ~5 fresh Docker images and starting
7 containers - non-trivial CPU/disk/memory use immediately adjacent to
what may be a live production service, and genuinely risky to attempt
without the user's explicit go-ahead given "do not touch production" is
an explicit, standing instruction for this mission. `RC_HTTP_PORT`/
`RC_HTTPS_PORT` overrides in `.env.rc.example` already document how to
avoid the port collision itself, but port safety alone doesn't remove
the resource-contention risk of building/running a full second stack
next to a live one. Until a rehearsal is actually run and its containers
observed healthy, `compose.rc.yml` must be treated as **structurally
validated, not proven** — the same distinction this audit applies
everywhere else marked `NEEDS EXECUTION`.

## 6. Feature flags

**RESOLVED this mission** (was "not started" below — kept for the
historical record).

- `MAINTENANCE_MODE` (`backend/app/config/commercial_settings.py:44`) — real, tested. Unchanged.
- Implicit dormancy via empty `PLATFORM_CLIENT_ID` — still the underlying
  credential-presence gate, unchanged; every existing call site that
  checked it still does.
- `PLATFORM_AUTH_ENABLED`, `PLATFORM_ENTITLEMENTS_ENABLED`,
  `PLATFORM_BILLING_ENABLED` (`backend/app/config/commercial_settings.py`)
  — **added**, all default `true` specifically so they *wrap* the
  existing `platform_client_id`-dormancy check rather than replacing it:
  every pre-existing test/deployment that only ever configured
  credentials, never touching these flags, keeps behaving exactly as
  before (nothing already proven had to be re-proven). What's new is a
  named, documented, credential-independent kill switch:
  - `platform_identity_service.is_configured()` now also requires
    `platform_auth_enabled`.
  - `get_authoritative_entitlement` / `resolve_effective_plan` /
    `revalidate_central_status_if_due` now also require
    `platform_entitlements_enabled` (the latter, being about account-
    status/session validity rather than plan data, is gated on
    `platform_auth_enabled` instead — a deliberate distinction).
  - A `model_validator` on `CommercialSettings` rejects
    `PLATFORM_ENTITLEMENTS_ENABLED=true` with `PLATFORM_AUTH_ENABLED=false`
    at startup (fails fast, not a silent no-op).
  - `platform_billing_enabled` is declared and tested but not yet wired
    to any call site — Loady's billing integration with Platform Core
    doesn't exist yet (see section 3); the flag exists now so the
    eventual cutover has a name to gate behind from day one.
  - A startup log line (`app/main.py`) now prints the resolved state of
    all three flags plus whether credentials are configured, so an
    operator can see the integration's actual state without
    cross-referencing `.env`.
  - Tests: `backend/tests/test_platform_feature_flags.py` (the validator,
    and each kill switch actually forcing dormancy even with valid
    credentials configured).

## Summary table (Mission 7 classification of every audited dependency)

| Dependency | Classification |
|---|---|
| Loady local password truth | must-remove-before-cutover |
| Loady local single-row plan gate for non-migrated users | acceptable-post-cutover (Free-tier/never-linked users have nothing to migrate) |
| V1 `/entitlements/me` as sole product-facing entitlement source | **RESOLVED this mission** — `/api/v1/capabilities/me` added, Loady's hybrid resolver now falls back to it |
| Loady's live Paddle integration | must-remove-before-cutover (after Platform Core billing goes live + reconciled) |
| Platform Core `PaddleBillingProvider` | must-build-before-cutover (currently non-functional beyond pure functions) |
| Ecosystem-wide sign-out (bounded, ~15 min) | acceptable-post-cutover (documented bound, not a blocker) |
| Combined production Compose | structurally validated this mission (config passes); build/run rehearsal is CUTOVER-DAY / NEXT-SESSION CHECK — deliberately not attempted, see section 5 |
| Named feature flags (`PLATFORM_*_ENABLED`) | **RESOLVED this mission** — added, wrap the existing credential-dormancy check, tested |
| Backup encryption/off-site/retention | **RESOLVED this mission** (encryption, permissions, retention verified end-to-end); real off-site destination still not configured — CUTOVER-DAY CHECK |
| Real TLS certificate | CUTOVER-DAY CHECK (needs a real domain, not a code change) |
| Grand Admin, Account Portal, SDKs | central, no changes needed |
