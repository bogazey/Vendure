# Production Security Review (Mission 15, Phase 44)

Fresh, static/local review against current source — re-checks every item
Phase 44 lists, rather than re-citing a prior mission's review without
verification. Where a prior mission's finding is simply re-confirmed
unchanged, that's stated explicitly; genuinely new checks are marked as
such.

| Area | Finding | Tier |
|---|---|---|
| OAuth `state` parameter | Generated per-authorize-request, verified on callback (`routes_platform_auth.py`/`oidc_service.py`) | UNIT TEST VERIFIED |
| PKCE | S256 challenge/verifier enforced, no plain fallback | UNIT TEST VERIFIED (`test_sso.py`) |
| Issuer/audience | JWT `iss` checked against `PLATFORM_AUTH_BASE_URL`; audience scoped per client | UNIT TEST VERIFIED |
| JWKS | Served at `/.well-known/jwks.json`; overlap-based rotation supported (`KEY_ROTATION_RUNBOOK.md`) | UNIT TEST VERIFIED + validated this mission (JWKS route present in the reverse-proxy config, `PRODUCTION_REVERSE_PROXY_REVIEW.md`) |
| JWT algorithm | RS256 only, confirmed no `alg: none`/HS256-confusion path in `jwt_keys.py` | CODE VERIFIED |
| Cookies | `httpOnly`, `SameSite=Lax`, `Secure` in production (`routes_auth.py`, read directly this mission) | CODE VERIFIED |
| CSRF | `SameSite=Lax` is the primary defense (no separate CSRF-token middleware) — standard, adequate for a cookie+bearer hybrid API where state-changing requests aren't triggered by simple cross-site form posts; no gap found relative to this architecture's actual attack surface | CODE VERIFIED |
| **CORS** | **Re-confirmed genuine gap, documented not fixed this mission**: `app/main.py`'s `CORSMiddleware` allowlist is hardcoded to localhost dev ports only, not environment-configurable. Accepted for V1 (no real cross-origin browser SPA needs it yet — Account Portal/Grand Admin become same-origin after the Phase 12 reverse-proxy fix); a real gap for any *future* product onboarding with its own cross-origin frontend | DOCUMENTED ONLY — tracked in `PRODUCTION_ENVIRONMENT_INVENTORY.md`, not silently fixed (would be new configuration surface, arguably in scope but deferred as non-blocking for this specific V1 cutover) |
| Host header trust | No `TrustedHostMiddleware` in either backend — the reverse proxy (nginx, `server_name`-scoped virtual hosts) is the actual trust boundary; a request that reaches `platform-core-backend` at all has already been routed by hostname at the edge | CODE VERIFIED (architecture-level, not application-level enforcement — acceptable given the single-edge design) |
| Forwarded headers | `X-Forwarded-For`/`X-Forwarded-Proto`/`X-Real-IP` set correctly at the edge (`nginx.production.conf.template`, confirmed this mission); Cloudflare real-IP restoration list present and current as of this mission's writing | CODE VERIFIED |
| Service auth (Loady ↔ Platform Core) | Existing mechanism, `SERVICE_AUTH.md`, unchanged | DOCUMENTED / prior UNIT TEST VERIFIED |
| Admin authorization | RBAC scoping tested (`test_admin.py`); product-scoped admin cannot escalate to global | UNIT TEST VERIFIED |
| Product scoping | `/api/v1/entitlements/me`/`/capabilities/me` both reject a caller with no `product_id`, and scope strictly to the caller's own product (`MISSION_7_ARCHITECTURE_AUDIT.md` §2, re-confirmed by reading the route code) | CODE VERIFIED |
| IDOR | Every admin lookup route scopes by the authenticated admin's own product membership before returning data (`test_admin.py`); no route found this mission that accepts a raw foreign-key id without a scoping check | CODE VERIFIED (spot-checked `routes_admin.py`'s admin-facing endpoints) |
| Entitlement spoofing | Bearer-scoped, server-resolved only (`resolve_effective_entitlements`) — no client-supplied plan/entitlement value is ever trusted | CODE VERIFIED |
| Billing webhook verification | HMAC-SHA256 signature check, fail-closed on missing/wrong secret (`paddle_provider.py::verify_webhook`) | UNIT TEST VERIFIED + SANDBOX VERIFIED |
| Replay/idempotency | `BillingWebhookEvent(provider, provider_event_id)` unique constraint; redelivery proven never double-applies (`PADDLE_WEBHOOK_EVENT_MATRIX.md`) | UNIT TEST VERIFIED |
| **Secret leakage** | **Genuine defect found and fixed this mission** — Platform Core's email service unconditionally logged real password-reset/verification tokens; fixed, tested (`PRODUCTION_LOGGING_REVIEW.md`) | FIXED, UNIT TEST VERIFIED |
| Migration takeover | `loady_migration_service` matches by immutable `global_user_id` first, then email; a conflicting match is reported, never silently resolved in favor of an attacker-controllable value | UNIT TEST VERIFIED |
| Email collisions | Explicitly tested via the 12 synthetic fixtures (Mission 3) | UNIT TEST VERIFIED |
| Disabled-user handling | Central-disable propagation tested and measured live (302s); disabled accounts correctly rejected at both the OIDC and local-Loady login layers | UNIT TEST VERIFIED + LOCAL LIVE-STACK VERIFIED |
| Rollback security | Rollback scripts require explicit `PLATFORM_MIGRATION_CONFIRM` confirmation, never default to production mode, never print secrets during restore (`COMMAND_SAFETY_AND_VERSION_PINNING.md`) | CODE VERIFIED |

## Net result of this fresh pass

**One genuine defect found and fixed** (email token logging — Phase 43,
this document cross-references it here since it's equally a security
finding). **One previously-known, still-open, explicitly accepted-for-V1
gap re-confirmed** (CORS allowlist not environment-configurable — no
change made, no current attack surface depends on it). **Everything else
checked in this pass matches its already-established, tested behavior** —
no new finding beyond those two.
