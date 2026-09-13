# Security Review

Platform Core is treated as the single highest-value target in the
ecosystem (mission-brief section 37): compromising it compromises every
product's identity layer. Reviewed against every item mission-brief
section 37 names, in order.

## Password storage

Argon2id via `argon2-cffi`, reused verbatim from Loady's own proven
implementation (`app/security/passwords.py`) - no custom hashing.
`needs_rehash()` checked on every login. Login timing is equalized
between "unknown email" and "wrong password" (`auth_service.login`
always runs the hasher) to resist email enumeration via timing.
**Verdict: no change needed from Loady's already-sound approach.**

## Session security / refresh rotation

Central-session access tokens are short-lived (15 min), httpOnly,
`SameSite=Lax`, RS256-signed. Refresh tokens are opaque, only their
SHA-256 hash is stored, and rotate on every use - a leaked-and-reused
refresh token is detectable (the old hash is already revoked) and its
blast radius is bounded to one rotation cycle. `logout-all` revokes every
session at once. No raw IP is ever persisted (mission-brief section 23).
**Verdict: matches Loady's proven pattern; no weaker than the original.**

## SSO / OAuth / OIDC / PKCE

Full write-up in `SSO.md`. Summary of what was specifically checked and
how, per mission-brief section 24's named threats:

| Threat | Verified by |
|---|---|
| Authorization-code interception/replay | `tests/test_sso.py::test_authorization_code_is_single_use` |
| Missing PKCE | `tests/test_sso.py::test_authorize_requires_pkce_s256` |
| CSRF/state | Demo clients verify `state` themselves (`demo-product-a/backend/app.py::auth_callback`); Platform Core stores and echoes it opaquely |
| Open redirect | `tests/test_sso.py::test_authorize_rejects_unregistered_redirect_uri` - exact-match only, error page (not a redirect) on failure |
| Redirect URI manipulation | Same test; also covered live (three-process `httpx` run in `SSO.md`) |
| Token leakage | Cookies httpOnly; OIDC tokens only in a same-origin POST response body, never a URL |
| Refresh-token replay | `tests/test_identity.py::test_refresh_rotates_session` (central); OIDC refresh tokens are per-client, checked in `oidc_service.refresh_oidc_token` |
| Session fixation | No code path accepts a caller-supplied session/refresh id |
| Weak signing keys | RS256, 2048-bit, `cryptography` library, never HS256 for anything cross-service |
| Cross-product token misuse | `tests/test_sso.py::test_access_token_audience_is_pinned_to_client` |

