# Loady Production Cutover Runbook

Operator-grade, step-by-step. Every step states COMMAND/ACTION, EXPECTED
RESULT, and STOP CONDITION. No real secrets appear anywhere in this
document. **This runbook has not been executed against production** —
every command shape is proven against `loady-staging`/
`platform-core-staging` in Mission 5's rehearsal
(`PRODUCTION_REHEARSAL_PLAN.md`, `PRODUCTION_ROLLBACK_REHEARSAL.md`);
production container/host names must be substituted by the operator
running this for real.

## A. 24 hours before

- **ACTION**: Confirm the production VPS has at least 1.5 GB free RAM and
  2 GB free disk (`free -h`, `df -h`) — see `PRODUCTION_CAPACITY_PLAN.md`.
  **EXPECTED**: both minimums met. **STOP IF**: either is below minimum —
  free up resources or postpone.
- **ACTION**: Confirm Platform Core's production secrets exist and are
  provisioned out of band (signing key file, `PLATFORM_TOKEN_ENCRYPTION_KEY`,
  Postgres password, `SECRET_KEY`) per `PRODUCTION_SECRET_INVENTORY.md`.
  **EXPECTED**: every secret in the inventory has a real value in place,
  none of them the mission's staging values. **STOP IF**: any secret is
  missing, or any staging/example value is still present in a production
  config file.
- **ACTION**: Confirm DNS/Cloudflare records for whichever hostnames
  `PRODUCTION_TOPOLOGY.md` calls for (e.g. `id.loady.cc`, `admin.loady.cc`)
  are created and proxied. **EXPECTED**: both resolve and terminate TLS
  correctly (a plain `curl -I` from outside the VPS). **STOP IF**: DNS
  hasn't propagated or TLS isn't Full-strict yet — this is real,
  externally-visible infrastructure this mission could not create or
  verify.
- **ACTION**: Announce the maintenance window to whatever channel Loady
  uses for user-facing status (out of scope for this mission to define).
  **EXPECTED**: users know a short window is coming. **STOP IF**: no
  communication channel exists yet — decide whether that's acceptable
  for this cutover's risk tolerance.

## B. 1 hour before

- **ACTION**: Re-run `preflight-production-migration.sh --env production`.
  **EXPECTED**: `GO`. **STOP IF**: `NO-GO` — resolve every listed reason
  and re-run before continuing.
- **ACTION**: Confirm the on-call operator has this runbook open and the
  rollback script (`rollback-platform-migration.sh`) ready to run.
  **EXPECTED**: both are accessible without needing to search for them
  mid-incident. **STOP IF**: not ready.

## C. Maintenance start

