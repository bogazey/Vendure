# Production Controller Security Review (Mission 16, Phase 47)

Reviewed `scripts/platform/platform-production.sh` for command injection,
unsafe `eval`, path traversal, symlink attacks, predictable temp files,
permissions, secret leakage, race conditions, and destructive defaults.
Two real issues were found and fixed; everything else checked out.

## Findings and fixes

### 1. Path traversal via `--deployment-id` — found and fixed

`DEPLOYMENT_ID` becomes a path component
(`DEPLOY_DIR="$ENV_ROOT/$DEPLOYMENT_ID"`). Before this fix, a value like
`--deployment-id ../../../etc/something` would have made every subsequent
read/write target a path outside the intended state directory. **Fixed**:
`--deployment-id` is now validated against the exact shape this script
itself ever generates
(`^[0-9]{8}T[0-9]{6}Z-[a-z]+-[0-9a-f]{7,40}$`) at argument-parsing time,
before it is used anywhere. Regression test: `SECTION 12` of
`test-platform-production.sh` — a traversal-shaped value is refused, and
no directory is created outside the state root.

### 2. State directory permissions — hardened

`state_init_if_missing` now `chmod 700`s `STATE_ROOT`, `ENV_ROOT`, and
`DEPLOY_DIR` on every call (idempotent, `|| true` so a permission error
on an already-correctly-owned directory never aborts a read). `state.json`
holds no secrets, but backup paths and infrastructure layout are still
not something to leave group/world-readable on a shared host — this
matches the existing `backup-before-platform-migration.sh` convention
(`chmod 700`/`600` on its own output) rather than inventing a new
standard.

## Checked, no issue found

| Concern | Finding |
|---|---|
| Command injection | Every external command is invoked via an argument array or a fixed literal string with variables passed as separate `"$var"` tokens — never string-concatenated into a shell command line that would need its own escaping. No user-controlled value is ever interpolated into a string later passed to `bash -c`/bin/sh -c`. |
| Unsafe `eval` | Exactly one `eval` call (`eval "exec $LOCK_FD>\"$LOCK_FILE\""`), needed because bash has no other syntax for a *variable* file descriptor number. `$LOCK_FD` is a fixed literal (`200`), never user input. `$LOCK_FILE` is derived from `$ENV_ROOT` (built from the validated `$ENVIRONMENT`, which can only be exactly `production` or `rehearsal`) — never attacker/operator-arbitrary. |
| Symlink attacks on state/backup directories | Every write to `state.json` goes through `mktemp "$DEPLOY_DIR/.state.XXXXXX"` (unpredictable suffix) then `mv -f` — a classic and correct pattern that resists a pre-planted symlink at the *final* path (the temp file is created fresh with a random name, and `mv` replaces the target atomically rather than following a symlink to write through it for an existing file... note: `mv -f` onto an existing symlink target WOULD replace the symlink itself, not follow it and write through, which is the safe direction). Backup/log directories are created with `mkdir -p` under a `chmod 700` parent (see fix #2), which is standard single-operator-host protection, not designed to resist a malicious co-tenant on a shared multi-user box — acceptable given this tool's actual deployment model (a dedicated single-purpose VPS, per `PRODUCTION_ARCHITECTURE_FREEZE.md`). |
| Predictable temp files | Every `mktemp` call in both the controller and its test suite uses a real random-suffix template (`.state.XXXXXX`, or plain `mktemp -d`) — no predictable `/tmp/fixedname` pattern anywhere. |
| Permissions on secrets the controller *reads* (signing key, TLS files) | The controller only ever checks *presence* (`[[ -f ... ]]`) of these files for its preflight category checks — it never reads their contents into a variable, so there is no code path where their contents could leak into logs/state even by accident. |
| Race conditions | The `flock` held for the full duration of any mutating command (acquired before dispatch, released via the `EXIT` trap) means `require_state` and the later `transition()` for the same invocation never race against a second invocation — see `PRODUCTION_CONTROLLER_RECOVERY.md` for the locking model in full. |
| Destructive defaults | No command defaults to a destructive action: `migrate`/`rollback` both require an exact, deliberate, deployment-ID-specific confirmation string with no default/blank-accepted path; `maintenance-off` requires either the normal `VERIFIED` state or an explicit `--force-emergency-override` flag: neither is silent. There is no `--yes`/`--force` flag that skips a confirmation prompt for either dangerous command — the confirmation text itself **is** the only way to proceed. |
| Secret leakage in logs/diagnostics | Covered in depth by the `redact()` filter (applied to every captured line before it reaches `log.txt`/`log.jsonl`/stdout-under-test) and `collect-diagnostics`'s explicit exclusion list. Regression-tested: `SECTION 10` of the test suite injects a real secret-shaped string and a PEM private-key block into a stubbed underlying script's output and confirms neither survives into the persisted log file or the controller's own stdout. |
| Environment-variable injection via `.env.rc`/`.env.production` | The controller never parses or sources these files itself — it only checks their *existence* and hands the *path* to `docker compose --env-file`, which is Compose's own well-tested mechanism, not something this controller reimplements or could be tricked into evaluating unsafely. |

## What this review does not claim

It does not claim to have found every possible issue in a script of this
size — it is a focused pass against the specific threat categories Phase
47 names, on code this mission itself wrote and controls end to end (no
third-party dependency surface to audit). The two real findings above
were fixed and regression-tested before this mission's commit, per the
"fix real issues" instruction — nothing here is a cosmetic-only change.
