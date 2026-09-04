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
   structured error (see §3.4) if anything fails — no job is created.
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

### 3.4 Structured error codes

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
  (download_dir, concurrency, audio/video presets, timeouts — still
  legitimately shared, see below) and layers the job's owning user's own
  container_mode/cookie_source/cookie_file_path on top before handing it
  to `ytdlp_service.build_download_opts`, so what a job is gated against
  and what it actually runs with are guaranteed to match.
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
at the time — not the download_dir case below, which is flagged but not
yet fixed):

- `GET/PUT /api/settings` had **no authentication at all** — any
  unauthenticated caller could rewrite the shared `download_dir`,
  concurrency limit, theme, or audio/video defaults for the entire
  server. Now requires `Depends(get_current_user)`.
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

### 4.2 Known limitation: `download_dir` is still a shared, global setting

Unlike container_mode/cookie_source, `download_dir` (and the rest of
`AppSettings` — concurrency, theme, audio/video presets, timeouts) was
**deliberately left as one shared row** in this pass, for two reasons: (1)
it wasn't the specific bug reported (a gating false-positive from a shared
setting) — `download_dir` isn't read by any entitlement check, so no plan
gets incorrectly blocked by another user's folder choice; and (2) properly
fixing it is a materially bigger change (see below), not a settings-table
tweak.

It's still a real problem for a genuine multi-tenant deployment, and is
arguably worse than the bug just fixed: `resolve_safe_directory()`
explicitly does **not** constrain the chosen path to any root ("since the
user explicitly chooses their own download directory" — true for the
original single-operator desktop app, not true once "the user" is any
signed-up web visitor). Today, any authenticated account can point the
*shared* `download_dir` at an arbitrary writable path on the server, which
both misdirects every other user's downloads into that folder and is an
arbitrary-file-write primitive beyond just a settings leak. `cookie_source
=file`'s `cookie_file_path` has the same unconstrained-path shape, though
lower severity (it's read, not written, and parse failures don't echo file
contents back to the caller).

**Recommended fix** (not implemented here — flagged, not silently left,
per the instruction not to start unrelated scope creep in this pass): make
`download_dir` per-user like `container_mode`/`cookie_source`, but instead
of letting each user set an arbitrary absolute path, resolve it to a
fixed, non-configurable subfolder under one admin/ops-configured root
(e.g. `<download_root>/<user_id>/`), and apply the same containment to
`cookie_file_path` (require it under a per-user uploads directory rather
than an arbitrary server path). This is real work — new download-path
resolution logic, a Settings UI change (folder becomes read-only/display-
only for non-admin accounts), and its own isolation tests — which is why
it's called out as the next task rather than rushed into this pass.

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
  way to become an admin via the API. The first admin account has to be
  promoted directly against the database (a one-line UPDATE against
  `commercial.db`, or a small script) — a deliberate "no huge admin system"
  scoping decision, but worth automating with a management command before
  a real launch.
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
