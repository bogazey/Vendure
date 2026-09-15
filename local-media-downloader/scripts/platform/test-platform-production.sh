#!/usr/bin/env bash
# Mission 16, Phase 41 (+26-39): regression/rehearsal suite for
# platform-production.sh. Builds one throwaway "fake repo" containing
# stub replacements for every external command the controller calls
# (docker, curl, the underlying scripts/platform/*.sh, the Python
# migration tool) so the controller's OWN orchestration logic - state
# transitions, guards, confirmations, locking, redaction, interruption -
# is exercised deterministically, without touching Docker, a real
# database, or any real script's actual behavior (those are each already
# tested/rehearsed on their own, in Mission 15 and this mission's earlier
# phases; this suite is about the controller wrapping them correctly).
#
# Usage: scripts/platform/test-platform-production.sh
set -uo pipefail  # NOT -e: this suite intentionally runs commands that
                  # are expected to fail and inspects their exit codes.

REAL_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTROLLER_SRC="$REAL_SCRIPT_DIR/platform-production.sh"

PASS=0
FAIL=0
FAILED_NAMES=()

pass() { PASS=$((PASS+1)); echo "  OK: $1"; }
fail() { FAIL=$((FAIL+1)); FAILED_NAMES+=("$1"); echo "  FAILED: $1"; }

assert_exit() {
  local expected="$1" actual="$2" label="$3"
  [[ "$actual" == "$expected" ]] && pass "$label (exit $actual)" || fail "$label (expected exit $expected, got $actual)"
}
assert_contains() {
  local haystack="$1" needle="$2" label="$3"
  grep -qF -- "$needle" <<<"$haystack" && pass "$label" || fail "$label (did not find: $needle)"
}
assert_not_contains() {
  local haystack="$1" needle="$2" label="$3"
  grep -qF -- "$needle" <<<"$haystack" && fail "$label (found forbidden: $needle)" || pass "$label"
}

# =======================================================================
# Fake repo construction
# =======================================================================
FAKE_REPO="$(mktemp -d)"
FAKE_BIN="$(mktemp -d)"
STATE_DIR="$(mktemp -d)"
trap 'rm -rf "$FAKE_REPO" "$FAKE_BIN" "$STATE_DIR"' EXIT

mkdir -p "$FAKE_REPO/scripts/platform"
cp "$CONTROLLER_SRC" "$FAKE_REPO/scripts/platform/platform-production.sh"
chmod +x "$FAKE_REPO/scripts/platform/platform-production.sh"
CONTROLLER="$FAKE_REPO/scripts/platform/platform-production.sh"

# --- a real (tiny) git repo, so git guards have something real to check
(
  cd "$FAKE_REPO"
  git init -q
  git config user.email "test@example.com"
  git config user.name "Test"
  echo "fake" > README.md
  git add README.md
  git commit -q -m "initial"
)
FAKE_COMMIT="$(cd "$FAKE_REPO" && git rev-parse HEAD)"

# --- structural files the controller's own preflight checks for
mkdir -p "$FAKE_REPO/platform-core"
echo "fake compose" > "$FAKE_REPO/compose.rc.yml"
echo "fake" > "$FAKE_REPO/.env.rc.example"
echo "fake" > "$FAKE_REPO/platform-core/.env.production.example"
echo "fake" > "$FAKE_REPO/.env.rc"
# Rehearsal TLS/signing-key fixtures: the controller's own rehearsal
# defaults point at $PLATFORM_CONTROLLER_STATE_DIR/rehearsal-fixtures/*
# (ephemeral, alongside operator state) rather than inside the repo -
# laid down fresh by reset_state() below, since reset_state wipes the
# state dir between test sections.
lay_down_rehearsal_fixtures() {
  mkdir -p "$STATE_DIR/rehearsal-fixtures/tls"
  echo "fake cert" > "$STATE_DIR/rehearsal-fixtures/tls/fullchain.pem"
  echo "fake key" > "$STATE_DIR/rehearsal-fixtures/tls/privkey.pem"
  echo "fake signing key" > "$STATE_DIR/rehearsal-fixtures/signing-key.pem"
}
mkdir -p "$FAKE_REPO/platform-core/backend/app/scripts"
echo "fake" > "$FAKE_REPO/platform-core/backend/app/scripts/loady_migration_dry_run.py"
mkdir -p "$FAKE_REPO/platform-core/backend/.venv/bin"