- **ACTION**: Set `MAINTENANCE_MODE=true` in Loady production's env file
  and restart the backend. **EXPECTED**: `GET /api/health` still returns
  200; any `POST`/`PUT`/`PATCH`/`DELETE` returns `503` with
  `"code":"MAINTENANCE_MODE"` (verified live against staging in this
  mission's phase 6). **STOP CONDITION**: if health checks themselves
  start failing (not just mutations being blocked), abort — that's a
  deploy problem, not a maintenance-mode problem; revert
  `MAINTENANCE_MODE` and investigate before proceeding.
- **EXPECTED DURATION of the whole window (C through N)**: 10-15 minutes
  at Loady's current production data scale, based on this mission's
  measured staging timings (migration commit + reconciliation together
  took well under a minute at 51 synthetic users; production's real user
  count will take longer but the per-row cost is the same lightweight
  operation) plus human verification time at each gate below. If any
  single step is taking dramatically longer than its staging-measured
  time, that is itself a signal to stop and investigate rather than wait
  indefinitely.

## D. Final backup

- **ACTION**: Run `backup-before-platform-migration.sh --env production
  --out <backup-dir>`. **EXPECTED**: all artifacts written, checksums
  printed. **STOP IF**: the script exits non-zero for any reason.
- **ACTION**: Run `verify-backup-restorable.sh <backup-dir>` immediately.
  **EXPECTED**: `Backup at <dir> is verified restorable.` **STOP
  CONDITION (hard)**: any checksum or restore failure here is an
  automatic abort of the entire cutover — do not proceed with an
  unverified backup, ever.

## E. Platform Core startup (if not already running continuously in production)

- **ACTION**: Bring up Platform Core's production stack.
  **EXPECTED**: `/health` → `{"status":"ok"}`, `/ready` →
  `{"status":"ok","checks":{"database":true,"signing_key":true}}`.
  **STOP IF**: either check fails — this mission's phase 15/16 rehearsals
  showed exactly what a real failure here looks like (503 with
  `database:false`, or a hard container-start failure for a missing
  signing key); do not proceed past a red `/ready`.

## F. Migration dry run

- **ACTION**: Run `loady_migration_dry_run.py --loady-database-url
  <production-url>` (no `--commit`). **EXPECTED**: a report of
  created/linked/skipped/conflicted/failed counts that look plausible
  against the known production user count; zero writes (this mission
  verified via direct row-count comparison — a production operator
  should do the same, comparing `SELECT count(*) FROM users WHERE
  global_user_id IS NOT NULL` before and after). **STOP IF**: the
  `--loady-database-url` contains "production" and the script refuses to
  run — this means the safety guard is working as intended and the
  command needs a different invocation path, not that the guard should
  be bypassed. **STOP IF**: `failed` count is anything other than what
  was expected/investigated in advance, or `conflicted` count is
  non-zero and each conflict hasn't been manually reviewed.

## G. GO/NO-GO

- **ACTION**: Run `preflight-production-migration.sh --env production`
  again (state may have changed since step B). **EXPECTED**: `GO`.
  **STOP CONDITION (hard)**: `NO-GO` — do not proceed to commit under any
  circumstance; lift maintenance mode and reschedule.

## H. Migration commit

- **ACTION**: Run `loady_migration_dry_run.py --loady-database-url
  <production-url> --commit --reason "Production cutover <date>"`.
  **EXPECTED**: created/linked/skipped/conflicted/failed counts matching
  the dry run from step F exactly (same shape — this mission's rehearsal
  confirmed dry run and commit produce identical classification, only
  commit actually writes). **STOP CONDITION**: any count differs
  unexpectedly from the dry run — investigate before proceeding to
  reconciliation; do not assume it's fine.

## I. Reconciliation

- **ACTION**: Compare pre/post manifests per
  `PRODUCTION_REHEARSAL_PLAN.md`'s Phase 9 criteria (user count,
  disabled/verified counts, history row count, entitlement source
  breakdown, zero `PaymentRecord` rows, admin role assignment count).
  **EXPECTED**: every invariant holds with zero unexplained deltas — this
  mission's own reconciliation report
  (`rehearsal-artifacts/reconciliation_report.json`, local-only) is the
  template to follow. **STOP CONDITION (hard, rollback trigger)**: any
  mismatch in user count, history ownership, or a non-zero
  `PaymentRecord` count — see Rollback Triggers below.

## J. SSO validation

- **ACTION**: Pick one real (consenting, ideally staff) migrated account.
  Log in via Platform Core with their existing password. **EXPECTED**:
  success, and (if other products are live) the same session works
  across products without a second password. **STOP CONDITION**: login
  fails for a known-correct password — this is a rollback trigger
  (password/hash migration failure).

## K. Entitlement validation

- **ACTION**: For the same test account (and, if possible, one known
  Pro/Creator/gifted account), confirm Grand Admin shows the correct
  entitlement and it matches what that account had before migration.
  **EXPECTED**: match. **STOP CONDITION**: an entitlement is wrong,
  missing, or shows an unexpected `source` — rollback trigger.

## L. Download validation

