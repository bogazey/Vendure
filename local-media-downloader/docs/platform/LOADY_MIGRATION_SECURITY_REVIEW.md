# Loady ↔ Platform Core Integration: Security Review

Scope: the Loady-specific integration built this mission
(`routes_platform_auth.py`, `platform_identity_service.py`,
`platform_entitlement_service.py`, `loady_migration_service.py`,
`loady_migration_dry_run.py`) and how it uses the OAuth/OIDC primitives
Platform Core already implements. Every item below was checked against
the actual code (file:line cited), not assumed; several were additionally
verified live in `LOADY_MIGRATION_DRY_RUN.md`.

## Findings

### FINDING 1 (fixed this mission): migration failure reports could leak an Argon2 password hash

**Severity**: Medium (local-tooling-only exposure, not a live attack
surface, but a real secret-handling defect).

`loady_migration_service.py`'s exception handlers originally recorded
`str(exc)` as the failure `reason`, printed verbatim by
`loady_migration_dry_run.py`. Reproduced directly: a SQLAlchemy
`IntegrityError`'s default `__str__` embeds the failing statement's
**bound parameters** — for the phase-1 user-creation `INSERT`, that
includes the migrated user's real Argon2id `password_hash`.

```
str(exc) contains secret? True
(sqlite3.IntegrityError) UNIQUE constraint failed: u.email
[SQL: INSERT INTO u (id, email, password_hash) VALUES (?, ?, ?)]
[parameters: ('2', 'a@example.com', 'ANOTHER-SECRET-HASH')]
```

**Fix**: `_safe_error_reason()`
(`platform-core/backend/app/services/loady_migration_service.py`) uses
`exc.orig` — the underlying DBAPI exception, which carries only the
driver's own message ("UNIQUE constraint failed: ...") — for any
`sqlalchemy.exc.StatementError`, never the statement or its parameters.
Applied to both exception sites (phase 1 identity resolution, phase 2
memberships/entitlements). Regression test:
`test_safe_error_reason_never_includes_a_password_hash` in
`tests/test_loady_migration.py`, passing (64/64 Platform Core tests
green after the fix).

This does not affect a live attack surface (the migration script is
CLI-only, run by an operator, never web-reachable), but a password hash
sitting in shell scrollback, a redirected log file, or a copy-pasted
report is exactly the kind of secret the mission's "no secrets should be
committed"/"passwords are never logged" requirements exist to prevent, so
it is treated as a real finding rather than dismissed.

## Checklist — verified, no other findings

