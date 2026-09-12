# Commercial Architecture (`commercial-v1`)

This document describes the commercial SaaS layer built on top of the
working personal media downloader, on the `commercial-v1` branch. The
personal app (`personal-stable` branch / `personal-v1-working` tag) is
untouched — this is an additive layer, not a rewrite.

**Positioning**: a creator media utility for importing, saving, converting,
organizing, and processing media the user is authorized to access. It is not
marketed as, and does not implement, DRM circumvention, paywall bypass, auth
bypass, or any other technical-protection circumvention.

## 1. Two databases, deliberately separate

| | Personal layer (untouched) | Commercial layer (new) |
|---|---|---|
| File | `data/app.db` | `data/commercial.db` |
| Access | raw `sqlite3` (`app/database/db.py`) | SQLAlchemy 2.0 ORM |
| Contents | `settings`, `history` | `users`, `subscriptions`, `usage_periods`, `usage_events`, `entitlements`, `billing_events`, `refresh_tokens`, `password_reset_tokens`, `email_verification_tokens`, `user_download_preferences` |
| Migrations | none (additive `ALTER TABLE` in `db.py._migrate_schema`, see §7) | Alembic (`backend/alembic/`) |
| Portability | SQLite only | `DATABASE_URL` env var — SQLite locally, PostgreSQL in production, no code changes |

Keeping them separate meant the entire personal-app codebase and its 121
existing tests needed zero changes to their own logic; the commercial layer
was added alongside, and the two touch each other only at the specific
integration point described in §4.

## 2. Authentication

- **Password hashing**: Argon2id via `argon2-cffi` (`security_service.py`).
  Passwords are re-hashed transparently on next login if parameters are ever
  strengthened later (`needs_rehash`).
- **Sessions**: two tokens, both delivered as **httpOnly cookies only** —
  never in a JSON response body, never in `localStorage`, never readable by
  frontend JS:
  - `lmd_access` — a short-lived (15 min default) stateless JWT.
  - `lmd_refresh` — a long-lived (30 days default) opaque random token.
    Only its SHA-256 hash is stored server-side (`RefreshToken` table), so a
    single session can be revoked (logout, password reset) without a JWT
    blocklist. **Rotated** on every use: each `/api/auth/refresh` call
    revokes the presented token and issues a new one, so a stolen-and-reused
    refresh token is detectable.
- **Password reset / email verification**: single-use, hashed-at-rest,
  expiring tokens (`PasswordResetToken`, `EmailVerificationToken`). A
  password reset revokes every active session for that user. The
  forgot-password endpoint never reveals whether an email is registered, and
  login takes the same code path (same hasher call, same error) for "no
  such user" and "wrong password" to avoid a timing/response side channel.
- **Rate limiting**: in-memory sliding-window limiter
  (`rate_limit_service.py`, no Redis — see §9) on signup, login (keyed by
  IP+email), forgot-password, reset-password, verify-email, and
  resend-verification.
- **Email delivery**: `EmailBackend` protocol with one implementation,
  `LogEmailBackend`, which writes the email (including the actual
  verify/reset link) to `data/logs/app.log` instead of requiring a real
  provider. Swapping in a real provider (SES, Postmark, Resend, ...) is a
  one-file change (`email_service.py`) — nothing else in the app needs to
  know.

## 3. Plans, entitlements, and credits

**Everything reads from one place**: `app/services/plan_policy.py`'s
`PLAN_POLICIES` dict. No `if plan == "pro"` is scattered through the
codebase — `EntitlementService` (`entitlement_service.py`) is the only thing
that answers "can this user do X right now", and `DownloadGateService`
(`download_gate_service.py`) is the only thing that calls it before a
download job is created.

| | Free | Pro | Creator |
|---|---|---|---|
| Price | $0 | $4.99/mo, $49/yr | $9.99/mo, $99/yr |
| Downloads | 5/day | 150 credits/mo | 500 credits/mo |
| Max resolution | 720p | Unlimited (4K) | Unlimited (4K) |
| Container mode | Compatibility MP4 only | Both | Both |
| Audio | Basic MP3 | MP3/M4A + advanced | MP3/M4A + advanced |
| Clip range | ✗ | ✓ | ✓ |
| Browser cookies | ✗ | ✓ | ✓ |
| Batch downloads | ✗ | ✓ | ✓ |
| Creator tools | ✗ | ✗ | entitlement architecture only — see §3.3 |
| Ads | On | Off | Off |
| Queue priority | 1 | 5 | 10 |

### 3.1 Credit costs

Free doesn't use credits — it's a daily allowance (5/day, resets at UTC
midnight). Pro/Creator use monthly credits that reset with the billing
period:

