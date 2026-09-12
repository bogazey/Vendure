# Web Statistics & Analytics (V1)

First-party, privacy-conscious analytics for Loady. No third-party analytics
vendor (Google Analytics, etc.) is used anywhere - every event is recorded
and reported by Loady's own backend, stored in the same commercial database
(SQLAlchemy, portable between SQLite and PostgreSQL) as users/billing.

## Architecture

```
Browser (page navigation)          Backend (authoritative actions)
        |                                    |
        v                                    v
POST /api/analytics/event          routes_analyze.py, routes_downloads.py,
(page_view ONLY)                   download_manager.py, routes_auth.py,
        |                          paddle_service.py (webhook handler)
        v                                    |
analytics_service.record_event()  <----------+
        |
        v
   analytics_events table (commercial DB)
        |
        v
GET /api/admin/analytics/*  (admin-only reporting)
        |
        v
  Admin > Statistics page (/admin/statistics)
```

`app/services/analytics_service.py` is the single writer of `AnalyticsEvent`
rows and the single place every admin reporting query lives - there is
exactly one implementation of each metric.

## Authoritative vs. browser-generated events

Per the design principle "prefer authoritative business data over analytics
events", only `page_view` is ever submitted by the browser. Everything else
is recorded server-side, at the moment the real action happens:

| Event | Recorded in | Trigger |
|---|---|---|
| `page_view` | `routes_analytics.py` | Browser SPA navigation (`usePageViewTracking` hook) |
| `analyze_started` / `_completed` / `_failed` | `routes_analyze.py` | `POST /api/analyze` |
| `download_started` | `routes_downloads.py` | `POST /api/downloads` (authenticated + guest) |
| `download_completed` / `_failed` | `download_manager.py` | Job reaches a terminal state (background task) |
| `signup_completed` | `routes_auth.py` | `POST /api/auth/signup` |
| `plan_upgraded` / `plan_downgraded` | `paddle_service.py` | Paddle webhook changes a subscription's plan (includes the initial `free -> pro`/`free -> creator` conversion) |
| `subscription_cancelled` | `paddle_service.py` | Paddle webhook cancels a subscription |
| `gifted_subscription_granted` / `_changed` / `_revoked` | `gift_subscription_service.py` | An admin grants/changes/revokes a **gifted** (non-Paddle) subscription via `PATCH /api/admin/users/{id}/subscription` |

The three gifted-subscription event types are deliberately **never** mixed
into the `plan_upgraded`/`plan_downgraded`/`subscription_cancelled` set
above - those three remain exclusively Paddle-webhook events, so a
revenue-movement query can never accidentally count a gifted grant as a
paid conversion. Like every other server-recorded event, they are written
only after an authenticated `require_admin` action ever reaches
`gift_subscription_service.py` - never accepted from the browser (see
"Ingestion endpoint security" below, which restricts the one browser-facing
endpoint to `page_view` only).

Business/entitlement facts that already have an authoritative source are
**never** recomputed from analytics events:

- Current plan distribution (Free/Pro/Creator counts): `Subscription` table (existing `AdminOverviewOut`, unchanged).
- New paid subscriber count: `Subscription.created_at` (a `Subscription` row is only ever created the first time a user's Paddle subscription is created - Free has no row at all).
- Total/active users: `User` table.
- Per-user download history (My Downloads / History page): the existing `history_repo` SQLite table, unchanged.

## Privacy model

- **No media URLs.** Neither `AnalyticsEvent` nor any query against it ever
  touches `request.url`/`CreateDownloadRequest.url`. Only `source_platform`
  (`youtube`/`tiktok`/`instagram`/`facebook`/`unknown` - Loady's existing
  `Platform` enum) is recorded.
- **No raw IP addresses, ever.** There is no IP column on `analytics_events`
  at all. The client IP is used only transiently, exactly as it already was
  before this feature, by the existing per-endpoint rate limiters.
- **No full User-Agent strings.** Only three bounded, parsed fields are kept:
  `device_type` (desktop/mobile/tablet/other), `browser_family`
  (chrome/firefox/safari/edge/other), `os_family`
  (windows/macos/ios/android/linux/other) - see `app/utils/ua_parse.py`, a
  small dependency-free parser (no new library).
- **No full referrer URLs.** Only the registrable domain is stored
  (`extract_referrer_domain`); a referrer matching Loady's own host (in-app
  navigation) is treated as absent ("Direct").
- **No generic metadata blob.** Every field on `AnalyticsEvent` is a specific,
  named, typed column - there is no JSON "extra data" column a caller could
  smuggle arbitrary data through.
- **No fingerprinting.** The anonymous visitor id is a single random token
  (`secrets.token_urlsafe(24)`), never a composite of fonts/canvas/screen/
  hardware signals.