| Item | Verified against | Result |
|---|---|---|
| OAuth `state` validation | `routes_platform_auth.py` `platform_callback`: missing/mismatched state cookie → 400 before any token exchange. `test_platform_auth.py::TestCallbackStateValidation` (2 tests). | Pass |
| PKCE (S256) | `platform_identity_service.generate_pkce_pair`/`build_authorize_url`; Platform Core's `oidc_service.validate_authorize_request` rejects any `code_challenge_method != "S256"`. | Pass |
| Authorization code replay | `oidc_service.exchange_authorization_code`: `record.used_at` set unconditionally before any token is issued, checked (`used_at is not None`) on every exchange attempt — comment notes this closes the concurrent-replay race too. | Pass (Platform Core, exercised by Loady's live flow) |
| Redirect URI exact matching | `validate_authorize_request`: `redirect_uri not in client.redirect_uris` (exact set membership, not prefix); `exchange_authorization_code`: `record.redirect_uri != redirect_uri` re-checked at exchange time. | Pass |
| Open redirects | `routes_platform_auth._safe_next`: only a path starting with `/` and not `//` and containing no `://` is ever accepted; anything else silently falls back to `/dashboard`. 8-case parametrized test incl. `//evil.com`, `https://evil.com`, `javascript://evil`. | Pass |
| CSRF | The `state` parameter is the relevant control for the OAuth redirect itself (covered above); Platform Core's own login POST is a same-origin `fetch(..., credentials:'include')` call, not a plain cross-site-postable form. | Pass |
| Cookie flags | Loady's 3 transfer cookies (`plat_pkce_verifier`, `plat_pkce_state`, `plat_next`): `httponly=True`, `secure=settings.cookie_secure` (same production-driven flag as every other Loady cookie), `samesite="lax"`, `max_age=300`. Loady's own resulting session cookies use the pre-existing, unmodified `_set_session_cookies`. | Pass |
| Token audience | `verify_id_token`: `jwt.decode(..., audience=settings.platform_client_id, ...)` — a token minted for a different client is rejected. `test_wrong_audience_rejected`. | Pass |
| Token issuer | Same call, `issuer=settings.platform_auth_base_url`. `test_wrong_issuer_rejected`. | Pass |
| Token expiration | PyJWT's own `exp` check inside `jwt.decode`. `test_expired_token_rejected` (a token minted with `expires_in=-60`). | Pass |
| JWT signature / JWKS | `verify_id_token` fetches the JWKS, matches `kid`, and rejects an unknown `kid` outright (`test_unknown_kid_rejected`) before ever attempting signature verification with the wrong key. | Pass |
| User/account enumeration | The only Loady-side response that reveals account state is the 403 collision case, which requires the caller to already hold a valid central session for the exact colliding email — not a guessing primitive. Platform Core's own login already returns the same error for "no such user" and "wrong password" (pre-existing, unmodified). | Pass |
| Account-linking takeover | `_find_or_link_local_user`: email-based linking only fires when the target Loady row's `global_user_id IS NULL`; any other email match is a hard 403, never a merge. `test_email_collision_with_a_different_linked_account_is_refused`. | Pass |
| Email collision | Same mechanism as above. | Pass |
| Disabled users | Checked in three independent places: Platform Core's own login (`AccountDisabledError`), Platform Core's code-exchange (`user.status != "active"` → `InvalidGrantError`), and Loady's own callback (`user.status != UserStatus.ACTIVE.value` → 403). Verified live end-to-end (`LOADY_MIGRATION_DRY_RUN.md` §5 item 5) and unit-tested (`test_disabled_local_account_cannot_start_a_new_session_via_central_login`). | Pass |
| Deleted users | Loady has no hard-delete for user accounts (only disable) — not reachable. Platform Core's `exchange_authorization_code` defensively handles `user is None` (`InvalidGrantError`) regardless. | Pass / N/A |
| Entitlement spoofing | Loady never reads a "plan" or "entitlement" claim from the id_token at all — the only claims consumed are `sub`/`email`/`email_verified`, all signature-verified. `platform_entitlement_service` always re-asks Platform Core server-side rather than trusting anything client-supplied. | Pass |
| Privilege escalation | Migrated admins get `RoleAssignment(role_slug=ADMIN, scope="product:loady")`. `rbac_service.is_global_admin` only ever checks `scope == GLOBAL_SCOPE` — confirmed by reading the function directly — so a product-scoped assignment can never satisfy a global-admin check. Verified against the real migrated row in the live run. | Pass |
| IDOR on download history | Unchanged: history rows are still scoped by Loady's own existing `user.id`-based auth dependency; this integration only changes *how* that `user` is resolved (central login vs. local password), never *what* it's allowed to see. Live-verified: the migrated user's own history row, and only that row, was visible after central login. | Pass |
| Admin scope isolation | See "Privilege escalation" row — same mechanism, confirmed via direct DB query in the live run (`role_slug='admin', scope='product:loady'`). | Pass |
| Leaking Paddle identifiers | `loady_migration_service.py` never reads `provider_customer_id`/`provider_subscription_id` from Loady's `subscriptions` table into anything written to Platform Core; `Entitlement` has no column for either. Confirmed by inspecting `entitlement_service.grant_or_change`'s full field list and by querying the live Platform Core database (`payment_records` count = 0; no Paddle id anywhere in `entitlements`). | Pass |
| Logging secrets/tokens/passwords | Every `logger.warning` call in `platform_identity_service.py`/`platform_entitlement_service.py` logs only an HTTP status code or a generic `httpx.HTTPError`/`jwt.PyJWTError` object — never a token, secret, or password value. Grepped directly, confirmed. | Pass |
| Migration script output containing sensitive values | See Finding 1 above (fixed). Aside from that, the printed report fields are `loady_user_id`, `email`, `global_user_id`, `entitlement_source`, `plan` — no password hash, no Paddle identifier, ever. | Fixed |

## Not applicable / out of scope for this integration

- Platform Core's own signup/login rate limiting, password-reset flow,
  and JWKS key rotation were built and reviewed in an earlier mission
  (`SECURITY.md`) and were only *exercised* here, not re-audited from
  scratch — this review focuses on the Loady-specific surface.
- Ecosystem-wide logout does not exist (`LOADY_IDENTITY_INTEGRATION.md`
  §6), so "logout doesn't propagate" is a documented limitation, not a
  vulnerability to fix here.