# --- fake python (the migration dry-run/commit tool)
cat > "$FAKE_REPO/platform-core/backend/.venv/bin/python" <<'PYEOF'
#!/usr/bin/env bash
# Fake loady_migration_dry_run.py: prints a canned report. Controlled by
# FAKE_MIGRATION_MODE: ok (default) | conflict | commit-mismatch | error
COMMIT="0"
for a in "$@"; do [[ "$a" == "--commit" ]] && COMMIT="1"; done
case "${FAKE_MIGRATION_MODE:-ok}" in
  error) echo "boom: something went wrong" >&2; exit 1 ;;
  conflict)
    if [[ "$COMMIT" == "0" ]]; then
      echo "=== DRY RUN (nothing was written - pass --commit to persist) ==="
      echo "created=5 linked=2 skipped=0 conflicted=1 failed=0"
    else
      echo "=== COMMITTED ==="
      echo "created=5 linked=2 skipped=0 conflicted=1 failed=0"
    fi
    ;;
  commit-mismatch)
    if [[ "$COMMIT" == "0" ]]; then
      echo "=== DRY RUN (nothing was written - pass --commit to persist) ==="
      echo "created=5 linked=2 skipped=0 conflicted=0 failed=0"
    else
      echo "=== COMMITTED ==="
      echo "created=6 linked=2 skipped=0 conflicted=0 failed=0"
    fi
    ;;
  *)
    if [[ "$COMMIT" == "0" ]]; then
      echo "=== DRY RUN (nothing was written - pass --commit to persist) ==="
      echo "created=5 linked=2 skipped=0 conflicted=0 failed=0"
    else
      echo "=== COMMITTED ==="
      echo "created=5 linked=2 skipped=0 conflicted=0 failed=0"
    fi
    ;;
esac
exit 0
PYEOF
chmod +x "$FAKE_REPO/platform-core/backend/.venv/bin/python"

# --- fake underlying operator scripts
write_fake_script() {
  local path="$1" body="$2"
  cat > "$path" <<EOF
#!/usr/bin/env bash
$body
EOF
  chmod +x "$path"
}

write_fake_script "$FAKE_REPO/scripts/platform/production-preflight-inspection.sh" '
if [[ "${FAKE_PREFLIGHT_MODE:-go}" == "go" ]]; then echo "GO"; exit 0; else echo "NO-GO:"; echo "  - fake reason"; exit 1; fi
'
write_fake_script "$FAKE_REPO/scripts/platform/backup-before-platform-migration.sh" '
OUT=""
while [[ $# -gt 0 ]]; do case "$1" in --out) OUT="$2"; shift 2;; *) shift;; esac; done
if [[ "${FAKE_BACKUP_MODE:-ok}" == "fail" ]]; then echo "NO-GO: fake backup failure" >&2; exit 1; fi
RUN_DIR="$OUT/production-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$RUN_DIR"
echo "fake" > "$RUN_DIR/CHECKSUMS.sha256"
echo "Backup complete: $RUN_DIR"
exit 0
'
write_fake_script "$FAKE_REPO/scripts/platform/verify-backup-restorable.sh" '
if [[ "${FAKE_VERIFY_BACKUP_MODE:-ok}" == "fail" ]]; then echo "checksum mismatch" >&2; exit 1; fi
echo "restore verified"
exit 0
'
write_fake_script "$FAKE_REPO/scripts/platform/cutover-go-no-go.sh" '
if [[ "${FAKE_CUTOVER_MODE:-go}" == "go" ]]; then echo "OVERALL: GO"; exit 0; else echo "OVERALL: NO-GO"; exit 1; fi
'
write_fake_script "$FAKE_REPO/scripts/platform/verify-migration.sh" '
if [[ "${FAKE_RECONCILE_MODE:-pass}" == "pass" ]]; then echo "RECONCILIATION: PASS"; exit 0; else echo "RECONCILIATION: FAIL"; exit 1; fi
'
write_fake_script "$FAKE_REPO/scripts/platform/rollback-platform-migration.sh" '
if [[ "${FAKE_ROLLBACK_MODE:-ok}" == "fail" ]]; then echo "fake rollback failure" >&2; exit 1; fi
echo "rollback layer complete"
exit 0
'

# --- fake docker
cat > "$FAKE_BIN/docker" <<'EOF'
#!/usr/bin/env bash
case "$1" in
  version) [[ "${FAKE_DOCKER_UP:-1}" == "1" ]] && exit 0 || exit 1 ;;
  compose)
    if [[ "${FAKE_PLATFORM_DEPLOY_MODE:-ok}" == "fail" ]]; then echo "compose up failed" >&2; exit 1; fi
    echo "containers started"; exit 0 ;;
  *) exit 0 ;;
esac
EOF
chmod +x "$FAKE_BIN/docker"

# --- fake curl (health/ready/jwks)
cat > "$FAKE_BIN/curl" <<'EOF'
#!/usr/bin/env bash
HAS_W="0"
URL=""
for a in "$@"; do
  [[ "$a" == "-w" || "$a" == '%{http_code}' ]] && HAS_W="1"
  [[ "$a" == http* ]] && URL="$a"
