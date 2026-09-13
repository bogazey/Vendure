# Central Identity

## The global user

`app/database/models.py::User` is the one, permanent, cross-product
identity (mission-brief section 4 / section 46: "one human -> one global
identity"). Its primary key is `id`, an immutable `usr_<uuid4 hex>` string
(`_global_user_id()`), **never** the email address. Email is stored as a
unique, indexed *attribute* that can be changed later (no such endpoint
exists in V1, but nothing in the schema prevents adding one - every other
table references `user_id`, never `email`).

```text
users
  id              usr_1a173541446c4c80bd6852f0aad585da   (immutable)
  email           alice@example.com                      (attribute, unique)
  password_hash   $argon2id$v=19$...
  email_verified  bool
  status          active | disabled
  created_at / updated_at
```

## Password storage

Argon2id via `argon2-cffi`'s `PasswordHasher`, the exact library and
default parameters Loady's `security_service.py` already uses in
production - reused verbatim (`app/security/passwords.py`), per the
mission's "reuse good existing security patterns" and "do not roll your
own crypto" rules. `needs_rehash()` is checked on every successful login
so a future parameter upgrade migrates existing hashes lazily, exactly
like Loady.

## Sessions

A **central session** is a short-lived RS256 JWT access token
(`plat_session_access` cookie, 15 min TTL) plus a longer-lived opaque
refresh token (`plat_session_refresh` cookie, 30 days, httpOnly,
`SameSite=Lax`). Only the refresh token's SHA-256 hash is ever persisted
(`RefreshToken.token_hash`) - a stolen DB row alone cannot be replayed.

Every `RefreshToken` row doubles as a **session record** (mission-brief
section 23): `id`, `created_at`, `last_used_at`, `expires_at`,
`revoked_at`, `remember_me`, `device_label`. `GET /api/v1/auth/sessions`
lists a user's own active sessions (marking which one is "current" by
comparing the presented cookie's hash) - the foundation for a future
account-portal "active sessions" screen. `POST /api/v1/auth/logout-all`
revokes every session at once ("sign out all devices").

**No raw IP address is ever stored** (mission-brief section 23) - the
session table has no IP column at all, only `device_label`, which nothing
currently populates automatically (a future UA-parsing pass, exactly like
Loady's own `ua_parse.py`, would populate it without ever needing a raw
IP).

A password reset revokes every `RefreshToken` for that user immediately
(`auth_service.reset_password` -> `logout_all_sessions`), matching Loady.
An already-issued *access token* JWT remains valid until its own short,
natural expiry - the same accepted stateless-JWT trade-off Loady's own
`reset_password` makes; the next `/api/v1/auth/refresh` call is what
actually fails once the refresh token is revoked (see
`tests/test_identity.py::test_password_reset_revokes_existing_sessions`).

## Signup / login / verification / reset

Endpoints under `/api/v1/auth/*`
(`app/api/routes_auth.py`), directly mirroring Loady's own
`routes_auth.py` shape: `signup`, `login`, `logout`, `logout-all`,
`refresh`, `me`, `sessions`, `change-password`, `forgot-password`,
`reset-password`, `verify-email`, `resend-verification`. Rate-limited the
same way Loady rate-limits its equivalents (`rate_limit_service.py`):
signup 10/hour/IP, login 10/5min/IP+email, password-reset/verification
5-10/hour.

Email verification and password reset use the same single-use,
SHA-256-hashed, expiring token pattern as Loady
(`app/security/tokens.py::generate_hashed_token`). **No production email
service is configured** (mission-brief section 21) - `email_service.py`
only logs what it would send; a real deployment would add a
Resend/SES/Postmark backend behind the same two function signatures.

## What products never receive

A product only ever sees, via the OIDC exchange (`SSO.md`): the user's
`sub` (the immutable `usr_...` id), `email`, `email_verified`. It never
receives `password_hash`, a central session cookie, or any Platform-Core-
internal token. This is structural, not a convention to remember - the
`id_token`/`access_token` schemas (`security/jwt_tokens.py`) simply don't
carry those fields.

## MFA and passwords: what V1 does not build, and why it still fits

Mission-brief section 22 asks for MFA *readiness*, not MFA itself. Nothing
in the `User` model or auth flow assumes a single factor is the only ever
factor: `AuthResult`/`_issue_session` are the one chokepoint every
successful authentication passes through, so adding a
"has TOTP -> require second step before issuing a session" branch there
later does not require touching `routes_auth.py`, `oidc_service.py`, or
any product-facing contract. Recovery codes and WebAuthn credentials would
be new tables referencing `User.id`, the same shape as `RefreshToken` -
no schema redesign implied. Grand Admin requiring *stronger* auth than an
ordinary user (mission-brief section 22) is likewise a policy check to add
at the `require_super_admin`/`require_global_admin` dependency layer, not
a new identity model.
