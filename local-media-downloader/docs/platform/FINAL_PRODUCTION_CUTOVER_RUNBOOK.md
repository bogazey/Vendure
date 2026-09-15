# Final Production Cutover Runbook (Mission 15, Phase 26)

**Nothing in this document has been executed.** This is the single,
authoritative, executable step-by-step runbook for a future, separately
authorized cutover, combining Platform Core's deployment (this mission's
package) with the identity migration
(`LOADY_PRODUCTION_MIGRATION_PLAN.md`/`LOADY_PRODUCTION_CUTOVER_RUNBOOK.md`,
Missions 3/5) into one sequence. It supersedes neither of those documents
— it cites their already-detailed steps rather than duplicating them, and
adds the steps this mission's own phases established (Platform Core
verification, the consolidated GO/NO-GO gate, billing/entitlement/admin
validation, the Cloudflare cache fix). Every command below uses
`<PLACEHOLDER>` for anything secret or environment-specific — no real
value is ever written here.

Every command in this runbook assumes `set -euo pipefail` is already the
calling shell's mode (per Phase 27, below) and that the operator has read
`FINAL_PRODUCTION_ROLLBACK_RUNBOOK.md` (Phase 38) before starting, not partway
through.

## T-24H

- **PURPOSE**: give the business, support, and on-call operator enough
  notice to actually prepare, and to catch a scheduling conflict.
- **COMMAND**: none — human coordination.
- **EXPECTED RESULT**: window confirmed with whoever owns customer
  communication; on-call operator confirmed available for the full window
  plus the 24-hour observation period after.
- **STOP CONDITION**: no communication channel exists yet, or no operator
  is available for the full window + observation — reschedule.
- **ROLLBACK IMPLICATION**: none — nothing has happened yet.

## T-1H

- **PURPOSE**: catch any infrastructure problem with hours of margin
  instead of minutes.
- **COMMAND**:
  ```bash
  scripts/platform/production-preflight-inspection.sh --env production
  ```
- **EXPECTED RESULT**: `GO`.
- **STOP CONDITION**: `NO-GO` — resolve every listed reason and re-run
  before continuing. Do not proceed to T-15MIN on a `NO-GO`.
- **ROLLBACK IMPLICATION**: none — purely informational at this point.

## T-15MIN

- **PURPOSE**: final human readiness check immediately before the window
  opens.
- **COMMAND**: none — human confirmation.
- **EXPECTED RESULT**: operator has this runbook open, the rollback
  runbook open, and `rollback-platform-migration.sh` located and
  confirmed executable. Cloudflare dashboard access confirmed available
  (for the cache-purge step at MAINTENANCE END, per
  `CLOUDFLARE_CUTOVER_PLAN.md`).
- **STOP CONDITION**: any of the above not ready.
- **ROLLBACK IMPLICATION**: none.

## PLATFORM CORE VERIFICATION

*(Performed before MAINTENANCE START — Platform Core carries zero time
pressure, per `PRODUCTION_DEPLOYMENT_SEQUENCING.md` Phase 22. If Platform
Core is already deployed and was verified in a prior session, re-confirm
rather than skip — state may have changed.)*

- **PURPOSE**: prove Platform Core is healthy, correctly keyed, and
  correctly wired to Loady, entirely before Loady's own users are ever
  affected.
- **COMMAND**:
  ```bash
  curl -f https://id.<domain>/health
  curl -f https://id.<domain>/ready          # expect signing_key: true in the JSON body
  curl -f https://id.<domain>/.well-known/jwks.json   # confirm the expected kid is present
  docker exec <loady-backend-container> printenv PLATFORM_TOKEN_ENCRYPTION_KEY >/dev/null && echo "set"  # presence only, never print the value
  ```
- **EXPECTED RESULT**: all four succeed; JWKS response contains the
  configured `JWT_KEY_ID`; the encryption-key presence check prints `set`.
- **STOP CONDITION**: any failure — do not proceed to MAINTENANCE START
  with Platform Core unverified.
