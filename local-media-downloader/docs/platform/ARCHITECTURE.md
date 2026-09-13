# Unified Platform Architecture (`unified-platform-v1`)

This document is both the audit of Loady's existing architecture that this
mission was built from, and the target architecture for the shared
ecosystem layer (Platform Core + Grand Admin) that Loady and future
products (Gamey, Filey, Pixly, Aidy, Linky, Sendy, Convy, Civy, Crafty,
...) will eventually authenticate against.

**Nothing in this document or this branch changes Loady production.** See
the repository root for the safety rules that governed this work; they are
repeated in full in `LOCAL_DEVELOPMENT.md`.

## 1. Audit of the existing Loady architecture

Before designing anything, the existing `local-media-downloader` commercial
layer (`COMMERCIAL_ARCHITECTURE.md`) was read in full and several of its
files inspected directly. Findings, and which of Loady's own patterns were
reused verbatim rather than reinvented:

| Area | Loady's implementation | Reused in Platform Core? |
|---|---|---|
| Password hashing | Argon2id via `argon2-cffi`'s `PasswordHasher` (`security_service.py`) | **Yes, verbatim** - same library, same defaults (`app/security/passwords.py`) |
| Access tokens | JWT, HS256, `PyJWT`, 15-minute TTL, `sub`/`role`/`type`/`exp`/`jti` claims | **Upgraded to RS256** - Platform Core additionally needs to hand out tokens *other services* can verify without sharing a secret (JWKS), which HS256 structurally cannot do |
| Refresh tokens | Opaque, `secrets.token_urlsafe`, only a SHA-256 hash stored, rotated on every refresh, revocable | **Yes, verbatim pattern** (`app/security/tokens.py`, `RefreshToken` model) |
| Password reset / email verification | Single-use hashed tokens, 1h/48h TTL, `used_at` marks consumption | **Yes, verbatim pattern** |
| Login timing | Hasher always runs, even for an unknown email, to avoid a timing side-channel revealing account existence | **Yes, verbatim** (`auth_service.login`) |
| Admin authorization | `require_admin` FastAPI dependency, re-resolves the user from the DB on every request, no HTTP path to self-promote (`promote_admin` CLI script only) | **Generalized, not copied 1:1** - Platform Core needed *scoped* roles (`RoleSlug` + `scope`), so `require_global_admin`/`require_super_admin` replace a single boolean `role=="admin"` check, but the "no HTTP self-promotion path" rule was kept exactly (`app/scripts/promote_super_admin.py`) |
| Audit log | `AdminActionLog`, append-only, `admin_id`/`action`/`target_user_id`/`details` JSON, written inside the same transaction as the change | **Yes, same shape** (`AuditLog` model, `audit_service.py`) - generalized with `target_type`/`product_id`/`before_state`/`after_state` since Platform Core audits more than just user accounts |
| Gifted/paid distinction | `Subscription.provider` (`"paddle"` vs `"gifted"`), explicit, never inferred from a missing Paddle id (`gift_subscription_service.py`) | **Directly generalized** into `Entitlement.source` (an enum with `paddle`/`gifted`/`promotion`/`trial`/`internal`/`lifetime`/`bundle`/`free`) - same non-inference rule, same "paid blocks gifted" precedence rule (see `ENTITLEMENTS.md`) |
| Revenue/analytics discipline | "Never fabricate financial numbers"; MRR not shown because it can't be computed accurately; gifted counted separately, never summed into paid | **Directly generalized** - Grand Admin's Overview and `BILLING.md` follow the identical philosophy |
| Rate limiting | In-memory sliding-window `RateLimiter`, per-concern instances (login/signup/password-reset), documented as needing a Redis swap before horizontal scaling | **Reused verbatim** (`app/services/rate_limit_service.py`) |
| DB portability | String UUID primary keys (never a DB-specific UUID type), a custom `UTCDateTime` `TypeDecorator` because SQLite silently drops timezone info | **Reused verbatim** (`app/database/sa_types.py` is a byte-for-byte copy of Loady's, `_uuid`-shaped id helpers) |
| Migrations | Alembic, `env.py` reads the app's own `DATABASE_URL` instead of the static `alembic.ini` value, `batch_alter_table` for SQLite ALTER-with-FK | **Reused verbatim pattern** |

Loady's admin panel (`§11` of `COMMERCIAL_ARCHITECTURE.md`) was the direct
template for Grand Admin's authorization posture, audit trail, and "credits
shown to admins are derived, never stored" discipline (Grand Admin's
`entitlement_count`/`gifted_entitlement_count` on `AdminUserOut` are
likewise always computed at read time).