- Video ≤1080p: 1 credit · 1440p: 2 credits · 4K: 3 credits
- Audio: 1 credit (flat)
- A request for "Best Available" on an uncapped plan is charged at the
  **worst case (4K, 3 credits) upfront** — there is no partial-refund
  true-up after the real resolution is known. This is a deliberate
  simplicity trade-off (see §10) — it slightly overcharges when "best"
  actually resolves to 1080p, never undercharges.

### 3.2 Reservation lifecycle (never allow a negative balance)

`UsageService.reserve()` uses an atomic SQL `UPDATE ... WHERE <budget still
available>` — never a `SELECT` followed by a separate `UPDATE`. Two
concurrent requests racing for the last credit can never both succeed; the
database enforces it per-row. This is portable to PostgreSQL without relying
on `SELECT ... FOR UPDATE` (which SQLite doesn't support), and is covered by
a real multi-threaded test (`tests/test_commercial_usage.py::
TestConcurrentReservationNeverGoesNegative`) that fires 20 concurrent
reservations at a 10-credit pool and asserts exactly 10 succeed.

Flow, wired into `routes_downloads.py` and `download_manager.py`:

1. `DownloadGateService.authorize_and_reserve()` runs every entitlement
   check for the request, then reserves the credit cost. Raises a
   structured error (see §3.5) if anything fails — no job is created.
2. The reservation is committed to the DB **before** `DownloadManager.
   create_job()` is called, closing a race where a fast-failing job could
   try to settle a reservation that isn't durable yet.
3. When the job reaches a terminal state, `DownloadManager._finalize_usage()`
   commits the reservation (completed) or refunds it (failed/cancelled),
   via `app.database.commercial_db.session_scope()` — a background asyncio
   task has no FastAPI request-scoped session to reuse.

### 3.3 Creator tools: architecture, not features

Per the spec, no actual Creator-only editing tools are built yet. What
exists is the extension point: `PlanPolicy.can_use_creator_tools` and the
`Entitlement` table (ad-hoc feature grants layered on top of a plan —
promos, rewarded-ad unlocks, admin overrides) so future Creator tools can
gate on `can_use_creator_tools` or a specific `Entitlement` row without
touching the plan model again.

### 3.4 Anonymous guest downloads

Separate from the authenticated Free plan's 5/day allowance above: an
anonymous visitor gets `GUEST_DOWNLOAD_LIMIT` (`commercial_settings.py`,
default **5**, raised from 2) downloads **for the lifetime of their
`lmd_guest` cookie**, not a daily reset — tracked by `GuestQuota`
(`guest_service.py`) with an atomic reserve/commit/refund pattern mirroring
the authenticated credit reservation lifecycle in §3.2. This is a distinct
quota from the Free plan's daily allowance; signing up for a Free account
gives the user the normal 5/day allowance independently of how much of
their guest quota they'd already used.

### 3.5 Structured error codes

Every gating failure is a typed `AppError` subclass with a stable `code` the
frontend branches on (`ApiError.code` in `services/api.ts`):
`PLAN_LIMIT_REACHED`, `DAILY_LIMIT_REACHED`, `FEATURE_NOT_INCLUDED`,
`UPGRADE_REQUIRED`, `INSUFFICIENT_CREDITS`. All enforcement is **backend
gating** — see §8 for why the frontend never fully trusts this alone.

## 4. Integration with the existing downloader

Only two files that predate this branch were touched, both additively:

- `download_manager.py`: `DownloadJob` gained optional `user_id` and
  `reservation_id` fields; `create_job()` gained optional `job_id`,
  `user_id`, `reservation_id` params (all default to the old
  auto-generated behavior, so the existing tests across
  `test_download_manager.py`/`test_mp4_compatibility.py` that call
  `create_job(request)` with no extra args are unaffected);
  `_finish_as_completed/_failed/_cancelled` now call `_finalize_usage()`.
- `routes_downloads.py` and `routes_history.py`: now require
  `Depends(get_current_user)` and scope every list/get/cancel/delete/clear
  operation to `user_id == current_user.id`. A mismatched job/history id
  reads as **404, never 403** — existence isn't leaked across accounts.

One pre-existing gap was found and fixed while wiring this up: `GET
/api/progress/stream` (the SSE job-progress feed) broadcast **every**
user's job titles/URLs/progress to any connected client — it had no owner
scoping at all before this branch. It's now `Depends(get_current_user)` and
filters to `manager.list_jobs(user_id=user.id)`, matching `GET
/api/downloads`.

### 4.1 Per-user download preferences (container_mode / cookie_source)

**Fixed** — this section originally flagged `container_mode` and
`cookie_source` as process-global settings that `DownloadGateService`
gated on directly: any user setting `container_mode=ORIGINAL` or a
non-`NONE` `cookie_source` would silently block every *other* Free-plan
user's downloads with `FEATURE_NOT_INCLUDED`, since it was one shared row.

They now live in a dedicated table, `user_download_preferences`
(`user_id` primary key, one row per account, created lazily on first
access with sensible defaults), owned by `app/services/
user_preferences_service.py`. Every place that used to read the global
`AppSettings.container_mode`/`cookie_source`/`cookie_file_path` now goes
through it instead:

- `DownloadGateService.authorize_and_reserve()` gates on `session,
  user.id`'s own row — never the global settings object (which it no
  longer even receives as a parameter).
