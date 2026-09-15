# Production Environment Inventory (Mission 15, Phase 7)

**No secret values appear anywhere in this document** — only variable
names, purpose, and handling requirements. Every row is read directly from
current source (`platform-core/backend/app/config/settings.py`,
`backend/app/config/commercial_settings.py`, `compose.rc.yml`,
`.env.rc.example`) — not copied from a prior mission's possibly-stale list.

Columns: **Required/Optional** (optional = has a safe non-production
default) · **Secret** (yes/no) · **Source** (where the operator gets the
value) · **Validation** (what happens if wrong/missing) · **Rotation
impact** · **Restart required** · **Backup required** (must the value
itself be recoverable, separately from database backups).

## Platform DB

| Var | Req/Opt | Secret | Source | Validation | Rotation impact | Restart | Backup |
|---|---|---|---|---|---|---|---|
| `PLATFORM_POSTGRES_DB` | Required (via `.env.rc`) | No | Operator-chosen name | Compose fails fast (`:?` mandatory) if unset | N/A (not rotated) | Yes (DB reconnect) | Yes — configuration inventory |
| `PLATFORM_POSTGRES_USER` | Required | No | Operator-chosen | Same `:?` guard | N/A | Yes | Yes |
| `PLATFORM_POSTGRES_PASSWORD` | Required | **Yes** | Generated per Phase 8 | Same `:?` guard; wrong value = connection refused at container start, healthcheck never passes, `platform-core-backend` never starts (`depends_on: condition: service_healthy`) | Requires coordinated backend restart; no rolling rotation exists | Yes | Never inside a DB backup's contents; track separately per `PRODUCTION_SECRET_INVENTORY.md` |
| `DATABASE_URL` (Platform Core) | N/A — **not set directly**; composed by `compose.rc.yml` from the three vars above | No (composed, not itself a raw secret) | Computed | If the three inputs are wrong, same failure mode as above | Same as above | Yes | N/A |

## JWT signing / JWKS

| Var | Req/Opt | Secret | Source | Validation | Rotation impact | Restart | Backup |
|---|---|---|---|---|---|---|---|
| `JWT_PRIVATE_KEY_PATH` | Optional (has a dev default; production must override to the mounted path) | No (a path, not the key itself) | Fixed value: `/run/secrets/platform-signing-key.pem` (matches `compose.rc.yml`'s mount target) | `app/security/jwt_keys.py` fails closed if the file at this path is missing — by design, never auto-generates in production | N/A | Yes, if changed | N/A |
| `PLATFORM_SIGNING_KEY_PATH` (top-level `.env.rc`, the HOST path bind-mounted to the above) | Required for production | **Yes** (the file it points to) | Generated per Phase 8, `KEY_ROTATION_RUNBOOK.md` | Missing file = container never becomes healthy | Every previously-issued token becomes unverifiable unless a JWKS overlap window is used (`KEY_ROTATION_RUNBOOK.md`) | Yes | **Yes, with equal or greater protection than the database backup** — compromise is total forgery capability |
| `JWT_KEY_ID` | Optional (default `platform-core-2026-1`) | No | Operator-chosen, must match the key's own `kid` used in JWKS | Mismatch = tokens signed with a `kid` JWKS doesn't advertise; clients fail signature verification | Must change together with the key during rotation, never independently | Yes, if changed | Yes — non-secret configuration inventory |

## Token encryption

| Var | Req/Opt | Secret | Source | Validation | Rotation impact | Restart | Backup |
|---|---|---|---|---|---|---|---|
| `PLATFORM_TOKEN_ENCRYPTION_KEY` (Loady-side) | Optional in dev (ephemeral per-process key generated); **must be set in production** | **Yes** | Generated per Phase 8 (32 raw bytes, base64) | Empty in production = service fails closed rather than storing plaintext (`token_encryption_service.py`, verified live) | Old ciphertext becomes permanently unreadable on rotation — no key-versioning exists yet (documented limitation, `PRODUCTION_SECRET_INVENTORY.md`) | Yes | **Yes, at least as rigorously as the Loady DB backup it protects** — losing it without a backup makes every stored `PlatformOidcToken` row permanently undecryptable |

## OAuth (Loady as a Platform Core client)

| Var | Req/Opt | Secret | Source | Validation | Rotation impact | Restart | Backup |
|---|---|---|---|---|---|---|---|
| `PLATFORM_CLIENT_ID` (Loady-side) | Optional — **empty means the integration is dormant** (explicit, safe default) | No (public identifier) | Assigned when Loady is registered as a client (`register_loady_client.py`) | Empty = every platform-auth route 404s cleanly, no half-configured state | N/A | Yes, to activate | Yes — configuration inventory |
| `PLATFORM_CLIENT_SECRET` (Loady-side) | Required once `PLATFORM_CLIENT_ID` is set | **Yes** | Issued by `register_loady_client.py`; Platform Core stores only its hash | Wrong value = Loady's token exchange calls fail auth | Both sides must change atomically — no overlap window | Yes | Not by value on either side (Platform Core stores a hash only; Loady's copy lives in its own env file) |
| `PLATFORM_REDIRECT_URI` (Loady-side) | Optional (dev default `http://localhost:8000/...`); **must be overridden for production** to Loady's real callback URL | No | Fixed, derived from `loady.cc` | Wrong value = OAuth `redirect_uri` mismatch, authorization fails closed (standard OAuth behavior) | N/A | Yes, if changed | Yes — configuration inventory |

