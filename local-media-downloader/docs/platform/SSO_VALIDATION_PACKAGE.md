# SSO Validation Package (Mission 15, Phase 33)

## What's already proven (not re-derived here)

| Property | Tier | Evidence |
|---|---|---|
| Central login (auth-code + PKCE) issues valid tokens | UNIT TEST VERIFIED | `platform-core/backend/tests/test_sso.py` |
| Loady's OIDC callback correctly exchanges the code and links `global_user_id` | UNIT TEST VERIFIED | `backend/tests/test_platform_auth.py` |
| Same account across cross-product SSO resolves to the same `global_user_id` | UNIT TEST VERIFIED | Mission 4's cross-product acceptance suite (task #105) |
| History and usage are unaffected by SSO login (side-column only) | CODE VERIFIED | `platform_identity_service.py` never touches history/usage tables |
| Free/paid/gifted accounts all log in correctly | UNIT TEST VERIFIED | 12 synthetic fixtures (Mission 3, task #98) cover each category |
| Logout/refresh work correctly, including the ~15-minute-bounded cross-product revocation and the now-immediate single-session revoke | UNIT TEST VERIFIED + LOCAL LIVE-STACK VERIFIED | `SESSION_REVOCATION.md`, `SESSION_SECURITY.md`; `test_http_revoke_single_session_immediately_rejects_that_devices_still_unexpired_cookie` |

## What the cutover runbook's SSO TEST step (real production) still needs, and why it's separate

Every item above is proven against synthetic fixtures or a local dev
stack — never against the real production Platform Core + real production
Loady, because neither has been deployed together until the cutover this
document prepares for. The SSO TEST step in
`FINAL_PRODUCTION_CUTOVER_RUNBOOK.md` is the first time this flow runs
against real infrastructure, and its job is narrow and specific:

1. Log in via `https://loady.cc` → central login → Loady callback, using a
   designated staff/test account (see `CANARY_VALIDATION.md`).
2. Confirm the same `global_user_id`, history, and plan as pre-migration.
3. Log out; confirm re-login works.
4. Confirm token refresh works (wait past `ACCESS_TOKEN_TTL_MINUTES`, or
   force a refresh call).

**This is not a re-test of correctness** (already proven above) — it is a
test of *this specific deployment's configuration* (real hostnames, real
signing key, real redirect URI, real TLS). A failure here almost always
means a config mismatch (Phase 22's PLATFORM CORE VERIFICATION step should
have already caught most of these), not a code defect.

## Free/paid/gifted coverage for the real production test

Exercise all three where safe test accounts exist (the canary account plus
any staff accounts of each plan tier) — per Phase 33's explicit
instruction. Do **not** create new real-customer-shaped test accounts
specifically to exercise this; use what's already safely available.