done
if [[ "$HAS_W" == "1" ]]; then
  echo -n "${FAKE_HTTP_STATUS:-200}"
  exit 0
fi
case "$URL" in
  */ready) [[ "${FAKE_READY_BAD:-0}" == "1" ]] && echo '{"signing_key":false}' || echo '{"signing_key":true}' ;;
  */jwks.json) [[ "${FAKE_JWKS_BAD:-0}" == "1" ]] && echo '{"keys":[]}' || echo '{"keys":[{"kid":"test"}]}' ;;
  *) echo '{}' ;;
esac
exit 0
EOF
chmod +x "$FAKE_BIN/curl"

# =======================================================================
# Common env for every invocation
# =======================================================================
run_controller() {
  # Runs the controller with a clean, minimal, rehearsal-safe env.
  PATH="$FAKE_BIN:$PATH" \
  PLATFORM_CONTROLLER_STATE_DIR="$STATE_DIR" \
  PLATFORM_AUTH_BASE_URL="https://localhost:18443" \
  LOADY_HEALTH_URL="https://localhost:18280/api/health" \
  LOADY_SNAPSHOT_DATABASE_URL="sqlite:////tmp/fake-snapshot.db" \
  LOADY_PRODUCTION_DATABASE_URL="sqlite:////tmp/fake-prod.db" \
  LOADY_ENV_FILE="$FAKE_REPO/.env.rc" \
  "$@" \
  bash "$CONTROLLER" "${CMD_ARGS[@]}"
}

reset_state() { rm -rf "$STATE_DIR"; mkdir -p "$STATE_DIR"; lay_down_rehearsal_fixtures; }

get_current_deployment_id() {
  # Bash does not support `ARR=(...) some_function` as a real prefix
  # assignment the way it does for scalar VAR=value - it silently fails
  # to update the array inside the function. Always use the safe
  # two-statement form instead.
  CMD_ARGS=(status --environment rehearsal)
  run_controller 2>&1 | grep '^Deployment ID:' | awk '{print $3}'
}

echo "=============================================================="
echo "SECTION 1: environment guard (Phase 3 / 37)"
echo "=============================================================="
reset_state
CMD_ARGS=(status)
OUT="$(run_controller 2>&1)"; RC=$?
assert_exit 1 "$RC" "no --environment given -> refused"
assert_contains "$OUT" "environment is required" "clear refusal message"

CMD_ARGS=(status --environment bogus)
OUT="$(run_controller 2>&1)"; RC=$?
assert_exit 1 "$RC" "invalid --environment value -> refused"

CMD_ARGS=(inspect --environment production)
OUT="$(run_controller 2>&1)"; RC=$?
assert_exit 1 "$RC" "production without required env vars -> refused"
assert_contains "$OUT" "requires \$LOADY_PG_CONTAINER" "names the missing var"

CMD_ARGS=(inspect --environment rehearsal)
OUT="$(LOADY_PG_CONTAINER=loady-prod-postgres-1 run_controller 2>&1)"; RC=$?
assert_exit 1 "$RC" "rehearsal with a non-rehearsal-named override -> refused"

echo
echo "=============================================================="
echo "SECTION 2: happy path (Phase 32) - full sequence through to LIVE"
echo "=============================================================="
reset_state
export FAKE_PREFLIGHT_MODE=go FAKE_BACKUP_MODE=ok FAKE_VERIFY_BACKUP_MODE=ok
export FAKE_CUTOVER_MODE=go FAKE_RECONCILE_MODE=pass FAKE_MIGRATION_MODE=ok
export FAKE_PLATFORM_DEPLOY_MODE=ok FAKE_HTTP_STATUS=200 FAKE_READY_BAD=0 FAKE_JWKS_BAD=0
export BACKUP_ENCRYPTION_PASSPHRASE=not-a-real-secret-test-only

CMD_ARGS=(inspect --environment rehearsal); OUT="$(run_controller 2>&1)"; RC=$?
assert_exit 0 "$RC" "inspect succeeds"
DEPLOY_ID="$(grep '^Deployment ID:' <<<"$OUT" | awk '{print $3}')"
[[ -n "$DEPLOY_ID" ]] && pass "deployment id minted ($DEPLOY_ID)" || fail "deployment id minted"

CMD_ARGS=(preflight --environment rehearsal); OUT="$(run_controller 2>&1)"; RC=$?
assert_exit 0 "$RC" "preflight GO"

CMD_ARGS=(backup --environment rehearsal); OUT="$(run_controller 2>&1)"; RC=$?
assert_exit 0 "$RC" "backup succeeds"

CMD_ARGS=(verify-backup --environment rehearsal); OUT="$(run_controller 2>&1)"; RC=$?
assert_exit 0 "$RC" "verify-backup succeeds"