- **ROLLBACK IMPLICATION**: none — Platform Core is still inert
  (`PLATFORM_CLIENT_ID` unset in Loady) at this point; nothing to roll
  back.

## MAINTENANCE START

- **PURPOSE**: block mutating traffic to Loady so the migration commit
  never races a live write.
- **COMMAND**:
  ```bash
  # set MAINTENANCE_MODE=true in Loady's production env, then:
  docker compose -p loady restart backend
  curl -f https://loady.cc/api/health          # must still succeed
  curl -X POST https://loady.cc/api/some-mutating-endpoint  # must return 503 MAINTENANCE_MODE
  ```
- **EXPECTED RESULT**: health still 200; mutations 503 with
  `{"code":"MAINTENANCE_MODE"}` and `Retry-After` (verified live in a
  prior mission's staging rehearsal).
- **STOP CONDITION**: health checks themselves fail (not just mutations
  blocked) — abort, revert `MAINTENANCE_MODE`, investigate as a deploy
  problem before retrying.
- **ROLLBACK IMPLICATION**: trivially reversible — set
  `MAINTENANCE_MODE=false` and restart.
- **NEW THIS MISSION**: confirm (per `CLOUDFLARE_CUTOVER_PLAN.md`) no
  Cloudflare Cache Rule caches HTML for `loady.cc/*` before proceeding —
  closes the maintenance-page caching gap this mission found.

## FINAL BACKUP

- **PURPOSE**: an up-to-the-minute, checksummed, restorable backup before
  any write.
- **COMMAND**:
  ```bash
  BACKUP_ENCRYPTION_PASSPHRASE=<PLACEHOLDER> PLATFORM_MIGRATION_CONFIRM=I_UNDERSTAND_THIS_IS_PRODUCTION \
    LOADY_PG_CONTAINER=<container> LOADY_PG_DB=<db> LOADY_PG_USER=<user> LOADY_BACKEND_CONTAINER=<container> \
    PLATFORM_PG_CONTAINER=<container> PLATFORM_PG_DB=<db> PLATFORM_PG_USER=<user> \
    scripts/platform/backup-before-platform-migration.sh --env production --out <backup-dir> --retention-days 30
  ```
- **EXPECTED RESULT**: all artifacts written, checksums printed, exit 0.
  **NEW THIS MISSION**: the script now runs a disk-space preflight
  (Phase 20) before writing anything — if it prints `NO-GO: insufficient
  free disk space`, this step fails safely, before touching the disk
  further, rather than partway through.
- **STOP CONDITION**: any non-zero exit.
- **ROLLBACK IMPLICATION**: this step *is* what makes rollback possible —
  do not proceed past it on any failure.

## BACKUP VERIFICATION

- **PURPOSE**: never trust a backup that hasn't been proven restorable.
- **COMMAND**:
  ```bash
  scripts/platform/verify-backup-restorable.sh --backup-dir <run-dir-from-previous-step>
  ```
- **EXPECTED RESULT**: restores into an isolated container, confirms row
  counts/schema version match, exit 0.
- **STOP CONDITION**: any mismatch or failure — do not proceed with an
  unproven backup.
- **ROLLBACK IMPLICATION**: this step confirms rollback will actually
  work if needed later in this same window.

## MIGRATION DRY RUN

- **PURPOSE**: see the exact shape of the real commit before committing
  anything, per `FINAL_MIGRATION_DRY_RUN_PROCEDURE.md`.
- **COMMAND**:
  ```bash
  python -m app.scripts.loady_migration_dry_run \
    --loady-database-url <restored-snapshot-from-BACKUP-step-above> \
    --reason "Production cutover dry run, <date>" | tee <dry-run-report-path>
  ```
- **EXPECTED RESULT**: `failed=0 conflicted=0` (or every conflict
  individually understood and accepted in advance).
- **STOP CONDITION**: any unexpected `conflicted`/`failed` row — stop,
  investigate, do not proceed to GO/NO-GO.
- **ROLLBACK IMPLICATION**: none — zero writes, per the dry-run guarantee.

## GO/NO-GO

- **PURPOSE**: one machine-checkable verdict across every category before
  committing.
- **COMMAND**:
  ```bash
  MIGRATION_DRY_RUN_REPORT_PATH=<dry-run-report-path> OAUTH_REDIRECT_URI_VERIFIED=yes \
    LOADY_PG_CONTAINER=<container> LOADY_BACKEND_CONTAINER=<container> \
    PLATFORM_PG_CONTAINER=<container> PLATFORM_BACKEND_CONTAINER=<container> \
    REVERSE_PROXY_CONTAINER=<container> SIGNING_KEY_PATH=<path> TLS_DIR=<dir> \
    scripts/platform/cutover-go-no-go.sh --env production --backup-dir <backup-dir>
  ```
- **EXPECTED RESULT**: `OVERALL: GO`.
- **STOP CONDITION**: `OVERALL: NO-GO` — read every `NO-GO` category's
  reason; do not proceed until every one is resolved (or, for `OAUTH`,
  actually manually verified and re-attested — never set the attestation
  variable without having actually performed the check).
- **ROLLBACK IMPLICATION**: none yet — nothing has been written.

## MIGRATION COMMIT

- **PURPOSE**: the one actual write.
- **COMMAND**:
  ```bash
  python -m app.scripts.loady_migration_dry_run \
    --loady-database-url <production-url> --commit \
    --reason "Production cutover <date>" | tee <commit-report-path>
  ```
- **EXPECTED RESULT**: `created`/`linked`/`skipped`/`conflicted`/`failed`
  counts match the dry run exactly (same shape — commit and dry run are
  proven identical in classification, only commit persists).
- **STOP CONDITION**: any count differs unexpectedly from the dry run —
  investigate before proceeding to reconciliation; this is the sharpest
  possible early-warning signal something changed between dry run and
  commit (e.g. a live write slipped through despite maintenance mode).
- **ROLLBACK IMPLICATION**: **this is the point-of-no-return threshold
  begins** — see `ROLLBACK_TRIGGERS_AND_POINT_OF_NO_RETURN.md`. Rollback
  after this step means restoring from the FINAL BACKUP above, not simply
  reverting a flag.

## RECONCILIATION

- **PURPOSE**: prove the commit produced exactly the expected aggregate
  state — see `RECONCILIATION_PACKAGE.md` for the full invariant list.
- **COMMAND**:
  ```bash
  LOADY_PG_CONTAINER=<container> PLATFORM_PG_CONTAINER=<container> \
    scripts/platform/verify-migration.sh
  ```
- **EXPECTED RESULT**: `RECONCILIATION: PASS`.
- **STOP CONDITION**: `FAIL` on any invariant — this is an explicit
  rollback trigger (`ROLLBACK_TRIGGERS_AND_POINT_OF_NO_RETURN.md`), not a
  warning.
- **ROLLBACK IMPLICATION**: a failure here means rolling back per
  `FINAL_PRODUCTION_ROLLBACK_RUNBOOK.md`.

## SSO TEST

- **PURPOSE**: prove central login actually works end-to-end for a real
  account, per `SSO_VALIDATION_PACKAGE.md`.
- **COMMAND**: manual — log in via `https://loady.cc` → central login →
  Loady callback, using a designated test/staff account.
- **EXPECTED RESULT**: successful login; Loady session reflects the same
  `global_user_id`, history, and plan as before migration.
- **STOP CONDITION**: login fails, or account state looks wrong post-login
  — rollback trigger.
- **ROLLBACK IMPLICATION**: systemic login failure is an explicit,
  objective rollback trigger (`ROLLBACK_TRIGGERS_AND_POINT_OF_NO_RETURN.md`).

## ENTITLEMENT TEST

- **PURPOSE**: prove entitlement resolution is correct post-migration for
  Free/paid/gifted accounts, per `ENTITLEMENT_VALIDATION_PACKAGE.md`.
- **COMMAND**: manual — check plan/credit display for one account of each
  kind available as a safe test account.
- **EXPECTED RESULT**: matches pre-migration state exactly.
- **STOP CONDITION**: any entitlement escalation or paid-user entitlement
  loss — both explicit rollback triggers.
- **ROLLBACK IMPLICATION**: same as above.

## DOWNLOAD TEST

- **PURPOSE**: prove the download gate still authorizes correctly, per
  `DOWNLOAD_VALIDATION_PACKAGE.md`.
- **COMMAND**: manual — one small, low-load test download per test
  account tier.
- **EXPECTED RESULT**: succeeds for entitled tiers, correctly blocked
  where expected.
- **STOP CONDITION**: systemic download authorization failure — rollback
  trigger. **No media-abuse/high-load testing during cutover.**
- **ROLLBACK IMPLICATION**: same as above.

## BILLING TEST

- **PURPOSE**: confirm billing-adjacent surfaces are healthy without
  requiring a real purchase, per `BILLING_VALIDATION_PACKAGE.md`. Real
  Paddle billing cutover is a **separate**, later, explicitly-authorized
  effort (`BILLING_CUTOVER_RUNBOOK.md`) — this step only confirms nothing
  in *this* cutover broke Loady's existing, unaffected Paddle integration.
- **COMMAND**: manual — load the billing/plans page for a test account;
  confirm Loady's existing checkout flow still initializes (without
  completing a real purchase).