- `DownloadManager._effective_settings()` builds the global `AppSettings`
  (concurrency, audio/video presets, timeouts — still legitimately shared)
  and layers the job's owning user's own container_mode/cookie_source/
  cookie_file_path **and** download_dir (see §4.2 — also no longer shared)
  on top before handing it to `ytdlp_service.build_download_opts`, so what
  a job is gated against and what it actually runs with are guaranteed to
  match.
- `POST /api/analyze` (format/quality preview, reachable anonymously as
  part of the pre-signup funnel) uses `get_optional_user` and applies the
  *signed-in* caller's own preferences when there is one, sensible
  defaults otherwise — an anonymous preview or another user's preview can
  never be shaped by a third user's settings.
- `GET/PUT /api/account/download-preferences` is the new per-user REST
  surface (auth required); the Settings page's "Video output" and
  "Authentication" sections now call it instead of the old global
  `/api/settings` endpoint, whose `container_mode`/`cookie_source`/
  `cookie_file_path` fields remain in the schema only for backward
  compatibility with any direct API consumer of the old shape — the
  commercial frontend never reads or writes them anymore.

Isolation is covered by `tests/test_commercial_user_preferences.py`:
a Free user is unaffected by a Pro user's changes, two Pro users' changes
never cross, a 20-thread/20-user concurrent-update test proves no
cross-account bleed even under contention, and a user who never opens
Settings still downloads normally on the hardcoded defaults.

**Other global-state issues found and fixed during this same audit** (the
task was explicitly to check for "other settings with the same
multi-tenant problem," and these three were real, live, exploitable gaps
at the time — `download_dir` itself was flagged in the same pass and fixed
separately shortly after, see §4.2):

- `GET/PUT /api/settings` had **no authentication at all** — any
  unauthenticated caller could rewrite the shared concurrency limit,
  theme, or audio/video defaults for the entire server (and, at the time,
  the shared `download_dir` — now moot, see §4.2). Now requires
  `Depends(get_current_user)`.
- `POST /api/fs/open` and `/api/fs/open-folder` — which run the OS's
  "reveal in file manager" handler (`open`/`xdg-open`/`explorer`) on a
  server-side path — also had **no authentication**. Now require auth.
- `ensure_path_permitted()`'s fallback check ("is this path something
  *any* history row ever recorded, even outside the current download
  folder") was a completely **unscoped, cross-account** lookup
  (`history_repo.filepath_exists` had no `user_id` filter at all) — one
  account could use it to act on, or merely probe the existence of,
  another account's downloaded file path. `filepath_exists()` now takes
  an optional `user_id` and every caller in the app passes the current
  authenticated user's id.

### 4.2 `download_dir` is now per-user and non-configurable

**Fixed.** This section originally flagged `download_dir` as still a
shared, global, freely-user-editable setting — worse than the
container_mode/cookie_source bug fixed in §4.1, since `resolve_safe_
directory()` placed **no restriction at all** on the path a user could
set, making it an arbitrary-server-file-write primitive once "the user"
became any signed-up web visitor rather than the original single-operator
desktop app's own owner.

**Design**: a new admin/server-only config value, `DOWNLOAD_ROOT`
(`CommercialSettings.download_root`, defaults to the personal app's own
default download folder), owned by `app/services/user_storage_service.py`.
Every authenticated user's downloads are confined to exactly
`<DOWNLOAD_ROOT>/<user_id>/` — never user-editable, never an admin-editable
per-user runtime value, purely a deterministic function of the account's
own id. No database column stores it (unlike container_mode/cookie_source,
this isn't a *preference* — it's an identity-derived storage location).

