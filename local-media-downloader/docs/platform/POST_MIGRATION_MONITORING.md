# Post-Migration Monitoring Plan (Mission 5, Phase 32)

No new external monitoring integration is built here — Mission 4/5's
readiness checklist already flags "no metrics/alerting pipeline" as a
HIGH gap, and standing one up is out of scope for this mission. This
document instead maps each monitoring window to signals this codebase
**already emits today** (structured logs, `/health`/`/ready`, audit
logs), so whatever log/metrics platform production eventually uses can
be pointed at them — and calls out explicitly which of these are
genuinely alertable today vs. log-only.

## What to watch, by window

### First 15 minutes (actively watch a terminal/dashboard)

- **Platform Core `/ready`** and **Loady `/api/health`** — poll every
  10-15s. Any non-200 is an immediate stop-and-look signal (this is
  exactly what `preflight-production-migration.sh` already checks once;
  post-cutover it should be watched continuously, not just once).
- **Login success/failure rate** — grep/count `WARNING` lines from
  `security_service`/`platform_identity_service` (invalid credentials,
  OIDC state mismatch, PKCE failure). A spike immediately after cutover
  suggests users hitting the "one-time re-login required" flow
  incorrectly, or a real config problem (wrong redirect URI, wrong
  client secret).
- **OAuth callback failures** — `InvalidTokenError`/`ForbiddenError` log
  lines from `routes_platform_auth.py` (state mismatch, account
  collision). Even one `ForbiddenError` here ("already linked to a
  different central identity") warrants immediate manual investigation —
  it means two Loady accounts are contending for one email.
- **Migration audit trail** — `SELECT * FROM audit_logs WHERE action =
  'loady_migration_import' ORDER BY created_at DESC` on Platform Core;
  cross-check counts against the reconciliation report produced during
  the commit run.

### First hour

- Everything above, at a lower polling frequency.
- **Refresh failures** — `_refresh_access_token` warning logs
  ("Platform Core token refresh failed"/"rejected") on Loady. Occasional
  ones are normal (an expired/revoked token); a sustained rate spike
  suggests a Platform Core-side problem (signing key, client secret,
  clock skew).
- **Entitlement cache fallback rate** — count `source: "cached"` vs.
  `source: "live"` in `get_entitlement_hybrid` results (not currently
  exposed as a metric — would need to be logged explicitly; today it's
  only visible by instrumenting a temporary debug log or querying
  `PlatformEntitlementCache.checked_at` freshness directly). Flag as a
  concrete gap: **this mission did not add a counter/metric for hybrid
  source**, only proved the underlying behavior correct live — tracked as
  a LOW-priority observability follow-up, not a blocker.
- **Download authorization failures/success** — `PlanLimitReachedError`/
  `FeatureNotIncludedError` rates from the download gate. A sudden rise
  in denials right after cutover, concentrated on **migrated** accounts
  specifically, is the signature of the phase-3 wiring misbehaving (e.g.
  fail-closed triggering for users who should be entitled) and should be
  cross-checked against Platform Core's own health/readiness first
  (a real outage would explain it; anything else needs code
  investigation).

### First 6 hours

- Everything above, at an even lower frequency, plus:
- **Central-disable propagation spot-check** — pick any account an
  admin disables in this window and confirm it loses access within the
  documented ~5-minute SLA (measured live at 302s in this mission's
  rehearsal — see `PRODUCTION_REHEARSAL_PLAN.md` phase 18). Note the
  known caveat found live: check via a **hard-auth** endpoint
  (`/api/auth/me`), not `/api/downloads`, which has a guest-tier fallback
  that will not show a 401 for a disabled session.
- **Gifted entitlement changes** — audit log entries for
  `gifted_access_granted`/`gifted_access_changed`/`entitlement_revoked`.
  Every one should have a real admin's `granted_by` — any null or
  unexpected actor here is a security review trigger, not a routine
  event.
- **5xx rate** on both services — the existing generic exception handler
  in `main.py` (Loady) and Platform Core's equivalent returns a clean
  500 with no stack trace to the client but does log the real traceback
  server-side; watch for a rise correlated with the cutover window
  specifically.

### First 24 hours

- Trend, don't just spot-check, everything above.
- **Unexpected Paddle mutation** — `SELECT count(*) FROM payment_records`
  on Platform Core should not increase at all due to anything this
  migration does (proven zero throughout this mission's entire
  rehearsal, including every gift grant). Any increase in this window
  that isn't a known, expected real Paddle webhook event is a rollback
  trigger (see `PRODUCTION_ROLLBACK_REHEARSAL.md`'s trigger list).
- **Admin errors** — any `ForbiddenError`/`AppError` from Grand Admin
  routes concentrated on one admin account may indicate a role-scoping
  regression; cross-check against `test_admin.py`'s
  product-scoped-admin-cannot-become-global-admin invariant, which
  should never be violated by production data.

### First 72 hours

- Confirm the metrics above have settled to a stable baseline (no
  elevated error rate specifically attributable to the migration).
- Decide, based on real data from this window, whether Phase 3's wiring
  (Platform Core as the entitlement authority for migrated users) should
  be widened to more of Loady's plan-display surface (see the known
  follow-up gap in `ENTITLEMENT_AVAILABILITY.md` — the account page
  still reads only the local `Subscription` row).

## Mission 15 addendum: webhook failures and outbox backlog

Phase 41 of the final pre-production mission asks these two signals be
explicit. Both are relevant only if the *separate* billing cutover
(`BILLING_CUTOVER_RUNBOOK.md`) is also in scope for a given deployment —
for an identity-only cutover, Platform Core's billing webhook endpoint
receives no real traffic yet and both counts should stay at zero
throughout every window above:

- **Webhook failures**: `SELECT count(*) FROM billing_webhook_events WHERE
  status = 'failed';` on Platform Core, trended across the same windows —
  a rising count is the sharpest signal that `paddle_provider.py`'s
  shape-mapping encountered something Sandbox testing didn't, per
  `BILLING_CUTOVER_RUNBOOK.md` Stage 5's own explicit monitoring
  instruction ("the number one signal that something in the shape-mapping
  was wrong despite Sandbox testing").
- **Outbox backlog**: `SELECT count(*) FROM outbox_events WHERE
  delivered_at IS NULL;` on Platform Core — a growing backlog indicates
  downstream delivery (to Loady or any other product) is failing or
  falling behind; `outbox_max_attempts`/`outbox_delivery_timeout_seconds`
  (`PRODUCTION_ENVIRONMENT_INVENTORY.md`) bound how long a single event
  retries before being marked failed, so a backlog that isn't shrinking
  over the retry window is real, not transient.

See `ALERT_THRESHOLDS.md` for where these cross from "log-only" to
"page someone."

## What existing production monitoring (Better Stack, per the user) can consume today

- Both services' structured stdout logs (already the existing pattern —
  no new log format introduced by this mission).
- `/api/health` (Loady) and `/health` + `/ready` (Platform Core) as
  standard HTTP uptime checks — already container-healthcheck-compatible,
  the same shape Better Stack or any uptime monitor expects.
- Nothing here requires a new agent, sidecar, or SDK — every signal above
  is either an existing log line or an existing HTTP endpoint. The only
  genuinely missing piece is the entitlement-hybrid-source counter noted
  above, which would need one new log line (not implemented in this
  mission) to become observable externally.
