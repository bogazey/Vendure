# Production Operator Command Index (Mission 15, Phase 52)

Concise reference only — every command here is fully specified, with its
exact rationale and stop conditions, in the runbook it links to. This
index never duplicates or restates logic that could drift out of sync
with its source of truth.

**Mission 16 update**: every command below now has a corresponding
`scripts/platform/platform-production.sh <command> --environment
production` equivalent that additionally persists state, enforces
ordering, and requires deliberate confirmation for the two dangerous
ones (`migrate`, `rollback`) — see `PRODUCTION_CONTROLLER.md` and
`PRODUCTION_ONE_PAGE_GUIDE.md`. The controller is the **preferred**
interface; the raw commands below remain a fully-supported, documented
fallback (e.g. if the controller's own state directory is unavailable or
its behavior needs independent verification), never removed.

| Controller command | Equivalent raw command(s) below |
|---|---|
| `inspect` | (new — git/environment facts, no raw equivalent) |
| `preflight` | PRECHECK |
| `backup` / `verify-backup` | BACKUP |
| `platform-deploy` | PLATFORM START |
| `platform-verify` | HEALTH |
| `migration-dry-run` | DRY RUN |
| `cutover-check` | GATE |
| `maintenance-on` / `maintenance-off` | MAINTENANCE |
| `migrate` | MIGRATE |
| `reconcile` / `verify` | VERIFY |
| `rollback-plan` / `rollback` | ROLLBACK |
| `collect-diagnostics` | (new — no raw equivalent) |

## PRECHECK

```bash
scripts/platform/production-preflight-inspection.sh --env production
```
→ `PRODUCTION_GO_NO_GO_GATE.md`, `FINAL_PRODUCTION_CUTOVER_RUNBOOK.md` (T-1H)

## BACKUP

```bash
BACKUP_ENCRYPTION_PASSPHRASE=... PLATFORM_MIGRATION_CONFIRM=I_UNDERSTAND_THIS_IS_PRODUCTION \
  scripts/platform/backup-before-platform-migration.sh --env production --out <dir> --retention-days 30
scripts/platform/verify-backup-restorable.sh <run-dir>
```
→ `PRODUCTION_BACKUP_PACKAGE.md`, `FINAL_PRODUCTION_CUTOVER_RUNBOOK.md` (FINAL BACKUP / BACKUP VERIFICATION)

## PLATFORM START

```bash
docker compose -p loady-rc -f compose.rc.yml --env-file .env.rc up -d --build
```
→ `PRODUCTION_COMPOSE_VALIDATION.md`, `PRODUCTION_DEPLOYMENT_SEQUENCING.md`

## HEALTH

```bash
curl -f https://id.<domain>/health
curl -f https://id.<domain>/ready
curl -f https://id.<domain>/.well-known/jwks.json
```
→ `PRODUCTION_DEPLOYMENT_SEQUENCING.md` (PLATFORM CORE VERIFICATION)

## DRY RUN

```bash
python -m app.scripts.loady_migration_dry_run \
  --loady-database-url <restored-snapshot> --reason "..." | tee <report-path>
```
→ `FINAL_MIGRATION_DRY_RUN_PROCEDURE.md`

## GATE

```bash
MIGRATION_DRY_RUN_REPORT_PATH=<path> OAUTH_REDIRECT_URI_VERIFIED=yes \
  scripts/platform/cutover-go-no-go.sh --env production --backup-dir <dir>
```
→ `PRODUCTION_GO_NO_GO_GATE.md`

## MIGRATE

```bash
python -m app.scripts.loady_migration_dry_run \
  --loady-database-url <production-url> --commit --reason "..." | tee <commit-report-path>
```
→ `FINAL_PRODUCTION_CUTOVER_RUNBOOK.md` (MIGRATION COMMIT) — **point of no return begins here**, see `ROLLBACK_TRIGGERS_AND_POINT_OF_NO_RETURN.md`

## VERIFY

```bash
scripts/platform/verify-migration.sh
```
→ `RECONCILIATION_PACKAGE.md`, then the SSO/ENTITLEMENT/DOWNLOAD/BILLING/ADMIN test steps in `FINAL_PRODUCTION_CUTOVER_RUNBOOK.md`

## MAINTENANCE

```bash
# enable: set MAINTENANCE_MODE=true, restart Loady's backend
# disable: set MAINTENANCE_MODE=false, restart Loady's backend
```
→ `MAINTENANCE_WINDOW_PLAN.md`

## ROLLBACK

```bash
# kill switch (fastest, no data change):
scripts/platform/rollback-platform-migration.sh --env production --layer kill-switch
# full restore (after MIGRATION COMMIT, if a trigger fires):
BACKUP_ENCRYPTION_PASSPHRASE=... scripts/platform/rollback-platform-migration.sh \
  --env production --layer full-restore --backup-dir <FINAL-BACKUP-dir> --env-file <loady-env-file>
```
→ `FINAL_PRODUCTION_ROLLBACK_RUNBOOK.md`, `ROLLBACK_TRIGGERS_AND_POINT_OF_NO_RETURN.md`

## MONITOR

```bash
# no new tooling - existing log/HTTP endpoints only, see the doc for exact queries
```
→ `POST_MIGRATION_MONITORING.md`, `ALERT_THRESHOLDS.md`

## Deliberately not indexed here

`scripts/restore-rehearsal.sh` (root) — superseded by
`scripts/platform/verify-backup-restorable.sh`; kept in the repository for
historical reference but never the current authoritative command for
restore verification (`FINAL_PREPRODUCTION_EVIDENCE_AUDIT.md` §8).
