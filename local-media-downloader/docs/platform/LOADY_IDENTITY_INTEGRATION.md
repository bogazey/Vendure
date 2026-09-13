# Loady's Central Identity Integration (built and locally verified this mission)

Everything in this document describes code that actually exists and was
actually run, on branch `unified-platform-v1`, entirely against local
test data. **Loady's existing local authentication is completely
unmodified and remains the default in every environment**, including
production — this integration is dormant until someone deliberately sets
`PLATFORM_CLIENT_ID`/`PLATFORM_CLIENT_SECRET`.

## 1. What was built

| File | Role |
|---|---|
| `backend/app/services/platform_identity_service.py` | Loady's OIDC *client* adapter: PKCE generation, authorize-URL building, code exchange, JWKS-verified id_token validation. |
| `backend/app/api/routes_platform_auth.py` | `GET /api/auth/platform/status`, `/login`, `/callback` — the only HTTP surface of this integration. |
| `backend/app/services/platform_entitlement_service.py` | Server-side, authoritative entitlement retrieval from Platform Core — a proven **capability**, deliberately not wired into the live download gate (see §5). |
| `backend/app/database/commercial_models.py` | `User.global_user_id` (nullable, unique) + new `PlatformOidcToken` table. |
| `backend/alembic/versions/8a1e5c3f9b02_*.py`, `9c3d7f1a4e56_*.py` | The two additive migrations for the above. |
| `frontend/src/pages/auth/Login.tsx` | One conditionally-rendered button, "Sign in with Central Identity", shown only when `/api/auth/platform/status` reports `{"enabled": true}`. |

Same real Authorization Code + PKCE (S256) protocol already proven with
`platform-core/demo-product-a` and `demo-product-b` — this is Loady's own
copy of that pattern, not a new one.

## 2. Configuration

```
PLATFORM_AUTH_BASE_URL=http://localhost:8100      # Platform Core's own base URL
PLATFORM_API_BASE_URL=http://localhost:8100
PLATFORM_CLIENT_ID=loady                          # from register_loady_client.py
PLATFORM_CLIENT_SECRET=<printed once at registration>
PLATFORM_REDIRECT_URI=http://localhost:8000/api/auth/platform/callback
```

`platform_identity_service.is_configured()` is `bool(client_id and
client_secret)` — empty `PLATFORM_CLIENT_ID` (the default) is the dormancy
switch. `routes_platform_auth.py`'s `_require_configured()` 404s both
routes outright when unconfigured, verified in
`backend/tests/test_platform_auth.py::TestDormantByDefault` and live in
this mission's own local run (`{"enabled": false}` before configuration,
`{"enabled": true}` after — see `LOADY_MIGRATION_DRY_RUN.md` §4).

No production domain or `localhost` is hard-coded into any business-logic
path — every URL above is settings-driven
(`backend/app/config/commercial_settings.py`).

## 3. The login flow

1. `GET /api/auth/platform/login?next=<safe-relative-path>` — generates a
   PKCE verifier/challenge and a `state`, stores all three plus the
   validated `next` path in three short-lived (300s), httpOnly,
   `SameSite=Lax` cookies, and 302s to Platform Core's
   `/oauth/authorize`.
2. Platform Core redirects to its own `/login` page if the browser has no
   central session yet, or straight back with a `code` if it does (this
   second case is exactly what makes cross-product SSO work — proven live
   in `LOADY_MIGRATION_DRY_RUN.md` §5).
3. `GET /api/auth/platform/callback?code=...&state=...` — validates
   `state` against the cookie, exchanges the code server-side
   (`exchange_code_for_tokens`, never exposed to the browser), verifies
   the returned `id_token`'s RS256 signature via Platform Core's own JWKS,
   issuer, and audience (`verify_id_token`), resolves/links the local
   Loady account (§4), stores the OIDC token pair via
   `platform_entitlement_service.store_tokens`, and finally issues
   **Loady's own local session** through the exact same
   `auth_service._issue_session` / `_set_session_cookies` machinery every
   other Loady login already uses.

No password, no Platform Core password hash, and no central refresh token
is ever sent to Loady's browser JavaScript at any point — the only things
that ever reach the browser are Loady's own httpOnly session cookies,
exactly as before this integration existed.

## 4. Account linking (the safety-critical part)

`_find_or_link_local_user()` in `routes_platform_auth.py`:

1. **Match by `global_user_id` first, always.** This is the only lookup
   used in steady state.
2. **Email is used exactly once per Loady account**: only when
   `global_user_id IS NULL` (this Loady row has never been linked before)
   does a matching email cause a link — `global_user_id` is written onto
   the *existing* Loady row, nothing is duplicated.
3. **Any email match where `global_user_id` is already set to something
   else raises `ForbiddenError` (403)** — a hard refusal, reported to the
   caller, never a silent merge. Verified in
   `test_platform_auth.py::test_email_collision_with_a_different_linked_account_is_refused`
   and live in `LOADY_MIGRATION_DRY_RUN.md`'s migration report's
   `conflicted` bucket.
4. **No match at all** creates a brand-new local Loady account with a
   locked, never-typeable random Argon2 password hash
   (`secrets.token_urlsafe(48)`) — this account can only ever be reached
   through central identity, by design.

## 5. Entitlement retrieval — a proven capability, not a live gate

`platform_entitlement_service.get_authoritative_entitlement()` correctly
calls Platform Core's `/api/v1/entitlements/me` with the stored access
token (refreshing it once on expiry or a single 401), and returns `None`
— "unknown", never "not entitled" — on any failure. This function is
fully unit-tested but **is not called anywhere in Loady's existing
`entitlement_service`/`plan_policy`/`download_gate_service`**, which
continue to gate every real download exactly as they did before this
mission. This is a deliberate scope decision (see the module's own
docstring): swapping the live gate to depend on Platform Core's
availability on every download request is a real availability regression
(Platform Core being briefly unreachable must never block Loady's own
paying users), and is listed as a blocker in
`LOADY_PRODUCTION_MIGRATION_PLAN.md`, not silently done in this mission.

## 6. Sign-out semantics

"Sign out of Loady" (Loady's existing `POST /api/auth/logout`) terminates
**only** Loady's own local session — completely unmodified by this
mission. It does **not** end the Platform Core central session, and it
does not revoke the stored `PlatformOidcToken` row. A future "sign out of
all products" would need a new, separate, deliberately-built mechanism
(Platform Core would need to track which products a session touched and
call each one back) — **this does not exist today, in Platform Core or in
Loady, and this mission does not claim otherwise.**

## 7. Known limitation: centrally-disabled status is checked at login time, not continuously

A user disabled centrally (`User.status = "disabled"` in Platform Core)
cannot **start a new** central login (Platform Core's own
`/api/v1/auth/login` and `oidc_service.exchange_authorization_code` both
reject non-active users — verified live in
`LOADY_MIGRATION_DRY_RUN.md` §6) and cannot obtain a new Loady session
through this integration (`platform_callback` also independently checks
the *linked local* Loady account's own status). However, an **already
open** Loady browser session (issued before the disable) is not
force-revoked by this integration — Loady has no live session-revocation
push mechanism today, centrally-driven or otherwise, and this mission
does not build one. That session still expires on its own normal TTL.