## Loady ↔ Platform Core integration

| Var | Req/Opt | Secret | Source | Validation | Rotation impact | Restart | Backup |
|---|---|---|---|---|---|---|---|
| `PLATFORM_AUTH_BASE_URL` (Loady-side) | Optional (dev default); **required override for production** | No | `https://id.<domain>` (recommended: `id.loady.cc`) | This is the `iss`/JWKS base every token is verified against — wrong value = every SSO login fails closed | Changing it invalidates outstanding token issuer checks (see `IDENTITY_DOMAIN_DECISION.md` Migration Consequence #2) | Yes | Yes — configuration inventory |
| `PLATFORM_API_BASE_URL` (Loady-side) | Same as above | No | Same hostname | Same | Same | Yes | Yes |
| `PLATFORM_INTERNAL_BASE_URL` (Loady-side) | Optional (empty = no override, calls go to the external URL above) | No | `http://platform-core-backend:8000` (the internal Docker DNS name, per `compose.rc.yml`'s `PLATFORM_INTERNAL_BASE_URL` environment override on the `backend` service) | Wrong value = Loady's server-to-server calls to Platform Core fail even though the public hostname works fine for browsers | N/A | Yes, if changed | Yes — configuration inventory |
| `ENTITLEMENT_CACHE_TTL_MINUTES` (Loady-side) | Optional (default 15) | No | Operator tuning | Governs the hybrid fail-closed cache window (`ENTITLEMENT_AVAILABILITY.md`) | N/A | Yes, if changed | Yes — configuration inventory |
| `SESSION_REVALIDATION_INTERVAL_MINUTES` (Loady-side) | Optional (default 5) | No | Operator tuning | Governs the central-disable propagation SLA (`SESSION_REVOCATION.md`) | N/A | Yes, if changed | Yes — configuration inventory |
| `PLATFORM_AUTH_ENABLED` / `PLATFORM_ENTITLEMENTS_ENABLED` / `PLATFORM_BILLING_ENABLED` (Loady-side) | Optional (all default `true`, wrapping the credential-presence dormancy check) | No | Operator kill switch | A `model_validator` rejects `ENTITLEMENTS_ENABLED=true` with `AUTH_ENABLED=false` at startup (fails fast) | Flipping to `false` is the fast rollback kill-switch (`LOADY_ROLLBACK_PLAN.md`) | Yes | Yes — configuration inventory |

## Paddle / billing

| Var | Req/Opt | Secret | Source | Validation | Rotation impact | Restart | Backup |
|---|---|---|---|---|---|---|---|
| `PADDLE_WEBHOOK_SECRET` (Platform Core) | Optional today (billing cutover not yet authorized — see `PADDLE_LIVE_INPUTS_REQUIRED.md`) | **Yes** | Paddle dashboard, once Stage 2 of `BILLING_CUTOVER_RUNBOOK.md` is authorized | Wrong/missing = every webhook signature check fails, all events rejected (fail-closed, correct) | Coordinated with Paddle dashboard update | Yes | Yes — same rigor as other credential secrets |
| `WEBHOOK_SECRET_ENCRYPTION_KEY` (Platform Core, encrypts `OAuthClient.webhook_signing_secret` at rest) | Required once any product's webhook secret is stored | **Yes** | Generated per Phase 8 | Empty = fails closed outside test/dev (`MISSION_6_SECURITY_REVIEW_CONTINUATION.md`) | Existing encrypted secrets become unreadable on rotation without a migration | Yes | Yes |
| `BILLING_DEFAULT_PROVIDER` | Optional (default `paddle`) | No | Fixed | N/A | N/A | Yes, if changed | Yes — configuration inventory |
| Loady's own `PADDLE_API_KEY`/`PADDLE_CLIENT_TOKEN`/`PADDLE_WEBHOOK_SECRET`/four price IDs | Existing, unaffected by this mission | **Yes** (all but price IDs) | Existing Loady production config | Unchanged | Unchanged | Unchanged | Unchanged existing practice |

## Public URLs / trusted proxies / CORS / hosts

| Var | Req/Opt | Secret | Source | Validation | Rotation impact | Restart | Backup |
|---|---|---|---|---|---|---|---|
| `RC_LOADY_HOSTNAME` / `RC_PLATFORM_AUTH_HOSTNAME` / `RC_ACCOUNT_HOSTNAME` / `RC_ADMIN_HOSTNAME` | Required (`:?` mandatory in `compose.rc.yml`) | No | `IDENTITY_DOMAIN_DECISION.md` | Compose fails fast if unset | See domain decision doc's Migration Consequence | Yes (edge restart re-renders the envsubst template) | Yes — configuration inventory |
| CORS allowed origins (Platform Core backend) | **Not env-configurable today — hardcoded to a fixed localhost-only allowlist in `app/main.py`** | No | N/A | **Finding, not a blocker for V1**: production origins (`https://account.loady.cc` etc.) are not in this list. Documented as accepted for V1 because the fixed reverse-proxy fix in Phase 12 makes Account Portal/Grand Admin calls same-origin (no CORS needed); a future product onboarding with its own cross-origin browser SPA would need this made configurable — tracked as a follow-up, not fixed here (no feature creep) | N/A | N/A | N/A |
| Cloudflare real-IP trust list | Hardcoded in `nginx.production.conf.template` (Cloudflare's published ranges) | No | Cloudflare's public IP list | Stale list = `CF-Connecting-IP` not trusted correctly if Cloudflare changes ranges — an existing, accepted maintenance burden (comment in the template says to keep in sync manually) | N/A | Yes (edge restart) | Yes — configuration inventory |

## Session/cookie security

| Var | Req/Opt | Secret | Source | Validation | Rotation impact | Restart | Backup |
|---|---|---|---|---|---|---|---|
| `COOKIE_SIGNING_KEY` (Platform Core) | Optional (dev generates one); **required explicit value for production** | **Yes** | Generated per Phase 8 | A generated dev key is process-ephemeral — restarting without a fixed production value invalidates all sessions on every restart, an availability bug in production if left unset | Invalidates every outstanding session cookie on rotation | Yes | Yes |
| `COOKIE_SECURE` | Optional (default `false`; production example sets `true`) | No | Fixed `true` for production | Wrong (`false`) in production = cookies sent over plain HTTP, a real security regression if TLS terminates elsewhere unexpectedly | N/A | Yes, if changed | Yes — configuration inventory |
| `COOKIE_DOMAIN` (Platform Core and Loady) | Optional (empty = host-only cookie) | No | Business decision — only set if a shared cookie-domain suffix across `id./account./admin.<domain>` is deliberately chosen | Wrong value = cookies silently not sent where expected, or sent more broadly than intended (a real security consideration, not just a UX one) | N/A | Yes, if changed | Yes — configuration inventory |
| `ACCESS_TOKEN_TTL_MINUTES` / `REFRESH_TOKEN_TTL_DAYS` / `OIDC_*_TTL_*` / `AUTHORIZATION_CODE_TTL_SECONDS` | Optional (sane defaults) | No | Operator tuning | N/A | N/A | Yes, if changed | Yes — configuration inventory |

## Mail

| Var | Req/Opt | Secret | Source | Validation | Rotation impact | Restart | Backup |
|---|---|---|---|---|---|---|---|
| `EMAIL_BACKEND` (Platform Core) | Optional, **defaults to `log` — MUST be changed before real cutover** (verification/password-reset email would otherwise never be delivered) | No | Operator choice | `log` backend = emails only appear in application logs, never delivered — acceptable for rehearsal, a real gap for production until changed | N/A | Yes, if changed | Yes — configuration inventory |
| Loady's own `EMAIL_BACKEND`/`RESEND_API_KEY`/`EMAIL_FROM` | Existing, unaffected by this mission | `RESEND_API_KEY` yes, others no | Existing Loady production config | Unchanged | Unchanged | Unchanged | Unchanged |

## `.env.production.example` files — status and this mission's additions

- `platform-core/.env.production.example` — already complete and accurate
  (verified line-by-line against `settings.py` above); no changes needed.
- Root `.env.production.example` (Loady) — **was missing every
  `PLATFORM_*` integration variable** (`PLATFORM_AUTH_BASE_URL`,
  `PLATFORM_API_BASE_URL`, `PLATFORM_CLIENT_ID`, `PLATFORM_CLIENT_SECRET`,
  `PLATFORM_REDIRECT_URI`, `PLATFORM_INTERNAL_BASE_URL`,
  `PLATFORM_TOKEN_ENCRYPTION_KEY`, `ENTITLEMENT_CACHE_TTL_MINUTES`,
  `SESSION_REVALIDATION_INTERVAL_MINUTES`, `PLATFORM_AUTH_ENABLED`,
  `PLATFORM_ENTITLEMENTS_ENABLED`, `PLATFORM_BILLING_ENABLED`) despite
  Loady's own `commercial_settings.py` supporting all of them today. **Fixed
  in this mission** — see the diff to `.env.production.example`, all values
  left empty/at their safe dormant defaults (`PLATFORM_CLIENT_ID` empty
  keeps the integration off exactly as it is in real production today).
  This is a documentation/template fix, not an application code change —
  no behavior changes for any existing deployment that doesn't set these
  new example lines.