- **EXPECTED RESULT**: page loads correctly; checkout initializes.
- **STOP CONDITION**: billing page errors or checkout fails to initialize.
- **ROLLBACK IMPLICATION**: investigate before declaring the window
  complete; not necessarily a full rollback trigger on its own unless
  systemic (Loady's billing is architecturally untouched by this
  cutover).

## ADMIN TEST

- **PURPOSE**: confirm Grand Admin is reachable and functional, per
  `GRAND_ADMIN_VALIDATION_PACKAGE.md`.
- **COMMAND**: manual — log into Grand Admin, look up the test account(s)
  used above, confirm their product membership/entitlement view matches
  what was just tested.
- **EXPECTED RESULT**: matches.
- **STOP CONDITION**: Grand Admin unreachable or shows incorrect state for
  a known test account — rollback trigger if it indicates a systemic
  authorization failure, investigate first if it looks like an isolated
  display issue.
- **ROLLBACK IMPLICATION**: per `ROLLBACK_TRIGGERS_AND_POINT_OF_NO_RETURN.md`.

## MAINTENANCE END

- **PURPOSE**: resume normal service.
- **COMMAND**:
  ```bash
  # set MAINTENANCE_MODE=false, then:
  docker compose -p loady restart backend
  ```
- **EXPECTED RESULT**: normal signup/login/download traffic resumes
  immediately.
