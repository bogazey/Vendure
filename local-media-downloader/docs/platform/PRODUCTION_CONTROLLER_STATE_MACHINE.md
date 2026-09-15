# Production Controller State Machine (Mission 16)

## States (exhaustive — `platform-production.sh`'s own `STATES` array)

```
UNKNOWN -> INSPECTED -> PREFLIGHT_PASSED -> BACKUP_CREATED -> BACKUP_VERIFIED
   -> PLATFORM_DEPLOYED -> PLATFORM_VERIFIED -> MIGRATION_DRY_RUN_PASSED
   -> CUTOVER_GO -> MAINTENANCE -> MIGRATED -> RECONCILED -> VERIFIED -> LIVE

(from MIGRATED/RECONCILED/VERIFIED, or on any post-migration failure)
   -> ROLLBACK_REQUIRED -> ROLLED_BACK

(from any dangerous stage, on SIGINT/SIGTERM)
   -> INTERRUPTED
```

Every transition is linear and strictly ordered — there is no skip-ahead
path. A command's `require_state` check names the *exact* states it will
accept; since each state can only be reached by having already passed
every earlier gate, requiring e.g. `MAINTENANCE` for `migrate` is
equivalent to (and implemented as, not merely documented as) requiring
preflight+backup+backup-verified+platform-verified+dry-run+GO+maintenance-
on all to have already happened, in that order, for *this specific
deployment ID*.

## Persistence

One `state.json` per `(environment, deployment_id)` pair, written with
`jq`, always through an atomic temp-file-then-`mv` (`state_set_atomic`) —
a crash mid-write never leaves a half-written, unparseable state file.

```json
{
  "deployment_id": "20260915T181936Z-rehearsal-22e2e1c",
  "environment": "rehearsal",
  "created_at": "...", "updated_at": "...",
  "git_commit": "...", "git_branch": "...",
  "current_state": "MAINTENANCE",
  "last_stable_state": "MAINTENANCE",
  "backup_id": "production-20260915T181937Z",
  "backup_dir": "/path/to/backup/dir",
  "migration_dry_run_report": "/path/to/report.txt",
  "migration_dry_run_counts": "created=5 linked=2 skipped=0 conflicted=0 failed=0",
  "commit_report": null, "commit_counts": null,
  "rollback_required": false, "rollback_reason": null,
  "stages": { "inspect": {"status":"passed","at":"...","detail":"..."}, "...": "..." },
  "history": [ {"from":"UNKNOWN","to":"INSPECTED","at":"..."}, "..." ]
}
```

**Never contains a secret value** — only paths, counts, timestamps, and
status strings. A real deployment's `state.json` is as safe to paste into
a bug report as its own `status` output.

## Deployment ID (Phase 9)

`<UTC-timestamp>-<environment>-<7-char-git-commit>`, minted once by
`inspect` (unless `--deployment-id` names an existing one) and then
resolved automatically by every other command via a `current` pointer
file per environment — never "latest" in the sense of a mutable symlink;
the pointer is a plain file rewritten only by `transition()`, and any
command can pin an explicit `--deployment-id` to operate on an older
attempt instead of whatever is current.

## Impossible transitions are refused, not merely discouraged

`require_state` (called at the top of every mutating command) compares
the deployment's actual `current_state` against the list of states the
command declares acceptable, and calls `die` with a message naming both
the actual and required state if they don't match — this is a hard
`exit 1`, not a warning the operator can click past. `transition()`
itself additionally refuses to ever write a value that isn't in the
`STATES` array (`is_valid_state`), so a typo in the controller's own code
would fail loudly rather than silently corrupt the state file.

## The two branch points

1. **Rollback**: `migrate`, `reconcile`, and `verify` each set
   `rollback_required: true` and transition to `ROLLBACK_REQUIRED` (rather
   than treating the failure as merely "not yet successful") whenever
   their own check fails post-migration — see
   `ROLLBACK_TRIGGERS_AND_POINT_OF_NO_RETURN.md` for why these three
   specific checks are the ones wired this way.
2. **Interruption**: any dangerous stage (`platform-deploy`, `migrate`,
   `rollback` — marked via the `DANGEROUS_STAGE` flag for the duration of
   the actual external call) interrupted by SIGINT/SIGTERM transitions to
   `INTERRUPTED` instead of leaving the previous state looking falsely
   current. See `PRODUCTION_CONTROLLER_RECOVERY.md`.