CMD_ARGS=(platform-deploy --environment rehearsal); OUT="$(run_controller 2>&1)"; RC=$?
assert_exit 0 "$RC" "platform-deploy succeeds"
assert_contains "$OUT" "IDENTITY NOT MIGRATED" "platform-deploy reports identity not migrated"

CMD_ARGS=(platform-verify --environment rehearsal); OUT="$(run_controller 2>&1)"; RC=$?
assert_exit 0 "$RC" "platform-verify succeeds"

CMD_ARGS=(migration-dry-run --environment rehearsal); OUT="$(run_controller 2>&1)"; RC=$?
assert_exit 0 "$RC" "migration-dry-run succeeds with zero conflicts"

CMD_ARGS=(cutover-check --environment rehearsal); OUT="$(run_controller 2>&1)"; RC=$?
assert_exit 0 "$RC" "cutover-check GO"

CMD_ARGS=(maintenance-on --environment rehearsal); OUT="$(run_controller 2>&1)"; RC=$?
assert_exit 0 "$RC" "maintenance-on succeeds"

CMD_ARGS=(migrate --environment rehearsal --confirm "MIGRATE $DEPLOY_ID"); OUT="$(run_controller 2>&1)"; RC=$?
assert_exit 0 "$RC" "migrate succeeds with correct confirmation"

CMD_ARGS=(reconcile --environment rehearsal); OUT="$(run_controller 2>&1)"; RC=$?
assert_exit 0 "$RC" "reconcile PASS"

CMD_ARGS=(verify --environment rehearsal); OUT="$(run_controller 2>&1)"; RC=$?
assert_exit 0 "$RC" "verify succeeds"

CMD_ARGS=(maintenance-off --environment rehearsal); OUT="$(run_controller 2>&1)"; RC=$?
assert_exit 0 "$RC" "maintenance-off succeeds"

CMD_ARGS=(status --environment rehearsal --format json); OUT="$(run_controller 2>&1)"; RC=$?
assert_exit 0 "$RC" "status --format json succeeds"
echo "$OUT" | jq -e '.current_state == "LIVE"' >/dev/null 2>&1 && pass "final state is LIVE" || fail "final state is LIVE (got: $(echo "$OUT" | jq -r .current_state 2>/dev/null))"

unset FAKE_PREFLIGHT_MODE FAKE_BACKUP_MODE FAKE_VERIFY_BACKUP_MODE FAKE_CUTOVER_MODE FAKE_RECONCILE_MODE FAKE_MIGRATION_MODE FAKE_PLATFORM_DEPLOY_MODE

echo
echo "=============================================================="
echo "SECTION 3: state machine refuses out-of-order commands"
echo "=============================================================="
reset_state
CMD_ARGS=(inspect --environment rehearsal); run_controller >/dev/null 2>&1
DEPLOY_ID="$(get_current_deployment_id)"

CMD_ARGS=(backup --environment rehearsal); OUT="$(BACKUP_ENCRYPTION_PASSPHRASE=x run_controller 2>&1)"; RC=$?
assert_exit 1 "$RC" "backup refused before preflight"
assert_contains "$OUT" "requires one of" "refusal names required states"

CMD_ARGS=(migrate --environment rehearsal --confirm "MIGRATE $DEPLOY_ID"); OUT="$(run_controller 2>&1)"; RC=$?
assert_exit 1 "$RC" "migrate refused with nothing else done"

CMD_ARGS=(maintenance-off --environment rehearsal); OUT="$(run_controller 2>&1)"; RC=$?
assert_exit 1 "$RC" "maintenance-off refused without --force-emergency-override from UNKNOWN/INSPECTED"

echo
echo "=============================================================="
echo "SECTION 4: confirmation guards (Phase 16 / 21)"
echo "=============================================================="
reset_state
export FAKE_PREFLIGHT_MODE=go FAKE_BACKUP_MODE=ok FAKE_VERIFY_BACKUP_MODE=ok
export FAKE_CUTOVER_MODE=go FAKE_MIGRATION_MODE=ok FAKE_PLATFORM_DEPLOY_MODE=ok
export BACKUP_ENCRYPTION_PASSPHRASE=not-a-real-secret-test-only
CMD_ARGS=(inspect --environment rehearsal); run_controller >/dev/null 2>&1
DEPLOY_ID="$(get_current_deployment_id)"
CMD_ARGS=(preflight --environment rehearsal); run_controller >/dev/null 2>&1
CMD_ARGS=(backup --environment rehearsal); run_controller >/dev/null 2>&1
CMD_ARGS=(verify-backup --environment rehearsal); run_controller >/dev/null 2>&1
CMD_ARGS=(platform-deploy --environment rehearsal); run_controller >/dev/null 2>&1
CMD_ARGS=(platform-verify --environment rehearsal); run_controller >/dev/null 2>&1
CMD_ARGS=(migration-dry-run --environment rehearsal); run_controller >/dev/null 2>&1
CMD_ARGS=(cutover-check --environment rehearsal); run_controller >/dev/null 2>&1
CMD_ARGS=(maintenance-on --environment rehearsal); run_controller >/dev/null 2>&1