- **ACTION**: With the test account, attempt one real, small download at
  that account's correct plan ceiling. **EXPECTED**: succeeds, and a
  request above that ceiling is correctly denied (this mission's phase 13
  live test is the template). **STOP CONDITION**: capability
  mismatch in either direction (denied when it shouldn't be, or allowed
  when it shouldn't be) — the second case especially is a hard rollback
  trigger (entitlement corruption / privilege escalation).

## M. Grand Admin validation

- **ACTION**: Search for the test account in Grand Admin, view its
  identity/membership/entitlement, confirm audit log shows the migration
  import event. **EXPECTED**: all present and correct. **STOP CONDITION**:
  Grand Admin itself is inaccessible or shows incorrect data — rollback
  trigger (admin inaccessible).

## N. Maintenance end

- **ACTION**: Set `MAINTENANCE_MODE=false` and restart Loady's backend.
  **EXPECTED**: normal signup/login/download traffic resumes
  immediately — no restart-induced data loss (verified live, Mission 5
  phase 19: full-stack restart left every dataset byte-identical).
  **STOP CONDITION**: none — this step should always be safe to perform;
  if something upstream (H-M) failed, maintenance mode should already
  have been lifted as part of that step's own rollback, not left on
  indefinitely.

## O. Post-cutover monitoring

- **ACTION**: Follow `POST_MIGRATION_MONITORING.md`'s window-by-window
  checklist (15 min / 1 hr / 6 hr / 24 hr / 72 hr).

## P. Rollback triggers (objective, decided in advance — Mission 5, Phase 31)

Roll back immediately (no further debugging in production first) if any
of the following is observed:

1. **Migration reconciliation mismatch** — any user-count, history-
   ownership, or entitlement-source discrepancy found in step I that
   isn't immediately, obviously explained (e.g. a known pre-existing
   test account).
2. **Unexpected user-count mismatch** — Loady's total user count changes
   by anything other than zero (the migration must never create or
   delete a Loady user row, only link existing ones).
3. **History ownership mismatch** — any download history row's owner
   changes, or a history row becomes unowned/cross-linked to the wrong
   account.
4. **Login failure rate above threshold** — more than a handful of
   genuine (non-bot, non-typo) login failures for accounts known to have
   correct passwords, concentrated in the post-cutover window.
5. **Platform Core cannot remain healthy** — `/ready` failing repeatedly
   and not recovering within a few minutes (contrast with the *designed*
   hybrid-availability tolerance for a brief outage — this trigger is
   for a Platform Core that will not come back, not one that's briefly
   down while Loady correctly serves cached entitlements).
6. **Signing failure** — any evidence of token forgery, algorithm
   confusion, or the signing key needing unplanned regeneration.
7. **Entitlement corruption** — any account showing a plan/entitlement it
   should not have (privilege escalation direction is always the harder
   stop than a fail-closed denial).
8. **Admin inaccessible** — Grand Admin login or the super-admin role
   itself broken, since that also blocks executing the rollback's own
   Grand-Admin-mediated recovery steps if any are needed.
9. **Download gate failure** — the phase-13-style capability check
   granting access it shouldn't (hard trigger) or denying it broadly to
   accounts that should have it (softer trigger — investigate first if
   isolated, roll back if widespread).
10. **Database corruption** — any integrity-check failure, foreign-key
    violation, or unexplained data anomaly in either database.
11. **Unexpected Paddle mutation** — any `PaymentRecord` created,
    modified, or referenced by anything this migration touches; Paddle
    itself must never be called by any code path exercised during
    cutover.

**Rollback procedure**: `rollback-platform-migration.sh --env production
--layer kill-switch` first (instant, no data touched); escalate to
`--layer full-restore --backup-dir <step-D-backup>` only if the
kill-switch alone doesn't resolve the trigger. See
`PRODUCTION_ROLLBACK_REHEARSAL.md` for the measured timing breakdown and
the two real limitations found by actually rehearsing this (Grand-Admin-
only entitlement changes are not preserved by rollback; re-running the
migration after rollback resyncs — and can silently downgrade — already-
linked accounts' entitlements).

## Q. Rollback procedure

See section P above and `PRODUCTION_ROLLBACK_REHEARSAL.md` in full. Do
not improvise a rollback under incident pressure — every step in that
document was actually run and timed; deviating from it during a real
incident reintroduces exactly the risk this rehearsal exists to remove.
