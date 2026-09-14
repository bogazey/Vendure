# Session Security V2: Sign-Out-All, Single-Session Revoke, Security Events

Mission-brief Phases 21-23. Extends (does not replace)
`SESSION_REVOCATION.md`'s existing account-disable propagation model,
which is unchanged.

## The gap this closes

V1 already had `POST /api/v1/auth/logout-all`, which revoked every
central `RefreshToken` row. What it did **not** do: invalidate an
already-issued, still-unexpired central `session_access` JWT (a stateless
token - revoking the refresh token only stops it being *renewed*), or
touch product-scoped `OAuthRefreshToken` rows at all. A stolen or
still-open central session cookie kept working for up to
`ACCESS_TOKEN_TTL_MINUTES` (default 15) after a user clicked "sign out
everywhere," and any product holding a refresh token for that user could
keep silently minting fresh OIDC access tokens indefinitely.

## The fix: a per-user security epoch

```text
users.security_epoch  (integer, default 1)
```

- `create_session_access_token(user_id, security_epoch)` bakes the
  epoch-at-issuance into the JWT (`"epoch"` claim).
- `api/deps.py::get_optional_user` rejects a token whose `epoch` claim
  doesn't match the user's *current* `security_epoch` - checked on every
  request, using the same DB read `get_optional_user` already does to
  load the user, so this costs nothing extra.
- `auth_service.logout_all_sessions` does three things atomically:
  1. Revoke every central `RefreshToken`.
  2. Revoke every product-scoped `OAuthRefreshToken` for that user
     (across every client/product - a Platform Core table, no product
     code touched).
  3. Increment `security_epoch`.

Verified end-to-end through the real HTTP cookie-auth dependency chain
(not just the service function) in
`test_session_security_v2.py::test_http_logout_all_rejects_a_previously_valid_still_unexpired_cookie`:
a cookie captured before "sign out everywhere," re-presented afterward,
is rejected (`401`) despite being correctly signed and not yet expired.

## Documented, bounded SLA (never claimed as instant)

| Session type | Propagation |
|---|---|
| Central `session_access` cookie (Grand Admin / future account portal) | **Immediate** - rejected on its very next use, regardless of remaining TTL. |
| Central `RefreshToken` | Immediate (revoked synchronously). |
| Product `OAuthRefreshToken` | Immediate (revoked synchronously) - a product cannot silently renew after this call. |
| A product's already-issued OIDC **access** token | Up to `OIDC_ACCESS_TOKEN_TTL_MINUTES` (default 15) - the same bounded-propagation precedent `SESSION_REVOCATION.md` already established for account disable. Not fixed further in this mission because doing so would require either (a) a product checking a live status/epoch endpoint on every single request (defeating the point of a short-lived stateless access token), or (b) modifying Loady's own integration code, which this mission does not touch. |

## Single-session revoke (Phase 21)

`DELETE /api/v1/auth/sessions/{session_id}` - IDOR-safe by construction:
`auth_service.revoke_session` looks the row up by `(id, user_id)`
together in one query, never `id` alone followed by a separate ownership
check a future refactor could drop. Verified by
`test_revoke_session_is_idor_safe_across_users`. Returns success either
way (no 404 distinction between "doesn't exist" and "belongs to someone
else") to avoid leaking session-id existence, matching this codebase's
existing "never reveal whether the account exists" convention
(`request_password_reset`).

## Password change with optional session revocation (Phase 20)

`POST /api/v1/auth/change-password` gained `revoke_other_sessions: bool
= false` (opt-in, not automatic - a UX decision left to the caller, per
the mission brief's "define whether other sessions revoke... recommended:
offer/recommend"). When set, the caller's *own* current session is
re-issued immediately afterward so the person who just changed their own
password isn't logged out by their own action - verified by
`test_change_password_with_revoke_other_sessions_keeps_caller_signed_in`.

## Security events (Phase 23)

`GET /api/v1/me/security-events` - a small, explicit allowlist of
`AuditLog` actions (`user_signup`, `user_login`, `password_changed`,
`session_revoked`, `all_sessions_revoked`) filtered to the caller's own
`actor_user_id`, never another user's. No raw technical log, no tokens,
no secrets - exactly the "recent security activity" surface the mission
brief describes, with no UI built on top of it yet.

## What is NOT built

- No device/browser/OS metadata enrichment on `RefreshToken.device_label`
  (still just a plain nullable string a caller may optionally set - no
  user-agent parsing was added).
- No "new product authorized" security event (would require instrumenting
  `product_service.touch_membership`, not done in this pass).
- No account-portal UI for any of this (`GET /api/v1/auth/sessions`
  already existed from V1 and, combined with the new `DELETE .../sessions/
  {id}`, is a complete API for a "Sessions/Devices" screen - no screen
  was built).