CMD_ARGS=(migrate --environment rehearsal); OUT="$(run_controller 2>&1)"; RC=$?
assert_exit 1 "$RC" "migrate refused with NO confirmation at all"
assert_not_contains "$OUT" "Migration committed" "no migration happened without confirmation"

CMD_ARGS=(migrate --environment rehearsal --confirm "y"); OUT="$(run_controller 2>&1)"; RC=$?
assert_exit 1 "$RC" "migrate refused with a blank/lazy 'y' confirmation"

CMD_ARGS=(migrate --environment rehearsal --confirm "MIGRATE wrong-id"); OUT="$(run_controller 2>&1)"; RC=$?
assert_exit 1 "$RC" "migrate refused with wrong deployment id in confirmation"

CMD_ARGS=(migrate --environment rehearsal --confirm "MIGRATE $DEPLOY_ID"); OUT="$(run_controller 2>&1)"; RC=$?
assert_exit 0 "$RC" "migrate succeeds with the exact correct confirmation"

# duplicate migrate must refuse (Phase 27 idempotent-safety-for-dangerous-ops)
CMD_ARGS=(migrate --environment rehearsal --confirm "MIGRATE $DEPLOY_ID"); OUT="$(run_controller 2>&1)"; RC=$?
assert_exit 1 "$RC" "second migrate call on the same deployment refuses (state no longer MAINTENANCE)"

unset FAKE_PREFLIGHT_MODE FAKE_BACKUP_MODE FAKE_VERIFY_BACKUP_MODE FAKE_CUTOVER_MODE FAKE_MIGRATION_MODE FAKE_PLATFORM_DEPLOY_MODE

echo
echo "=============================================================="
echo "SECTION 5: rollback rehearsal (Phase 33) - fail after migrate"
echo "=============================================================="
reset_state
export FAKE_PREFLIGHT_MODE=go FAKE_BACKUP_MODE=ok FAKE_VERIFY_BACKUP_MODE=ok
export FAKE_CUTOVER_MODE=go FAKE_MIGRATION_MODE=ok FAKE_PLATFORM_DEPLOY_MODE=ok
export BACKUP_ENCRYPTION_PASSPHRASE=not-a-real-secret-test-only
CMD_ARGS=(inspect --environment rehearsal); run_controller >/dev/null 2>&1
DEPLOY_ID="$(get_current_deployment_id)"
CMD_ARGS=(preflight --environment rehearsal); run_controller >/dev/null 2>&1
CMD_ARGS=(backup --environment rehearsal); run_controller >/dev/null 2>&1
CMD_ARGS=(verify-backup --environment rehearsal); run_controller >/dev/null 2>&1
CMD_ARGS=(platform-deploy --environment rehearsal); run_controller >/dev/null 2>&1
CMD_ARGS=(platform-verify --environment rehearsal); run_controller >/dev/null 2>&1
CMD_ARGS=(migration-dry-run --environment rehearsal); run_controller >/dev/null 2>&1
CMD_ARGS=(cutover-check --environment rehearsal); run_controller >/dev/null 2>&1
CMD_ARGS=(maintenance-on --environment rehearsal); run_controller >/dev/null 2>&1
CMD_ARGS=(migrate --environment rehearsal --confirm "MIGRATE $DEPLOY_ID"); run_controller >/dev/null 2>&1

export FAKE_RECONCILE_MODE=fail
CMD_ARGS=(reconcile --environment rehearsal); OUT="$(run_controller 2>&1)"; RC=$?
assert_exit 1 "$RC" "reconcile FAIL is treated as a failure, not silently OK"
CMD_ARGS=(status --environment rehearsal --format json); OUT="$(run_controller 2>&1)"
echo "$OUT" | jq -e '.current_state == "ROLLBACK_REQUIRED"' >/dev/null 2>&1 \
  && pass "state correctly became ROLLBACK_REQUIRED" \
  || fail "state correctly became ROLLBACK_REQUIRED (got: $(echo "$OUT" | jq -r .current_state 2>/dev/null))"

CMD_ARGS=(rollback-plan --environment rehearsal); OUT="$(run_controller 2>&1)"; RC=$?
assert_exit 0 "$RC" "rollback-plan is read-only and always succeeds"
assert_contains "$OUT" "NO CHANGES MADE" "rollback-plan explicitly states no changes"

