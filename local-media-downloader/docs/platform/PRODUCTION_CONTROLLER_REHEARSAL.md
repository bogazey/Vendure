# Production Controller Rehearsal (Mission 16, Phases 31-36, 40-43)

## Environment constraint, disclosed plainly (Phase 43)

**This environment has no Docker daemon** (`/var/run/docker.sock` does
not exist — re-confirmed this mission, consistent with every environment
Missions 15/16 have run in). Per Phase 43's own instruction: this is not
faked. `platform-deploy` (the one command that genuinely needs Docker)
was tested only against a **stubbed** `docker` binary that simulates
success/failure — never a real container. **Mark: FULL DOCKER REHEARSAL
PENDING.** The protected local personal-use stack a prior mission
identified (`MISSION_7_ARCHITECTURE_AUDIT.md` §5) was never queried,
touched, or assumed reachable — this environment doesn't even have a
Docker daemon to check it against.

## `--environment rehearsal` design (Phase 31)

Rehearsal mode never touches anything real by construction, not by
promise:

- Every container/database name defaults to something containing the
  literal string `rehearsal` (`loady-rehearsal-postgres-1`,
  `platform-rehearsal-backend-1`, etc.) — distinct from both real
  production names and the pre-existing `loady-staging-*` convention
  other Mission 5/15 scripts default to, so a rehearsal run can never be
  mistaken for, or collide with, either.
- Any operator override of these names is **rejected** unless it still
  contains `rehearsal` (the Phase 37 "wrong environment" guard, tested in
  `SECTION 1` of the test suite) — a copy-pasted real name cannot sneak
  through silently.
- Rehearsal's Compose project name (`loady-rehearsal`) and ports
  (`18280`/`18443`) are distinct from every other project this repo's
  tooling knows about (`loady`, `loady-staging`, `loady-rc`).
- TLS/signing-key fixtures live under the controller's own ephemeral,
  gitignored state directory (`$PLATFORM_CONTROLLER_STATE_DIR/rehearsal-fixtures/`),
  never inside the repository itself.

## Synthetic end-to-end rehearsal (Phase 32) — result: PASS

`scripts/platform/test-platform-production.sh` Section 2 drives the
**entire** happy path — `inspect` → `preflight` → `backup` →
`verify-backup` → `platform-deploy` → `platform-verify` →
`migration-dry-run` → `cutover-check` → `maintenance-on` → `migrate`
(with real confirmation-text enforcement) → `reconcile` → `verify` →
`maintenance-off` — against a fully stubbed but structurally faithful
fake repo (real git history, real `compose.rc.yml`/env-example files,
real file-existence checks, stub replacements only for the specific
external calls that would otherwise need Docker/a real database/real
network access). **Result: every stage transitions correctly, final
state is `LIVE`.** Run this mission: **60/60, then 64/64 after the
path-traversal regression was added** (two independent full runs, zero
flakiness).

## Synthetic rollback rehearsal (Phase 33) — result: PASS

Section 5 repeats the same sequence through `migrate`, then deliberately
fails `reconcile` (`FAKE_RECONCILE_MODE=fail`). Confirmed:

1. `reconcile` itself exits non-zero, never silently treated as success.
2. State becomes `ROLLBACK_REQUIRED` (not merely "failed").
3. `rollback-plan` runs read-only and correctly reports the recorded
   backup ID, git commit, and required confirmations — with **zero**
   state changes (verified by re-checking `state.json` unchanged).
4. `rollback` refused without confirmation; refused with only the
   kill-switch confirmation when a DB restore is also needed; succeeds
   only once **both** exact confirmation strings are supplied.
5. Final state is `ROLLED_BACK`.

## Backup failure injection (Phase 34) — result: PASS

Section 6: a stubbed backup failure (`FAKE_BACKUP_MODE=fail`) is refused
(non-zero exit), and — critically — **state remains `PREFLIGHT_PASSED`**,
not advanced to `BACKUP_CREATED`, confirming a failed backup never looks
like a successful one and the operation is safe to simply retry.

## Platform failure injection (Phase 35) — result: PASS

Section 6 also covers: `production-preflight-inspection.sh` NO-GO blocks
`preflight`; a `/ready` response without `signing_key: true` (simulating
a wrong/missing signing key) blocks `platform-verify`; an empty JWKS
`keys` array (simulating a JWKS-serving failure) also blocks
`platform-verify`. None of these produce a false pass.

## Migration failure injection (Phase 36) — result: PASS

Section 6's last case: the stubbed migration tool reports
`conflicted=1` on a dry run — `migration-dry-run` refuses (non-zero
exit), and state never reaches `MIGRATION_DRY_RUN_PASSED`. Separately
(not itself failure-injected in the current suite, but structurally
enforced in the controller): a **commit** whose counts differ from the
already-passed dry run's counts is treated as an anomaly and forces
`ROLLBACK_REQUIRED` rather than `MIGRATED` — this is the concrete
implementation of `ROLLBACK_TRIGGERS_AND_POINT_OF_NO_RETURN.md`'s
"migration conflict outside the expected set" trigger.

## Docker validation (Phase 43)

`docker compose config` (pure client-side YAML parse, no daemon needed)
already validated `compose.rc.yml` in Mission 15 and is unaffected by this
mission (no changes to that file). The controller's own `platform-deploy`
command was exercised only against a stub `docker` binary — **FULL DOCKER
REHEARSAL PENDING** is the honest status for that one command until a
real Docker daemon is available to a future session, or a human operator
runs it directly.

## What "rehearsed" does and does not mean here

Every guard, transition, confirmation, redaction, and failure-path in the
**controller's own logic** has been exercised and passes. What has *not*
been exercised is any of the underlying scripts' real behavior against
real infrastructure — that evidence is Mission 15's (backup encryption,
restore mechanics, real reconciliation SQL, etc.), unchanged and not
re-claimed here. This mission's rehearsal proves the orchestration layer
is correct; it does not re-prove what Mission 15 already proved about the
scripts being orchestrated.