**What was deliberately NOT reused as-is:** Loady's `User.role` is a single
flat string (`"user"`/`"admin"`). Platform Core needed a role that can be
scoped per-product (mission-brief section 17), so RBAC here is a
`RoleAssignment(role_slug, scope)` table instead - see `RBAC.md`.

## 2. Target architecture

```text
                      GRAND ADMIN (admin-frontend/)
                           |  cookie-session, same-origin to Platform Core
                           v
                   PLATFORM CORE API (backend/)
                           |
         +-----------------+-----------------+
         |                 |                 |
      Identity        Entitlements        RBAC / Audit
   (users, sessions,   (product-scoped     (roles, scopes,
    OIDC clients)        plans, sources)     append-only log)
         |                 |                 |
         +-----------------+-----------------+
                           |
      +-------------+------+------+-------------+
      |             |             |             |
   Loady.cc      Gamey.cc      demo-a         demo-b
  (not yet        (not built    (built to     (built to
   integrated,     in V1)        PROVE SSO     PROVE SSO
   see LOADY_                    end-to-end)   end-to-end)
   MIGRATION.md)
```

Every product is an **OIDC client** of Platform Core (mission-brief
section 5) - it never sees a password or a password hash, only:

1. A signed `id_token`/`access_token` pair from `/oauth/token`, verifiable
   via `/.well-known/jwks.json`.
2. Whatever it learns by calling `/api/v1/entitlements/me` with that
   access token as a bearer credential.

Product-specific operational data (Loady's download history, a future
Gamey's game library, etc.) never lives in Platform Core's database and
never will - see `LOCAL_DEVELOPMENT.md` §"Database boundaries" and
mission-brief section 26.

## 3. Directory / project structure

```text
local-media-downloader/
  platform-core/
    backend/            FastAPI app - Identity, SSO/OIDC, Entitlements,
                         RBAC, Audit, Grand Admin API. Own SQLite dev DB,
                         own Alembic history, own venv/requirements.txt.
      app/
        api/            routes_auth, routes_oauth, routes_pages,
                         routes_v1, routes_admin, deps
        security/       passwords, jwt_keys (RSA keypair + JWKS),
                         jwt_tokens, pkce, tokens
        services/       auth, oidc, entitlement, product, rbac, audit,
                         rate_limit, email
        database/       models (all tables), db, sa_types, seed_roles
        models/         enums, Pydantic schemas
        scripts/        promote_super_admin, seed_products,
                         register_demo_clients (all CLI-only, see
                         LOCAL_DEVELOPMENT.md)
      alembic/
      tests/
    admin-frontend/     Grand Admin - Vite + React + TypeScript +
                         Tailwind, EN/AR + RTL, same dark-navy/glass
                         design language as Loady's own admin panel.
    demo-product-a/backend/   Minimal, REAL OIDC client (FastAPI) -
    demo-product-b/backend/   proves cross-product SSO, not a mock.
  docs/platform/        This documentation set.
```

Nothing here touches `local-media-downloader/backend` or
`local-media-downloader/frontend` (Loady itself) - grep confirms zero
modified files outside `platform-core/`, `demo-product-a/`,
`demo-product-b/`, and `docs/platform/` on this branch.

## 4. Threat model summary

See `SECURITY.md` for the full write-up. In short, Platform Core is
treated as the single highest-value target in the whole ecosystem (it is
the one system that, if compromised, compromises every product) and is
reviewed against: password storage, session security, refresh rotation,
the SSO/OIDC exchange itself (PKCE, state, redirect-URI allowlisting,
code single-use/expiry, token audience pinning), CORS, rate limiting,
brute-force/email-enumeration resistance, RBAC/IDOR, service-to-service
auth, secret management, audit-log integrity, and injection classes
(SQL/XSS). One real vulnerability class was found and fixed during this
mission's own live browser testing - a `next`-redirect parameter that was
HTML-escaped but not URL-encoded when embedded in an `<a href>`, which
silently truncated the pending OIDC request at the first `&` rather than
being exploitable, but was still a correctness/robustness bug worth fixing
before it became a security one. See `SSO.md` §"A bug the browser found".

## 5. Documentation set

- `IDENTITY.md` - the central user model, `usr_` ids, sessions.
- `SSO.md` - the OIDC/PKCE flow, endpoint-by-endpoint, and its threat model.
- `ENTITLEMENTS.md` - the generic entitlement system, sources, product scoping.
- `RBAC.md` - roles, scopes, the "no self-escalation" guarantee.
- `BILLING.md` - identity vs. entitlement vs. payment, revenue rules.
- `GRAND_ADMIN.md` - the admin console's API and UI.
- `LOADY_MIGRATION.md` - the (unexecuted) plan to migrate Loady onto this.
- `SECURITY.md` - the full security review.
- `LOCAL_DEVELOPMENT.md` - how to run all five services locally.
