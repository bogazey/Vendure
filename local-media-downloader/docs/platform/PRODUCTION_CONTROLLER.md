# Production Controller (Mission 16)

## What this is, and what it is not

`scripts/platform/platform-production.sh` is a single operator entry
point that **orchestrates** the already-proven Mission 5/7/15 scripts
(`backup-before-platform-migration.sh`, `verify-backup-restorable.sh`,
`production-preflight-inspection.sh`, `cutover-go-no-go.sh`,
`verify-migration.sh`, `rollback-platform-migration.sh`, and the
`loady_migration_dry_run.py` tool) into one staged, resumable, state-
tracked sequence. It reimplements none of their checks — every category
of verification those scripts already perform correctly is called into,
not duplicated.

**It has never been run against real production.** Building, testing,
and rehearsing it — entirely with stubbed/synthetic infrastructure — is
this mission's whole scope. The first real invocation against
`185.2.103.46` happens later, by a human operator, one command at a time,
with this documentation and the GO/NO-GO evidence from Mission 15 in
hand.

## Why a controller, given Mission 15 already built a runbook

`FINAL_PRODUCTION_CUTOVER_RUNBOOK.md` is a correct, complete, human-
readable script for a cutover — but it assumes one uninterrupted operator
session and manual bookkeeping of what has and hasn't happened yet. Real
production operations get interrupted: an SSH session drops, a step needs
re-running after a fix, two people need to agree on exactly what state a
half-finished attempt is in. The controller adds:

- **Persisted state** — a deployment's progress survives a terminal
  disconnect; `status` always shows exactly what happened and what's next.
- **Enforced ordering** — a command refuses to run if its prerequisites
  haven't actually completed, rather than relying on an operator reading
  the runbook correctly under pressure.
- **Deliberate confirmation** for the two genuinely destructive commands
  (`migrate`, `rollback`) — never a blank-accepted "y".
- **One place** all the individual scripts' outputs, logs, and results
  are gathered, redacted, and timestamped per attempt.

It does not replace the runbook's own narrative detail (PURPOSE/COMMAND/
EXPECTED RESULT/STOP CONDITION/ROLLBACK IMPLICATION for each step) — an
operator should still read `FINAL_PRODUCTION_CUTOVER_RUNBOOK.md` once
before a real cutover. The controller is the thing they actually type.

## Command reference

| Command | What it does | Requires (current state) |
|---|---|---|
| `inspect` | Mints a new deployment ID (or reuses `--deployment-id`), records git/environment facts. Safe, repeatable. | any |
| `preflight` | Runs the Phase 5 category checks (HOST/CPU/RAM/SWAP/DISK/DOCKER/LOADY/DATABASE/NETWORK/PORTS/TLS/SECRETS/OAUTH/PADDLE/BACKUP CAPACITY/PLATFORM CONFIG/MIGRATION/ROLLBACK), delegating the heavy lifting to `production-preflight-inspection.sh`. | INSPECTED (or later) |
| `plan` | Read-only: shows the remaining stage sequence. No secrets, no side effects. | any |
| `backup` | Runs `backup-before-platform-migration.sh`, records the resulting backup directory. | PREFLIGHT_PASSED |
| `verify-backup` | Runs `verify-backup-restorable.sh` against the recorded backup. | BACKUP_CREATED |
| `platform-deploy` | `docker compose ... up -d --build`. Does **not** touch Loady's identity. | BACKUP_VERIFIED |
| `platform-verify` | Health/ready/JWKS checks only. Reports "IDENTITY NOT MIGRATED" explicitly. | PLATFORM_DEPLOYED |
| `migration-dry-run` | Runs the real dry-run tool against a **snapshot** URL. Zero writes. | PLATFORM_VERIFIED |
| `cutover-check` | Runs `cutover-go-no-go.sh` across every category. | MIGRATION_DRY_RUN_PASSED |
| `maintenance-on` | Verifies (does not itself flip) Loady's maintenance mode. | CUTOVER_GO |
| `migrate` | **The dangerous one.** Requires `--confirm 'MIGRATE <deployment-id>'`. | MAINTENANCE |
| `reconcile` | Runs `verify-migration.sh`. A `FAIL` sets `ROLLBACK_REQUIRED`, never silently passes. | MIGRATED |
| `verify` | Safe smoke tests only (health endpoints). No customer mutation. | RECONCILED |
| `maintenance-off` | Verifies normal traffic resumed. | VERIFIED (or `--force-emergency-override`) |
| `status` | Read-only. `--format json` for machine consumption. | any |
| `rollback-plan` | Read-only preview of what a rollback would do. No changes. | any |
| `rollback` | Requires `--confirm 'ROLLBACK <deployment-id>'`, and if a DB restore is needed, also `--confirm-restore 'RESTORE-DATABASE <deployment-id>'`. | MIGRATED/RECONCILED/VERIFIED/ROLLBACK_REQUIRED/INTERRUPTED |
| `collect-diagnostics` | Safe bundle: state, git facts, container states, resource snapshot, redacted log tail. Never secrets. | any |

There is deliberately **no** `deploy-everything-without-stopping` command.
Every dangerous boundary requires its own explicit invocation.

## `--environment production` vs. `--environment rehearsal`

There is no default — every invocation must say which. `production`
requires every target container/path name as an explicit, pre-set
environment variable (never guessed); `rehearsal` supplies safe,
obviously-fake defaults that are structurally guaranteed to contain the
word "rehearsal", so a copy-pasted real name is rejected outright rather
than silently used. See `PRODUCTION_CONTROLLER_SECURITY.md` for the full
guard rationale and `PRODUCTION_CONTROLLER_REHEARSAL.md` for how rehearsal
mode is actually exercised.

## Where its state lives

`.platform-production-state/<environment>/<deployment-id>/` (gitignored,
overridable via `PLATFORM_CONTROLLER_STATE_DIR`), containing `state.json`,
`log.txt`, `log.jsonl`, the backup directory, and dry-run/commit reports.
See `PRODUCTION_CONTROLLER_STATE_MACHINE.md`.