## Visitor identification

An anonymous visitor id is minted server-side into an httpOnly, first-party
cookie (`lmd_visitor`, `SameSite=Lax`, `Secure` in production, 365-day
`Max-Age`, `path=/`) the first time any tracked endpoint runs
(`analytics_service.ensure_visitor_id`). Unlike the guest-download-quota
cookie (`lmd_guest`), this id is **never validated against a server-side
row** - it grants no privilege, so a cleared or forged cookie can only skew
that one browser's own analytics, never another visitor's data or any
entitlement. `httpOnly` means frontend JavaScript never reads or sends it
explicitly; it rides along automatically on same-origin `fetch(...,
{credentials: "include"})` calls, exactly like the existing auth/guest
cookies.

Logged-in users are additionally tagged with their real `user_id` (derived
server-side from the existing access-token cookie, never trusted from the
request body) so admin reporting can distinguish "new user" and "paid
conversion" cohorts - but the anonymous `visitor_id` and the authenticated
`user_id` remain two separate columns; no internal user id is ever exposed
to another user.

**Session tracking is not implemented in V1.** "Unique visitors" and "Active
Now" are computed directly from `visitor_id` + `timestamp` (see below); a
true session concept (session start/end, session count) is left as a
documented future extension rather than invented from partial data.

## IP handling

Loady runs behind Cloudflare in production (`frontend/nginx.tls.conf` +
`frontend/cloudflare-realip.conf`, which already trusts `CF-Connecting-IP`
from Cloudflare's published edge ranges and rewrites `X-Forwarded-For` to
the real visitor IP - this pre-dates this feature and is unchanged).
Analytics adds exactly one thing to that existing trust boundary: forwarding
Cloudflare's own `CF-IPCountry` header to the backend
(`proxy_set_header CF-IPCountry $http_cf_ipcountry;`, added only to
`nginx.tls.conf`, the config actually paired with `cloudflare-realip.conf`
in `compose.tls.yml` - **not** added to the plain `nginx.conf`, which is
never deployed behind that same Cloudflare real-IP trust boundary). The
backend reads only this header (`analytics_service.request_country_code`),
treats Cloudflare's own "unknown" sentinel (`XX`) as absent, and **never**
derives geography from a stored IP - no IP is stored at all. If this header
is ever unavailable (local dev, a deployment without the TLS/Cloudflare
overlay), `GET /api/admin/analytics/geography` honestly reports
`available: false` with an empty list rather than fabricating countries.

No paid geolocation service was added, per the V1 scope in the mission spec.

## Event schema

`analytics_events` (see `app/database/commercial_models.py`):

`id`, `event_type`, `visitor_id`, `user_id`, `timestamp`, `path`, `locale`,
`referrer_domain`, `utm_source`, `utm_medium`, `utm_campaign`, `job_id`,
`source_platform`, `media_type`, `format`, `failure_category`, `plan`,
`from_plan`, `country_code`, `device_type`, `browser_family`, `os_family`,
`client` (always `"web"` in V1 - reserved for a future
`chrome_extension`/`firefox_extension`/`safari_extension` value once browser
extensions exist; no extension analytics are implemented now).

Indexes: `event_type`, `visitor_id`, `user_id`, `timestamp`, `path`,
`job_id`, and a composite `(event_type, timestamp)` for the most common
"count events of type X in a date range" query shape.