**One real bug was found and fixed** during this review's own live browser
testing (not by static review) - see `SSO.md` §"A bug the browser found":
the `next` redirect parameter was HTML-escaped but not URL-encoded when
embedded in an `<a href>`, silently truncating the pending SSO request at
the first `&`. Not itself an authentication bypass (the request was lost,
not redirected anywhere attacker-controlled - `_safe_next` still only ever
accepted a same-path `/oauth/authorize?...` value), but a real correctness
bug with security-adjacent blast radius (a broken SSO flow that fails
open toward "start over" is fine; one that fails toward "redirect
somewhere unintended" would not have been). Fixed and covered by a
regression test (`tests/test_pages.py`).

## CORS

`app/main.py`'s `CORSMiddleware` uses an explicit local-dev origin
allowlist (`allow_credentials=True` requires this - Starlette refuses
`"*"` with credentials, same as Loady's own CORS posture), never a
wildcard.

## Rate limiting / brute-force protection

Reused Loady's exact `RateLimiter` pattern
(`app/services/rate_limit_service.py`) - sliding-window, per-concern
instances for login/signup/password-reset/token-exchange. Documented (in
the module itself, like Loady's) as needing a Redis-backed limiter before
horizontal scaling.

## Email enumeration

`forgot-password` never reveals whether an account exists
(`auth_service.request_password_reset` returns silently either way,
exactly like Loady). Login's timing-equalization (above) closes the
timing side-channel too.

## Admin authorization / RBAC / IDOR

Every `/api/v1/admin/*` route requires at least `require_global_admin`;
role/client management additionally requires `require_super_admin` -
re-resolved from the DB on every single request, not cached, not trusted
from a client-supplied header or claim. Verified live over real HTTP, not
just unit-tested in isolation:
`tests/test_admin.py::test_anonymous_denied_overview`,
`test_ordinary_user_denied_overview`,
`test_product_scoped_role_does_not_grant_global_admin`. IDOR: every
admin endpoint takes a `user_id`/`product_id` path parameter and looks up
exactly that row - there is no implicit "current user" fallback that
could be confused with an admin acting on someone else's data, and no
endpoint trusts a client-supplied `user_id` for anything other than "which
row to act on" (the *acting* identity always comes from the verified
session, never the URL).

## Service-to-service auth

No single shared API key (mission-brief section 25) - each product is a
separately-registered `OAuthClient` with its own `client_secret_hash`
(Argon2, never stored plaintext) and its own exact-match redirect URI
allowlist, independently deactivatable (`is_active`).

## Token signing / secret management

RS256 via `cryptography`, private key generated locally and gitignored
(`data/*.pem`), never committed. `COOKIE_SIGNING_KEY` and the JWT signing
key both fall back to a randomly generated value per-process if unset,
never a fixed "dev" constant that could accidentally mean something in a
real deployment - same posture as Loady's `SECRET_KEY`. No demo client
secret is committed to git either - `.env.example` files ship placeholder
text only, real `.env` files are gitignored (`local-media-downloader/
.gitignore`'s `platform-core/**`/`demo-product-*/**` entries added by this
mission).

## Audit log integrity

Append-only by construction - no update/delete endpoint exists for
`AuditLog` rows anywhere in `routes_admin.py`. Every write happens inside
the same transaction as the change it records, so there is no window
where a change succeeds but goes unaudited (or vice versa).
`before_state`/`after_state` are always small, explicitly-constructed
dicts passed by the calling service - never a raw ORM object dump - which
structurally prevents a password hash, token, or raw payment detail from
ever reaching the log (`tests/test_audit.py::
test_audit_log_never_stores_secrets_or_password_hashes` verifies this by
inspecting real audit rows written by real API calls, not by inspecting
the code alone).

## SQL injection

100% SQLAlchemy ORM/Core `select()` construction throughout - no raw SQL
string formatting anywhere in this codebase.

## XSS

The hosted `/login`/`/signup` pages are the only server-rendered HTML in
Platform Core; user-controlled input (`next`) is escaped for its actual
embedding context (URL-encoded for an `href`, JSON-encoded for a `<script>`
string - see `SSO.md`'s bug writeup for why getting this distinction wrong
matters) rather than a single blanket HTML-escape. The Grand Admin
frontend is a React SPA - React escapes all rendered text by default, and
this codebase introduces no `dangerouslySetInnerHTML` anywhere.

## Sensitive logging

`app/config/logging_config.py`'s logger is used for operational messages
only (signup/login events by user id, never a password or token). The
dev-only `email_service.py` logs the *verification/reset URL* it would
send - acceptable in a `log` backend explicitly reserved for local
development (mission-brief section 21), never wired to run against
production.

## Account linking / privilege escalation

No account-linking feature exists in V1 to review (out of scope,
correctly not built). Privilege escalation is covered under RBAC above -
the `RoleAssignment(scope)` design structurally prevents a product-scoped
role from ever being read as a global one (`RBAC.md`).

## Race conditions

The Grand Admin paid-precedence check
(`_reject_if_paid`-equivalent in `entitlement_service`/`routes_admin.py`)
re-reads the live `Entitlement` row inside the same request transaction
as the write it's guarding, so a webhook or another admin action landing
between the check and the write is still seen (this mirrors Loady's own
`gift_subscription_service._reject_if_paid` precedent exactly). No
payment webhook exists yet in Platform Core to race against in V1 (no
live processor is wired - `BILLING.md`) - this is noted as a "verified
correct for what exists today, re-verify when a real webhook is added" item
under Known Limitations below.

## Known limitations (honestly stated, not hidden)

- No MFA implemented (readiness only - `IDENTITY.md`).
- No live payment processor wired - `PaymentRecord` is a schema boundary,
  not an integration (`BILLING.md`).
- The hosted `/login`/`/signup` pages are English-only in V1 (Grand Admin
  itself is fully EN/AR/RTL; the central login page was not, per the
  mission's scope-control instruction to keep V1 focused).
- No explicit user-consent screen on `/oauth/authorize` - acceptable for
  first-party demo clients under this project's own control, but a real
  third-party product integration should add one before going live.
- OAuth client secret rotation has no dedicated endpoint yet (only
  register-once); `is_active=false` deactivation exists in the schema and
  is checked everywhere but has no admin UI/endpoint to flip it yet.