- `user_download_dir(user_id)` resolves (and lazily creates) that
  directory. Security checks, in order: `user_id` must match a strict
  allow-list pattern (blocks path traversal via the id itself - `..`, `/`,
  `\`, empty, or anything not matching the UUID shape this app actually
  generates); if a **symlink** already occupies where the directory should
  be, it's refused outright rather than silently followed (`mkdir(exist_ok=
  True)` would otherwise happily accept a symlinked directory); the
  resolved result is verified to still fall within `DOWNLOAD_ROOT` as a
  final check.
- `ensure_within_user_dir(path, user_id)` is the sole authorization check
  behind every open/delete/cleanup/retry filesystem action for an
  authenticated caller — no history-based fallback, no global-download-dir
  fallback (both existed before this fix and both are now gone for any
  caller with a real user_id). It resolves **both sides** before comparing,
  so a symlink planted *inside* an otherwise-legitimate user directory,
  pointing elsewhere, can't be used to escape it either.
- `DownloadManager._effective_settings()` now overrides `download_dir` too
  (alongside container_mode/cookie_source from §4.1) with this computed,
  confined path before a job ever touches disk — re-verified once more
  immediately before the actual write in `_blocking_download`, and again in
  `_cleanup_cancelled_file`, on the theory that a security boundary this
  consequential deserves more than one layer of defense. A job created with
  no `user_id` (the lower-level, non-HTTP `manager.retry_job()`, kept for
  programmatic/test use) keeps the old global-`download_dir` behavior
  unchanged - full backward compatibility for that one legacy path.
- `filesystem_service.ensure_path_permitted(path, user_id=...)` — what
  `/api/fs/*` and `/api/history/*` actually call — now routes through
  `ensure_within_user_dir` whenever a `user_id` is present (every real HTTP
  route in this build). The old global-download-dir + unscoped-history
  fallback survives only as a no-`user_id` branch for programmatic callers
  with no authenticated context, unreachable from any route.
- `GET /api/settings` now returns this computed, read-only path in its
  `download_dir` field (still the same response shape, so nothing else
  breaks); `PUT /api/settings` rejects any patch that includes
  `download_dir` with a clear `400`. The Settings page's "Download folder"
  field is now a read-only display, not an editable input.

**Not addressed in this fix** (separate, smaller, and lower-severity):
`cookie_source=file`'s `cookie_file_path` still accepts an arbitrary server
path. It's read-only (never written to), and a parse failure doesn't echo
file contents back to the caller, so the risk is materially lower than
`download_dir` was — but it's the same *shape* of problem and would
benefit from a similar per-user-sandboxed-uploads treatment if this ever
needs to harden further before a real launch.

Verified: 27 new/updated automated tests (`tests/test_user_storage_service.py`
plus `TestPerUserDownloadDirectory` in `tests/test_download_manager.py`)
covering path traversal via a malicious `user_id`, a symlink planted where
a user's directory should be, a symlink planted *inside* an otherwise-
legitimate directory, cross-user access denial (including at the real HTTP
layer — two real accounts, real cookies), and that a job with no user_id
still falls back to the old behavior unchanged. Also verified live against
a running server: two real accounts each got their own, differently-named
directory under `DOWNLOAD_ROOT` (confirmed on disk after an actual queued
download); an attempted `PUT /api/settings` with an arbitrary
`download_dir` was rejected with 400; and a path-traversal attempt via
`POST /api/fs/open` (`/etc/passwd`) was rejected.

## 5. Paddle billing

**Sandbox only.** `PADDLE_ENV` defaults to `sandbox` and
`get_commercial_settings()` logs a loud warning if it's ever anything else;
nothing in this codebase is wired to accept live Paddle credentials as
"just another env var" — see `PADDLE_SANDBOX_TESTING.md` for what was and
wasn't possible to verify without a real Paddle account.

- **Checkout**: `POST /api/billing/checkout` returns `{price_id,
  client_token, environment, plan, billing_period, custom_data: {user_id}}`
  (raises a clean `502 BILLING_ERROR` rather than crashing if no price/token
  is configured for that plan+period). The backend never creates a
  "checkout session" — `frontend/src/lib/paddle.ts` loads Paddle.js v2 from
  Paddle's CDN client-side and opens its checkout overlay directly against
  the price ID and public client token; `environment` drives
  `Paddle.Environment.set()` so the frontend never hardcodes sandbox vs.
  production. The backend API key (`PADDLE_API_KEY`) is never sent to the
  frontend — only the public, checkout-only client token is.
- **Webhook — the sole source of truth**: `POST
  /api/billing/paddle/webhook`. A successful frontend checkout redirect is
  *never* trusted on its own; the account page keeps showing the old plan
  until this webhook lands. Verification:
  `Paddle-Signature: ts=<unix>;h1=<hex hmac>` where
  `h1 = HMAC-SHA256(secret, f"{ts}:{raw_body}")`, compared with
  `hmac.compare_digest` (timing-safe).
- **Idempotency**: `BillingEvent.provider_event_id` is the primary key. A
  duplicate delivery is a guaranteed no-op — checked before any
  state-changing work runs (`paddle_service.process_webhook_event`). On a
  processing failure, the session is rolled back before recording a
  `failed` `BillingEvent`, so a partial failure can never leave half-applied
  subscription state committed alongside a "failed" audit row.
- **User correlation**: Paddle's `custom_data: {user_id}`, set at checkout
  time and echoed back on every subsequent webhook for that
  subscription/transaction — no separate customer-lookup round trip needed.
- **Event handling**: `subscription.created/activated/updated/canceled/
  paused/resumed`, `transaction.completed`, `transaction.payment_failed` are
  handled; anything else is recorded (for audit/idempotency) but ignored.
- **Customer portal**: `POST /api/billing/portal` proxies to Paddle's
  hosted customer-portal session API — the Billing page's "Manage billing"
  button opens Paddle's own UI in a new tab. No custom card-management UI
  was built, per the explicit instruction not to invent one.

`paddle_client.py` (the low-level REST wrapper), the webhook payload
shapes in `paddle_service.py`, and the Paddle.js integration in
`frontend/src/lib/paddle.ts` are all written against Paddle's documented
Billing API v1 / Paddle.js v2 from training knowledge — **no Paddle
MCP/sandbox tooling has been available in this environment**, checked
twice across two build sessions (`ToolSearch`/`SearchMcpRegistry`/
`ListConnectors`, all empty for Paddle) to exercise any of it against a
real account. See `PADDLE_SANDBOX_TESTING.md` for exactly what is and
isn't verified, and the manual steps to finish verification with real
credentials.

## 6. Database model

SQLAlchemy 2.0 declarative models (`app/database/commercial_models.py`),
all primary keys are UUID strings (portable, not a DB-specific UUID type),
all timestamps go through a custom `UTCDateTime` `TypeDecorator`
(`app/database/sa_types.py`) — SQLite silently drops timezone info even on
a `DateTime(timezone=True)` column, which caused a real bug during
development (`/api/auth/refresh` 500ing on "can't compare offset-naive and
offset-aware datetimes"); the custom type normalizes to timezone-aware UTC
on both read and write, portable to PostgreSQL unchanged.

Tables: `users`, `subscriptions`, `usage_periods` (unique per
`user_id, period_start`), `usage_events` (append-only audit log of every
reserve/commit/refund/admin-grant), `entitlements` (ad-hoc grants, see
§3.3), `billing_events`, `refresh_tokens`, `password_reset_tokens`,
`email_verification_tokens`, `user_download_preferences` (`user_id` itself
is the primary key — one row per account, see §4.1).

## 7. Migrations

- **Commercial layer**: Alembic (`backend/alembic/`), `env.py` reads
  `DATABASE_URL` from `CommercialSettings` and targets `Base.metadata`.
  `scripts/start.sh`/`start.bat` run `alembic upgrade head` on every
  startup — safe to run repeatedly (no-op once current). **Do not rely on
  `create_all()` for production** — the migrations currently checked in
  (`20491e9286b1_create_commercial_tables.py`, then
  `2b437cf7ea5c_add_per_user_download_preferences.py`) are what actually
  create the tables in a fresh environment; both were verified against a
  completely empty database.
- **Personal layer** (`data/app.db`): still schema-on-connect via
  `CREATE TABLE IF NOT EXISTS` in `db.py`, as before — with one additive
  change: a `user_id` column was added to `history` (needed so download
  history can be scoped per-account, see §4). Since `CREATE TABLE IF NOT
  EXISTS` doesn't add columns to an already-existing table, `db.py.
  _migrate_schema()` runs an idempotent `ALTER TABLE history ADD COLUMN
  user_id TEXT` for any pre-commercial database that doesn't have it yet.

## 8. Security summary

- Backend enforces every plan/usage limit — the frontend hiding a button is
  a convenience only. A direct API call from a Free account requesting
  1440p, or exceeding 5/day, is rejected server-side with a structured
  error code regardless of what the frontend sent.
- CORS: fixed local-origin allowlist (`allow_credentials=True` requires
  this — Starlette refuses `"*"` with credentials), never a wildcard.
- Cookies: httpOnly always; `COOKIE_SECURE` must be set `true` behind HTTPS
  in any real deployment (defaults `false` for local `http://` dev only).
- Webhook signatures verified with a timing-safe comparison; secrets are
  never logged (only "verification failed" is logged, never the header or
  the secret itself).
- No endpoint in the commercial layer executes a shell command or reads an
  arbitrary file path; the personal app's existing filesystem
  guardrails (`ensure_path_permitted`, `resolve_safe_directory`) are
  untouched.
- No admin self-service promotion endpoint exists on purpose — there is no
  way to become an admin via the API. The first admin account is promoted
  with `python -m app.scripts.promote_admin <email>` (§11), a CLI-only,
  existing-user-only, idempotent operator action; it never runs
  automatically and there is deliberately no HTTP path to it.
- `npm audit` on the frontend still flags the same pre-existing
  Vite/react-router advisories noted in the personal app's README (dev-only,
  local-bind-only exposure) — unrelated to and not worsened by this branch's
  dependency additions (`@testing-library/*`, `jsdom`, dev-only).

## 9. Production readiness notes (not built, intentionally)

- **PostgreSQL**: swap `DATABASE_URL`, nothing else changes — every model
  uses portable types.
- **Redis / job queue**: deliberately not introduced. The credit
  reservation race protection doesn't need it (atomic SQL `UPDATE`), and
  the rate limiter is in-memory single-process by design; the module's own
  docstring says explicitly to swap it for a Redis-backed limiter before
  scaling to multiple worker processes.
- **Nginx / TLS**: out of scope for local dev; `COOKIE_SECURE=true` and a
  real reverse proxy are the two things that actually need to change.

## 10. Other deliberate scoping decisions

- "Best Available" is charged at the worst-case tier upfront (§3.1) rather
  than adding partial-refund-after-the-fact logic.
- Anonymous users cannot download — landing/pricing/legal pages are public,
  everything else requires a Free account, per the spec's stated default.
- Ads are architecture-only: the `AdSlot` placeholder component (never a
  fake button, popunder, or redirect) renders for Free-plan accounts and
  nothing else — no real ad network is integrated. Rewarded ads (watch an
  ad → temporary bonus credits) are **not built**: only a
  `UsageEventType.REWARD_GRANT` enum value exists as a placeholder in the
  audit-log schema, so a future `RewardGrant` flow has somewhere to record
  itself, but there is no service, endpoint, or `RewardGrant` model yet.
  Whoever builds it should keep the spec's constraint in mind: never trust
  a frontend-only "I watched the ad" claim — the eventual ad provider's own
  server-to-server webhook must be the thing that actually grants credit.

## 11. Admin Panel

- **UI**: `/admin` is five pages sharing one tab strip (`AdminLayout`) —
  Overview, Users, Billing, Activity, System — under `frontend/src/pages/admin/`.
  Every route is guarded twice: `AdminRoute` (frontend, UX-only redirect)
  and `require_admin` (backend, re-resolves the user from the DB on every
  request — the only check that actually matters).
- **Endpoints** (`app/api/routes_admin.py`, all `require_admin`):
  `GET /api/admin/users`, `GET /api/admin/users/{id}`,
  `POST /api/admin/users/{id}/grant-credits`,
  `POST /api/admin/users/{id}/status` (disable/reactivate, with
  self-disable rejected), `PATCH /api/admin/users/{id}/subscription`
  (grant/change/revoke a **gifted** subscription — never Paddle, see §12),
  `GET /api/admin/billing-events`, `GET /api/admin/overview`,
  `GET /api/admin/audit-log`. None of them return Paddle secrets, API keys,
  or raw webhook payloads.
- **Audit log**: `AdminActionLog` (own table, not overloaded onto
  `UsageEvent`) records every grant/disable/reactivate with the acting
  admin's id, the action, the affected user, a small JSON `details` blob,
  and a timestamp. Written by `admin_audit_service.record()` inside the
  same request that performs the change; read back by `GET
  /api/admin/audit-log` and by the Overview page's "recent admin actions"
  panel.
- **Provisioning**: `python -m app.scripts.promote_admin <email>` — see the
  script's own docstring for the full contract (existing-user-only,
  idempotent, no secrets in or out, exit codes 0/1/2). There is
  deliberately no HTTP path to it.
- **Credits shown to admins**: `credits_bonus` (Users page, user detail,
  `AdminUserOut`) is derived at read time as
  `max(0, credits_included - plan's own monthly_credits)` — it is never a
  stored column, so it can't drift from the real credit ledger.

## 12. Gifted Subscriptions (admin-granted, non-revenue access)

An admin can manually grant, change, or revoke Pro/Creator access for a
user **without charging them** — for support, promos, partnerships, or
internal testing. A Gifted Subscription is internal promotional/manual
access; it is never treated as paid income, and it is never created,
modified, or synced through Paddle in any way.

### 12.1 Explicit subscription source, never inferred

`Subscription.provider` (an existing `String` column that already defaulted
to `"paddle"`) is now typed against `SubscriptionProvider` (`commercial_
enums.py`): `PADDLE` or `GIFTED`. This is the one, explicit, queryable
source of truth for "is this row paid or gifted" — nothing infers gifted
status from a missing Paddle subscription id or any other absent field, and
no unrelated column is overloaded to carry this meaning.

### 12.2 Entitlements: reuse, not a parallel system

A gifted `Subscription` row is a completely ordinary row — same table, same
`plan`/`status="active"` semantics — so every existing entitlement/credit
code path treats it identically to a paid one, with no new gating logic:

- `account_service.get_active_subscription`/`get_current_plan` filter by
  `status`, not `provider` — a gifted row is picked up automatically.
- `EntitlementService`/`DownloadGateService` never look at `provider` at
  all — a gifted Pro/Creator user gets pixel-identical feature access
  (resolution cap, batch, clip range, cookies, ads-off, queue priority) to
  a paid one.
- Gifted subscriptions have no confirmed Paddle billing period, so
  `UsageService.get_or_create_current_period`'s existing "no confirmed
  billing period yet" 30-day rolling-window fallback (already used for
  brand-new paid subscriptions before their first Paddle webhook lands)
  is what rolls a gifted user's monthly credits over — no new credit-reset
  mechanism was built.

### 12.3 Paid Paddle subscriptions always take precedence

`gift_subscription_service._reject_if_paid()` is checked before any
grant/change: if the user has an active Paddle-provider subscription, the
call raises `PaidSubscriptionActiveError` (`409 PAID_SUBSCRIPTION_ACTIVE`)
and nothing is written. An admin cannot use the gifting control to
overwrite, downgrade, cancel, or otherwise alter a real Paddle subscription
— the admin UI disables the gifting controls for such a user up front and
shows "Paid subscription managed through Paddle" instead of a form.
`gift_subscription_service.py` never imports or calls `paddle_client`; it
never creates a Paddle customer/subscription/checkout, never touches a
Paddle price or subscription id, and never cancels billing. (A pre-existing
safety net, `routes_billing._owned_subscription`'s `provider != "paddle"`
check, independently blocks the Paddle-management endpoints from ever
acting on a gifted row.)

### 12.4 Admin workflow

`AdminUsers.tsx`'s "Manage subscription" button opens a modal (not a raw
dropdown):

- **Active Paddle subscription** → the modal renders a non-editable notice
  ("This user has an active paid Paddle subscription. Manage billing
  through the normal subscription workflow.") — no form is shown.
- **Otherwise** → a plan selector (Free / Gift Pro / Gift Creator), an
  optional reason (validated, max 500 chars), and an explicit warning
  ("This grants Loady access without charging the user.") before a second,
  confirmation step. The confirm button reads "Grant/Update/Revoke Gifted
  Subscription" depending on the transition. Choosing Free on a gifted
  user revokes it.
- The Users table and user-detail modal show a "Gifted" badge, the
  subscription source, the granted date, who granted it
  (`granted_by_admin_id` → resolved email), and the optional reason —
  visible to admins only; end users never see the admin's note.

### 12.5 Backend endpoint

`PATCH /api/admin/users/{user_id}/subscription` (`require_admin`,
`AdminUpdateSubscriptionRequest {plan, reason?}`):

- Anonymous → 401, non-admin → 403 (same `require_admin` dependency as
  every other admin route).
- `plan` is a strict `Plan` enum (422 on anything else) — there is no way
  to set an arbitrary/free-text subscription source from the request body;
  `provider` itself is never client-supplied, it's always set server-side
  to `GIFTED`.
- `plan == Plan.FREE` → `gift_subscription_service.revoke()`; otherwise →
  `grant_or_change()`. Both run inside the request's existing DB
  transaction — either the subscription update **and** the audit log
  **and** the analytics event all commit, or none do.
- Blocked (409) whenever the target already has an active Paddle
  subscription, per §12.3.

### 12.6 Reversibility

Revoking a gifted subscription sets `plan=free`, `provider` to no active
row (the subscription's status moves to a terminal state exactly like a
cancelled Paddle subscription would), and the user immediately gets Free
entitlements on their very next request — no caching, no delay. Gifted
Creator → Gifted Pro (or back) preserves `provider=gifted` and simply
updates `plan`, writing a `gift_subscription_changed` audit row rather than
a grant/revoke. Paid billing fields (`granted_by_admin_id` aside, which is
gift-only) are never touched by any gifted-subscription operation.

### 12.7 Audit log

Reuses the existing `AdminActionLog` table and `admin_audit_service.record()`
— no new audit mechanism. Three new `AdminActionType` values:
`gift_subscription_granted`, `gift_subscription_changed`,
`gift_subscription_revoked`. Each entry's `details` JSON carries the target
user's email, previous/new plan, previous/new subscription source, and the
optional reason; the acting admin's id and a timestamp are the log row's
own existing columns. This is append-only, like every other admin action —
a later revoke does not delete or rewrite the original grant's row.

### 12.8 Revenue and analytics: gifted is never revenue

Every query that counts "paid subscribers" now explicitly filters
`Subscription.provider == SubscriptionProvider.PADDLE.value` — this
changed `analytics_service.get_overview` (`paid_conversions`),
`analytics_service.get_revenue` (`active_paid_subscribers`,
`new_paid_subscribers`), and the admin overview's plan-breakdown query
(`routes_admin.get_overview`). Gifted subscriptions are counted **only** in
their own, separate, never-summed fields: `AdminOverviewOut.
gifted_subscribers`, `RevenueOut.gifted_active_subscriptions`, `RevenueOut.
gifted_events_this_period`. A gifted user is structurally excluded from
`Subscription.created_at`-based "new paid subscriber" counts and from
`plan_upgraded`/`plan_downgraded`/`subscription_cancelled` events (those
three event types are written **only** from `paddle_service.py`'s webhook
handler — never from `gift_subscription_service`). Three new, structurally
separate event types exist for gifted actions
(`gifted_subscription_granted/changed/revoked`, `AnalyticsEventType`) so a
revenue-movement query can never accidentally mix gifted activity into paid
movement — and, like every other analytics event, they are recorded only
server-side after an authenticated admin action (`analytics_service.
record_event`, called from `gift_subscription_service.py`), never
submittable from the browser (see `docs/ANALYTICS.md`'s ingestion-endpoint
section — `POST /api/analytics/event` only ever accepts `page_view`).

### 12.9 User-facing billing UI

`Billing.tsx` checks `subscription.provider === "gifted"` and, when true:
shows a "Gifted Subscription" badge instead of the Paddle status pill, an
explanatory notice ("This subscription was provided by Loady and does not
require payment.") instead of exposing any admin note, and hides every
Paddle-only action (Manage billing link, `<BillingManagement />`'s change
plan / cancel / resume / update-payment-method controls) — a gifted user
has no Paddle subscription to manage, so those controls would otherwise
404. `BillingManagement.tsx` itself independently refuses to render for
any non-`"paddle"` provider, so this is enforced in two places, not one.
Gifted users keep full entitled feature access throughout — only the
billing chrome changes.

### 12.10 Migration

`alembic/versions/7d2e9a4c1f83_add_gifted_subscription_fields.py`
(`down_revision = "4c8a1f2e6b9d"`, the analytics-events migration) adds two
nullable columns to `subscriptions` via `batch_alter_table` (required for
SQLite's lack of in-place `ALTER … ADD CONSTRAINT`, matching the existing
`224af020fc5a_add_admin_action_log_and_billing_...` migration's pattern):
`granted_by_admin_id` (FK → `users.id`) and `granted_reason`. Both are
purely additive and nullable — every existing row (paid or Free) is
unaffected; no existing `Subscription.provider` value is rewritten by this
migration, so existing paid subscriptions remain `paddle` and existing
Free accounts (no `Subscription` row at all) remain Free. Verified with a
clean upgrade + downgrade round-trip against a fresh SQLite database.

### 12.11 Emails

No new email is sent for a gifted-subscription grant/change/revoke — there
is no existing "admin changes a user's plan" email pattern to extend
(`grant-credits`/`status` toggles don't email either), and the mission
explicitly said not to introduce new Resend behavior for this feature.

### 12.12 Files

**Backend (new):** `app/services/gift_subscription_service.py`,
`alembic/versions/7d2e9a4c1f83_add_gifted_subscription_fields.py`,
`tests/test_gifted_subscriptions.py`.

**Backend (modified):** `app/models/commercial_enums.py`
(`SubscriptionProvider`, 3 `AdminActionType`/`AnalyticsEventType` values),
`app/database/commercial_models.py` (`granted_by_admin_id`,
`granted_reason`, disambiguated `Subscription.user`/`User.subscriptions`
relationships), `app/utils/exceptions.py`
(`PaidSubscriptionActiveError`), `app/models/commercial_schemas.py`
(`SubscriptionOut.provider`, gifted fields on `AdminUserOut`,
`AdminUpdateSubscriptionRequest`, `AdminOverviewOut.gifted_subscribers`),
`app/api/routes_admin.py` (new endpoint, gifted-aware overview counts),
`app/api/routes_account.py` (`SubscriptionOut.provider`),
`app/services/analytics_service.py` (paid-only filters, gifted counters),
`app/models/analytics_schemas.py` (`RevenueOut` gifted fields).

**Frontend (new):** `src/pages/Billing.test.tsx`.

**Frontend (modified):** `src/types/commercial.ts`
(`SubscriptionSource`, gifted fields/types), `src/types/analytics.ts`
(`RevenueOut` gifted fields), `src/services/api.ts`
(`adminUpdateSubscription`), `src/pages/admin/adminShared.tsx` (gift action
labels), `src/pages/admin/AdminUsers.tsx` (Manage-subscription modal,
badges, detail fields), `src/pages/admin/AdminOverview.tsx` (Gifted
subscriptions tile), `src/components/BillingManagement.tsx` (provider
guard), `src/pages/Billing.tsx` (gifted badge/notice, hidden Paddle
actions), `src/i18n/locales/{en,ar}.json`, plus test-fixture updates in
`AdminUsers.test.tsx`, `AdminOverview.test.tsx`, `AdminStatistics.test.tsx`,
`BillingManagement.test.tsx`, `i18n.test.tsx`, and the `SubscriptionOut`
literal in `AdSlot.test.tsx`, `Header.test.tsx`, `ProtectedRoute.test.tsx`,
`AuthContext.test.tsx`, `Dashboard.test.tsx`, `Pricing.test.tsx`.