CMD_ARGS=(rollback --environment rehearsal); OUT="$(run_controller 2>&1)"; RC=$?
assert_exit 1 "$RC" "rollback refused with no confirmation"

CMD_ARGS=(rollback --environment rehearsal --confirm "ROLLBACK $DEPLOY_ID"); OUT="$(run_controller 2>&1)"; RC=$?
assert_exit 1 "$RC" "rollback refused: kill-switch confirmed but DB-restore confirmation still missing"

CMD_ARGS=(rollback --environment rehearsal --confirm "ROLLBACK $DEPLOY_ID" --confirm-restore "RESTORE-DATABASE $DEPLOY_ID")
OUT="$(BACKUP_ENCRYPTION_PASSPHRASE=not-a-real-secret-test-only run_controller 2>&1)"; RC=$?
assert_exit 0 "$RC" "rollback with BOTH confirmations succeeds"

CMD_ARGS=(status --environment rehearsal --format json); OUT="$(run_controller 2>&1)"
echo "$OUT" | jq -e '.current_state == "ROLLED_BACK"' >/dev/null 2>&1 \
  && pass "final state is ROLLED_BACK - proves the rollback path completes" \
  || fail "final state is ROLLED_BACK"

unset FAKE_PREFLIGHT_MODE FAKE_BACKUP_MODE FAKE_VERIFY_BACKUP_MODE FAKE_CUTOVER_MODE FAKE_MIGRATION_MODE FAKE_PLATFORM_DEPLOY_MODE FAKE_RECONCILE_MODE

echo
echo "=============================================================="
echo "SECTION 6: failure injection (Phases 34-36)"
echo "=============================================================="

reset_state
export FAKE_PREFLIGHT_MODE=go BACKUP_ENCRYPTION_PASSPHRASE=not-a-real-secret-test-only
CMD_ARGS=(inspect --environment rehearsal); run_controller >/dev/null 2>&1
CMD_ARGS=(preflight --environment rehearsal); run_controller >/dev/null 2>&1
export FAKE_BACKUP_MODE=fail
CMD_ARGS=(backup --environment rehearsal); OUT="$(run_controller 2>&1)"; RC=$?
assert_exit 1 "$RC" "backup failure blocks progression"
CMD_ARGS=(status --environment rehearsal --format json); OUT="$(run_controller 2>&1)"
echo "$OUT" | jq -e '.current_state == "PREFLIGHT_PASSED"' >/dev/null 2>&1 \
  && pass "state unchanged after failed backup (safe to retry)" \
  || fail "state unchanged after failed backup"
unset FAKE_BACKUP_MODE

reset_state
export FAKE_PREFLIGHT_MODE=nogo
CMD_ARGS=(inspect --environment rehearsal); run_controller >/dev/null 2>&1
CMD_ARGS=(preflight --environment rehearsal); OUT="$(run_controller 2>&1)"; RC=$?
assert_exit 1 "$RC" "preflight NO-GO blocks progression"
unset FAKE_PREFLIGHT_MODE

reset_state
export FAKE_PREFLIGHT_MODE=go FAKE_BACKUP_MODE=ok FAKE_VERIFY_BACKUP_MODE=ok FAKE_PLATFORM_DEPLOY_MODE=ok
CMD_ARGS=(inspect --environment rehearsal); run_controller >/dev/null 2>&1
CMD_ARGS=(preflight --environment rehearsal); run_controller >/dev/null 2>&1
CMD_ARGS=(backup --environment rehearsal); run_controller >/dev/null 2>&1
CMD_ARGS=(verify-backup --environment rehearsal); run_controller >/dev/null 2>&1
CMD_ARGS=(platform-deploy --environment rehearsal); run_controller >/dev/null 2>&1
export FAKE_READY_BAD=1
CMD_ARGS=(platform-verify --environment rehearsal); OUT="$(run_controller 2>&1)"; RC=$?
assert_exit 1 "$RC" "platform-verify fails when signing_key is not true (wrong/missing signing key simulated)"
unset FAKE_READY_BAD

export FAKE_JWKS_BAD=1
CMD_ARGS=(platform-verify --environment rehearsal); OUT="$(run_controller 2>&1)"; RC=$?
assert_exit 1 "$RC" "platform-verify fails when JWKS has no keys"
unset FAKE_JWKS_BAD FAKE_PREFLIGHT_MODE FAKE_BACKUP_MODE FAKE_VERIFY_BACKUP_MODE FAKE_PLATFORM_DEPLOY_MODE