- **STOP CONDITION**: none — always safe to perform; if a prior step
  failed, maintenance mode should already have been part of that step's
  own rollback, not left on.
- **ROLLBACK IMPLICATION**: none.
- **NEW THIS MISSION**: if any doubt remains about Cloudflare caching the
  maintenance response, purge cache for `loady.cc/*` now and verify a
  fresh (non-browser-cached) fetch shows the live page — closes the gap
  `CLOUDFLARE_CUTOVER_PLAN.md` identifies.

## 15-MIN / 1-HR / 24-HR OBSERVATION

- **PURPOSE**: catch a delayed-onset problem the immediate post-window
  tests didn't surface.
- **COMMAND**: follow `POST_MIGRATION_MONITORING.md`'s window-by-window
  checklist, using the alert thresholds in `ALERT_THRESHOLDS.md` (Phase
  42).
- **EXPECTED RESULT**: no threshold breach.
- **STOP CONDITION**: any rollback-triggering threshold breach
  (`ROLLBACK_TRIGGERS_AND_POINT_OF_NO_RETURN.md`) — roll back per
  `FINAL_PRODUCTION_ROLLBACK_RUNBOOK.md`. An investigate-only threshold breach
  does not require rollback but must be logged and resolved.
- **ROLLBACK IMPLICATION**: increasingly costly the longer the window
  since MIGRATION COMMIT — see the point-of-no-return document for why.