`job_id` lets a `download_started` row be joined to its matching
`download_completed`/`download_failed` row for a genuine average
processing-time measurement (`get_downloads`'s `_stage_stats`), without
guessing.

## Bot filtering

`app/utils/bot_detect.py` matches common crawler/bot User-Agent substrings
(Googlebot, Bingbot, common SEO/scraper tools, missing User-Agent, etc.).
A matched request's `page_view` is simply not recorded - this is analytics
filtering only, never a firewall rule. SEO crawling itself (see
`docs/SEO.md`) is completely unaffected: robots.txt, sitemaps, and the
prerendered HTML pages are served identically to bots and humans.

## Path normalization

Raw SPA paths are collapsed to a small, bounded set of canonical keys
(`analytics_service.normalize_path`) before being stored:

- Known static routes (`/`, `/pricing`, `/dashboard`, `/admin/statistics`, ...) map to themselves.
- The bilingual SEO tool pages aggregate by canonical page, not by locale: `/en/video-downloader` and `/ar/video-downloader` both store `path="/video-downloader"` (locale itself is tracked separately via the `locale` column, so per-locale traffic is still answerable).
- Anything unrecognized (which should never happen from Loady's own frontend) buckets into `/other` rather than persisting an arbitrary, potentially attacker-controlled string.

Query strings and hash fragments are always stripped server-side, regardless
of what the client sends.

## Metrics definitions

- **Visitor**: a unique `visitor_id` associated with at least one `page_view` event in the selected period.
- **Page View**: one normalized SPA navigation (deduplicated client-side against React 18 StrictMode's dev-only double-invoke and same-path re-renders - see `usePageViewTracking`).
- **Active Now**: a `visitor_id` with any recorded event in the last 5 minutes.
- **Download Started**: the server accepted a download job (credit/quota reservation succeeded, job queued) - see `routes_downloads.create_download`.
- **Download Completed**: the job reached `DownloadStage.COMPLETED` (file fully written and validated).
- **Download Failed**: the job reached `DownloadStage.FAILED`. A user-initiated cancellation is **not** counted as failed (it's an intentional stop, not an error) and is excluded from the success-rate denominator, though it still counts toward "started".
- **Paid User / New Paid Subscriber**: a `Subscription` row exists **with `provider == "paddle"`** (authoritative - Free plan has no row at all, and a gifted subscription's row is explicitly excluded so it can never be counted as a paid conversion; see "Gifted subscriptions" below).
- **Conversion Funnel**: an aggregate **period** count at each stage (distinct visitors doing X within the selected range), explicitly **not** a per-visitor cohort funnel - a visitor counted at one stage is not guaranteed to be the same person counted at the next. The admin UI and API both carry this disclaimer verbatim (`FunnelOut.methodology_note`).
- **"Today"**: a UTC calendar day (`00:00:00 UTC` to now), matching every other timestamp in this app (`UTCDateTime`) - there is no separate "admin timezone" convention elsewhere to follow instead.

## Revenue: what's shown and what's deliberately omitted

`Subscription` does not persist which billing period (monthly vs. annual)
each subscription uses - it's resolved from Paddle's price id only at
request time (`account_service`/`paddle_service`), not stored. Computing a
monthly-normalized MRR would require guessing which price applies to each
active subscription. Per the "accuracy over visual completeness" principle,
**MRR is not shown** (`RevenueOut.mrr_available = false`, with an explanatory
`mrr_note`) rather than estimated. What *is* shown, because it comes
directly from authoritative data with no guessing:

- Active paid subscribers (live `Subscription` count, filtered to `provider == "paddle"`).
- New paid subscribers this period (`Subscription.created_at` in range, same paddle-only filter).
- Cancellations this period (`subscription_cancelled` events, recorded synchronously with the real webhook state change - gifted subscriptions never emit this event, see below).
- Plan movements this period (`plan_upgraded`/`plan_downgraded` events, each carrying both `from_plan` and `plan` so direction is never guessed).

To add real MRR later: persist `billing_period` (and the price actually
charged) on `Subscription` at webhook-write time, then sum
`monthly-equivalent price` over active subscriptions.

### Gifted subscriptions are never revenue

An admin can grant a Pro/Creator subscription without payment (see
`COMMERCIAL_ARCHITECTURE.md` §12) by setting `Subscription.provider =
"gifted"` instead of `"paddle"`. Every "paid" query above filters on
`provider == "paddle"` explicitly, so a gifted subscription:

- Contributes **0** to `active_paid_subscribers`, `new_paid_subscribers`,
  and `paid_conversions` - never combined with real paid counts.
- Is counted **only** in its own, separate fields:
  `RevenueOut.gifted_active_subscriptions` and `RevenueOut.
  gifted_events_this_period` (`AdminOverviewOut.gifted_subscribers` on the
  main Overview page, similarly separate from `pro_count`/`creator_count`).
- Never emits `plan_upgraded`/`plan_downgraded`/`subscription_cancelled` -
  those three remain exclusively Paddle-webhook events. It emits its own
  `gifted_subscription_granted`/`_changed`/`_revoked` events instead
  (`gift_subscription_service.py`), which no revenue-movement query reads.

There is no code path anywhere that sums gifted and paid counts together.

## Admin API

All under `/api/admin/analytics/*`, all gated by the existing
`require_admin` dependency (same pattern as every other `/api/admin/*`
route) - anonymous → 401, non-admin user → 403, admin → 200 (see
`tests/test_analytics.py::TestAdminAuthorization`). Every route takes a
`range` query param restricted to `today | 7d | 30d | 90d` (rejects anything
else with 422 before any query runs, bounding worst-case query cost):

`overview`, `traffic`, `pages`, `sources`, `geography`, `devices`,
`downloads` (folds in platform + failure-category breakdowns), `funnel`,
`revenue`.

## Ingestion endpoint security (`POST /api/analytics/event`)

Treated as fully untrusted input from any visitor, signed in or not:

- Only `event_type: "page_view"` is a valid shape at all (Pydantic `Literal`) - there is no way to submit a business/revenue event from the browser, structurally, not just by convention.
- `visitor_id` and `user_id` are always derived server-side (cookie / `get_optional_user`), never read from the JSON body, even if the body includes them (tested).
- `path`, `utm_*` are length- and character-bounded by the schema; `path` is further normalized/whitelisted server-side; `utm_*` values are re-validated against `^[A-Za-z0-9_.\-]{1,100}$`, silently dropped (not erroring the request) if they don't match.
- `referrer` is reduced to a bounded registrable domain, never stored as a full URL.
- Rate limited per visitor (`analytics_limiter`, 120 events / 5 minutes) - the same in-process sliding-window limiter pattern already used for auth/analyze/billing.
- Country/device/browser/OS are derived server-side from request headers, never accepted from the body.

## Frontend resilience

`usePageViewTracking` (`frontend/src/lib/pageTracking.ts`) always
`.catch()`s the tracking call - a network failure, ad blocker interference
on some unrelated rule, or a 429 from the rate limiter never surfaces to the
user and never blocks navigation. The hook fires once per pathname change,
guarded by a ref that also collapses React 18 StrictMode's dev-only
double-invoke to a single call (see
`pageTracking.test.tsx`). The same "must not break the primary flow"
principle applies to every server-side recording call: `download_manager.py`
wraps its analytics write in its own try/except (mirroring the existing
`_finalize_usage` pattern) so an analytics failure can never fail a real
download.

## Retention

Raw `analytics_events` rows are purged after `ANALYTICS_RETENTION_DAYS`
(default 90, configurable, 1-365) by `analytics_service.purge_expired_events`,
called from the **existing** periodic cleanup loop
(`media_cleanup_service.periodic_cleanup` / `cleanup_once`) rather than a
new scheduler. There is no separate aggregated/long-term rollup table in V1
(see Scaling below).

## Scaling considerations (V1 traffic level)

- All reporting queries run directly against the raw `analytics_events`
  table with the indexes listed above; this is appropriate for Loady's
  current traffic and keeps V1 simple (no ETL/rollup pipeline to maintain).
- If raw-table scans become expensive as volume grows, the natural next
  step is a `analytics_daily_stats` rollup table (one row per
  day/event_type/dimension), populated by the same periodic cleanup task,
  with the admin API reading from it for anything older than a short recent
  window (e.g. last 48h reads raw, older reads the rollup). This is a
  documented upgrade path, not implemented now, per "do not over-engineer."
- Event recording is a single lightweight `INSERT` per event and never blocks
  the download pipeline itself (server-side events are recorded via already-
  open sessions or a dedicated best-effort session in `download_manager.py`,
  never by waiting on aggregation).

## Files

**Backend (new):** `app/services/analytics_service.py`,
`app/api/routes_analytics.py`, `app/api/routes_admin_analytics.py`,
`app/models/analytics_schemas.py`, `app/utils/bot_detect.py`,
`app/utils/ua_parse.py`, `alembic/versions/4c8a1f2e6b9d_add_analytics_events.py`,
`tests/test_analytics.py`.

**Backend (modified):** `app/database/commercial_models.py` (new
`AnalyticsEvent` model), `app/models/commercial_enums.py` (new
`AnalyticsEventType`/`AnalyticsFailureCategory`), `app/config/
commercial_settings.py` (`analytics_retention_days`), `app/api/deps.py`
(`VISITOR_COOKIE_NAME`), `app/services/rate_limit_service.py`
(`analytics_limiter`), `app/main.py` (router wiring), `app/api/
routes_analyze.py`, `app/api/routes_downloads.py`, `app/api/routes_auth.py`,
`app/services/download_manager.py`, `app/services/paddle_service.py`,
`app/services/media_cleanup_service.py` (retention purge wired into the
existing cleanup loop).

**Frontend (new):** `src/types/analytics.ts`, `src/lib/pageTracking.ts` (+
test), `src/pages/admin/AdminStatistics.tsx` (+ test).

**Frontend (modified):** `src/services/api.ts` (analytics methods),
`src/App.tsx` (tracking hook + `/admin/statistics` route),
`src/pages/admin/AdminLayout.tsx` (Statistics tab),
`src/pages/admin/AdminOverview.tsx` (+ test - small analytics summary row),
`src/i18n/locales/{en,ar}.json`, `src/i18n/i18n.test.tsx` (mock update),
`frontend/nginx.tls.conf` (`CF-IPCountry` passthrough),
`frontend/nginx.conf` + `nginx.tls.conf` (`/admin/statistics` route
allowlist).