reset_state
export FAKE_PREFLIGHT_MODE=go FAKE_BACKUP_MODE=ok FAKE_VERIFY_BACKUP_MODE=ok FAKE_PLATFORM_DEPLOY_MODE=ok FAKE_MIGRATION_MODE=conflict
CMD_ARGS=(inspect --environment rehearsal); run_controller >/dev/null 2>&1
CMD_ARGS=(preflight --environment rehearsal); run_controller >/dev/null 2>&1
CMD_ARGS=(backup --environment rehearsal); run_controller >/dev/null 2>&1
CMD_ARGS=(verify-backup --environment rehearsal); run_controller >/dev/null 2>&1
CMD_ARGS=(platform-deploy --environment rehearsal); run_controller >/dev/null 2>&1
CMD_ARGS=(platform-verify --environment rehearsal); run_controller >/dev/null 2>&1
CMD_ARGS=(migration-dry-run --environment rehearsal); OUT="$(run_controller 2>&1)"; RC=$?
assert_exit 1 "$RC" "unexpected dry-run conflict is NO-GO, never a false GO"
unset FAKE_PREFLIGHT_MODE FAKE_BACKUP_MODE FAKE_VERIFY_BACKUP_MODE FAKE_PLATFORM_DEPLOY_MODE FAKE_MIGRATION_MODE

echo
echo "=============================================================="
echo "SECTION 7: wrong-commit test (Phase 38)"
echo "=============================================================="
reset_state
CMD_ARGS=(inspect --environment rehearsal)
OUT="$(EXPECTED_GIT_COMMIT=deadbeefdeadbeefdeadbeefdeadbeefdeadbeef run_controller 2>&1)"; RC=$?
assert_exit 1 "$RC" "commit mismatch refused"
assert_contains "$OUT" "Git commit mismatch" "clear commit-mismatch message"

OUT="$(EXPECTED_GIT_COMMIT="$FAKE_COMMIT" run_controller 2>&1)"; RC=$?
assert_exit 0 "$RC" "matching EXPECTED_GIT_COMMIT succeeds"

echo
echo "=============================================================="
echo "SECTION 8: locking (Phase 28)"
echo "=============================================================="
reset_state
CMD_ARGS=(inspect --environment rehearsal); run_controller >/dev/null 2>&1
(
  # Hold the lock manually via flock, exactly like the controller does,
  # then confirm a second invocation is refused while it's held.
  exec 9>"$STATE_DIR/rehearsal/.controller.lock"
  flock 9
  CMD_ARGS=(preflight --environment rehearsal)
  OUT="$(FAKE_PREFLIGHT_MODE=go run_controller 2>&1)"; RC=$?
  assert_exit 1 "$RC" "second mutating command refused while lock is held"
  assert_contains "$OUT" "already running" "lock refusal message is clear"
)
# lock released now - the same command should work
CMD_ARGS=(status --environment rehearsal); OUT="$(run_controller 2>&1)"; RC=$?
assert_exit 0 "$RC" "read-only 'status' never blocked by the lock"

echo
echo "=============================================================="
echo "SECTION 9: interruption handling (Phase 29 / 26)"
echo "=============================================================="
reset_state
export FAKE_PREFLIGHT_MODE=go FAKE_BACKUP_MODE=ok FAKE_VERIFY_BACKUP_MODE=ok
export FAKE_CUTOVER_MODE=go FAKE_MIGRATION_MODE=ok FAKE_PLATFORM_DEPLOY_MODE=ok
export BACKUP_ENCRYPTION_PASSPHRASE=not-a-real-secret-test-only
CMD_ARGS=(inspect --environment rehearsal); run_controller >/dev/null 2>&1
DEPLOY_ID="$(get_current_deployment_id)"
CMD_ARGS=(preflight --environment rehearsal); run_controller >/dev/null 2>&1
CMD_ARGS=(backup --environment rehearsal); run_controller >/dev/null 2>&1
CMD_ARGS=(verify-backup --environment rehearsal); run_controller >/dev/null 2>&1
CMD_ARGS=(platform-deploy --environment rehearsal); run_controller >/dev/null 2>&1
CMD_ARGS=(platform-verify --environment rehearsal); run_controller >/dev/null 2>&1
CMD_ARGS=(migration-dry-run --environment rehearsal); run_controller >/dev/null 2>&1
CMD_ARGS=(cutover-check --environment rehearsal); run_controller >/dev/null 2>&1
CMD_ARGS=(maintenance-on --environment rehearsal); run_controller >/dev/null 2>&1

# Make the migration tool hang, so we can SIGTERM the controller mid-migrate.
cat > "$FAKE_REPO/platform-core/backend/.venv/bin/python" <<'PYEOF'
#!/usr/bin/env bash
echo "=== DRY RUN (nothing was written - pass --commit to persist) ==="
sleep 30
PYEOF
chmod +x "$FAKE_REPO/platform-core/backend/.venv/bin/python"

PATH="$FAKE_BIN:$PATH" PLATFORM_CONTROLLER_STATE_DIR="$STATE_DIR" \
  LOADY_PRODUCTION_DATABASE_URL="sqlite:////tmp/fake-prod.db" \
  bash "$CONTROLLER" migrate --environment rehearsal --confirm "MIGRATE $DEPLOY_ID" &
CTRL_PID=$!
sleep 1
kill -TERM "$CTRL_PID" 2>/dev/null
wait "$CTRL_PID" 2>/dev/null
RC=$?
[[ "$RC" != "0" ]] && pass "interrupted migrate does not exit 0" || fail "interrupted migrate does not exit 0"

CMD_ARGS=(status --environment rehearsal --format json); OUT="$(run_controller 2>&1)"
echo "$OUT" | jq -e '.current_state == "INTERRUPTED"' >/dev/null 2>&1 \
  && pass "interrupted dangerous stage recorded as INTERRUPTED, not silently MAINTENANCE or MIGRATED" \
  || fail "interrupted dangerous stage recorded as INTERRUPTED (got: $(echo "$OUT" | jq -r .current_state 2>/dev/null))"

unset FAKE_PREFLIGHT_MODE FAKE_BACKUP_MODE FAKE_VERIFY_BACKUP_MODE FAKE_CUTOVER_MODE FAKE_MIGRATION_MODE FAKE_PLATFORM_DEPLOY_MODE

echo
echo "=============================================================="
echo "SECTION 10: secret redaction (Phase 39 / 28)"
echo "=============================================================="
reset_state
write_fake_script "$FAKE_REPO/scripts/platform/production-preflight-inspection.sh" '
echo "PADDLE_WEBHOOK_SECRET=sk_live_totally_fake_1234567890abcdef_not_real_but_secret_shaped"
echo "SIGNING_KEY_PATH check: -----BEGIN RSA PRIVATE KEY----- FAKEFAKEFAKE -----END RSA PRIVATE KEY-----"
echo "GO"
exit 0
'
CMD_ARGS=(inspect --environment rehearsal); run_controller >/dev/null 2>&1
CMD_ARGS=(preflight --environment rehearsal); OUT="$(run_controller 2>&1)"
assert_not_contains "$OUT" "sk_live_totally_fake_1234567890abcdef_not_real_but_secret_shaped" "long secret-shaped token redacted from controller stdout capture"
LOG_CONTENT="$(cat "$STATE_DIR"/rehearsal/*/log.txt 2>/dev/null || echo "")"
assert_not_contains "$LOG_CONTENT" "BEGIN RSA PRIVATE KEY-----" "private key block redacted from persisted log file"
assert_not_contains "$LOG_CONTENT" "sk_live_totally_fake" "secret-shaped token redacted from persisted log file"

echo
echo "=============================================================="
echo "SECTION 11: idempotent-safe commands (Phase 27)"
echo "=============================================================="
reset_state
CMD_ARGS=(inspect --environment rehearsal); run_controller >/dev/null 2>&1
CMD_ARGS=(status --environment rehearsal); OUT1="$(run_controller 2>&1)"; RC1=$?
CMD_ARGS=(status --environment rehearsal); OUT2="$(run_controller 2>&1)"; RC2=$?
assert_exit 0 "$RC1" "status call 1 succeeds"
assert_exit 0 "$RC2" "status call 2 succeeds (repeatable)"
CMD_ARGS=(collect-diagnostics --environment rehearsal); OUT="$(run_controller 2>&1)"; RC=$?
assert_exit 0 "$RC" "collect-diagnostics succeeds"
assert_not_contains "$OUT" "BEGIN RSA PRIVATE KEY" "diagnostics bundle path never surfaces key material"

echo
echo "=============================================================="
echo "SECTION 12: path-traversal guard on --deployment-id (Phase 47)"
echo "=============================================================="
reset_state
CMD_ARGS=(status --environment rehearsal --deployment-id "../../../../etc/passwd")
OUT="$(run_controller 2>&1)"; RC=$?
assert_exit 1 "$RC" "path-traversal-shaped --deployment-id refused"
assert_contains "$OUT" "does not match the expected shape" "clear refusal reason"
[[ ! -e "/etc/passwd.d" ]] && pass "no directory created outside the state root" || fail "no directory created outside the state root"

CMD_ARGS=(status --environment rehearsal --deployment-id "not-a-real-shape")
OUT="$(run_controller 2>&1)"; RC=$?
assert_exit 1 "$RC" "arbitrary non-matching --deployment-id also refused"

echo
echo "=============================================================="
echo "RESULTS: $PASS passed, $FAIL failed"
echo "=============================================================="
if [[ $FAIL -gt 0 ]]; then
  echo "Failed cases:"
  printf '  - %s\n' "${FAILED_NAMES[@]}"
  exit 1
fi
exit 0
