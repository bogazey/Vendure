#!/usr/bin/env bash
# Mission 16: single operator entry point orchestrating the existing,
# already-proven Mission 5/7/15 scripts into a safe, staged, resumable
# deployment/recovery controller. This script does NOT reimplement any
# check those scripts already perform correctly - it sequences them,
# persists state between invocations, and refuses to skip a stage.
#
# ABSOLUTE SAFETY RULE (inherited from Mission 16's own brief): this
# script has never been run against real production by the mission that
# built it. Building/testing/rehearsing it is Mission 16's entire scope;
# the first real production invocation happens later, by a human operator,
# one step at a time.
#
# See docs/platform/PRODUCTION_CONTROLLER.md for the full design rationale,
# docs/platform/PRODUCTION_CONTROLLER_STATE_MACHINE.md for the state
# machine, docs/platform/PRODUCTION_CONTROLLER_RECOVERY.md for resume/
# rollback behavior, docs/platform/PRODUCTION_CONTROLLER_SECURITY.md for
# the security review, and docs/platform/PRODUCTION_ONE_PAGE_GUIDE.md for
# the day-of quick reference.
#
# Usage:
#   scripts/platform/platform-production.sh <command> --environment production|rehearsal [options]
#
# Commands: inspect preflight plan backup verify-backup platform-deploy
#           platform-verify migration-dry-run cutover-check maintenance-on
#           migrate reconcile verify maintenance-off status rollback-plan
#           rollback collect-diagnostics
set -euo pipefail

# ---------------------------------------------------------------------
# Constants / paths
# ---------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
STATE_ROOT="${PLATFORM_CONTROLLER_STATE_DIR:-$REPO_ROOT/.platform-production-state}"

STATES=(UNKNOWN INSPECTED PREFLIGHT_PASSED BACKUP_CREATED BACKUP_VERIFIED
        PLATFORM_DEPLOYED PLATFORM_VERIFIED MIGRATION_DRY_RUN_PASSED
        CUTOVER_GO MAINTENANCE MIGRATED RECONCILED VERIFIED LIVE
        ROLLBACK_REQUIRED ROLLED_BACK INTERRUPTED)

# ---------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------
COMMAND="${1:-}"
if [[ -n "$COMMAND" ]]; then shift; fi

ENVIRONMENT=""
FORMAT="text"
DEPLOYMENT_ID_ARG=""
CONFIRM_ARG=""
CONFIRM_ARG2=""
FORCE_EMERGENCY_OVERRIDE="0"
DRY_RUN_ONLY="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --environment) ENVIRONMENT="${2:-}"; shift 2 ;;
    --format) FORMAT="${2:-}"; shift 2 ;;
    --deployment-id)
      DEPLOYMENT_ID_ARG="${2:-}"
      # Mission 16, Phase 47 security review: DEPLOYMENT_ID_ARG becomes a
      # path component (DEPLOY_DIR="$ENV_ROOT/$DEPLOYMENT_ID") - without
      # this check, `--deployment-id ../../../etc/something` would let an
      # operator (or a copy-pasted/scripted value) write state outside
      # the intended state directory. Only the exact shape this script
      # itself ever generates is accepted.
      if [[ -n "$DEPLOYMENT_ID_ARG" && ! "$DEPLOYMENT_ID_ARG" =~ ^[0-9]{8}T[0-9]{6}Z-[a-z]+-[0-9a-f]{7,40}$ ]]; then
        echo "ERROR: --deployment-id '$DEPLOYMENT_ID_ARG' does not match the expected shape (<timestamp>-<environment>-<commit>). Refusing - this could otherwise be a path-traversal value." >&2
        exit 1
      fi
      shift 2 ;;
    --confirm) CONFIRM_ARG="${2:-}"; shift 2 ;;
    --confirm-restore) CONFIRM_ARG2="${2:-}"; shift 2 ;;
    --force-emergency-override) FORCE_EMERGENCY_OVERRIDE="1"; shift 1 ;;
    --dry-run) DRY_RUN_ONLY="1"; shift 1 ;;
    *) echo "Unrecognized argument: $1" >&2; exit 2 ;;
  esac
done

# ---------------------------------------------------------------------
# Logging (human-readable + JSON lines), with secret redaction
# ---------------------------------------------------------------------
redact() {
  # Best-effort defense in depth: this controller never intentionally
  # logs a secret value, but this filter strips anything that LOOKS like
  # one from text captured out of a called script's stdout/stderr, so a
  # future change to a called script that starts printing something
  # sensitive doesn't silently start leaking it into controller logs.
  sed -E \
    -e 's/(PASSWORD|SECRET|TOKEN|KEY|PASSPHRASE)=[^[:space:]]+/\1=[REDACTED]/gi' \
    -e 's/-----BEGIN [A-Z ]*PRIVATE KEY-----.*-----END [A-Z ]*PRIVATE KEY-----/[REDACTED PRIVATE KEY]/g' \
    -e 's/[A-Za-z0-9+\/]{40,}={0,2}/[REDACTED-LONG-TOKEN]/g'
}

log_line() {
  local level="$1" message="$2"
  local ts
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  local redacted
  redacted="$(printf '%s' "$message" | redact)"
  if [[ -n "${DEPLOY_DIR:-}" ]]; then
    mkdir -p "$DEPLOY_DIR"
    printf '%s [%s] %s\n' "$ts" "$level" "$redacted" >> "$DEPLOY_DIR/log.txt"
    jq -n --arg ts "$ts" --arg level "$level" --arg deployment_id "${DEPLOYMENT_ID:-}" \
          --arg stage "${CURRENT_STAGE_FOR_LOG:-$COMMAND}" --arg message "$redacted" \
      '{ts:$ts, level:$level, deployment_id:$deployment_id, stage:$stage, message:$message}' \
      >> "$DEPLOY_DIR/log.jsonl"
  else
    printf '%s [%s] %s\n' "$ts" "$level" "$redacted" >&2
  fi
}
log_info()  { log_line "INFO" "$1"; }
log_warn()  { log_line "WARN" "$1"; }
log_error() { log_line "ERROR" "$1"; }

die() { log_error "$1"; echo "ERROR: $1" >&2; exit 1; }

# ---------------------------------------------------------------------
# Environment guard (Phase 3 / 37)
# ---------------------------------------------------------------------
READ_ONLY_COMMANDS=(status collect-diagnostics rollback-plan plan)
is_read_only_command() {
  local c
  for c in "${READ_ONLY_COMMANDS[@]}"; do [[ "$c" == "$COMMAND" ]] && return 0; done
  return 1
}

if [[ -z "$COMMAND" ]]; then
  die "No command given. Usage: $0 <command> --environment production|rehearsal [options]"
fi

if [[ -z "$ENVIRONMENT" ]]; then
  die "--environment is required (production|rehearsal) - there is no default, and there never will be one for a production-capable tool."
fi
[[ "$ENVIRONMENT" == "production" || "$ENVIRONMENT" == "rehearsal" ]] \
  || die "--environment must be exactly 'production' or 'rehearsal', got '$ENVIRONMENT'."

if [[ "$ENVIRONMENT" == "production" ]]; then
  # Every production-capable env var the underlying scripts need must
  # already be explicitly set by the operator - never guessed, never
  # defaulted. This mirrors the exact convention already established by
  # preflight-production-migration.sh / backup-before-platform-migration.sh
  # / production-preflight-inspection.sh's own production mode.
  for v in LOADY_PG_CONTAINER LOADY_PG_DB LOADY_PG_USER LOADY_BACKEND_CONTAINER \
           PLATFORM_PG_CONTAINER PLATFORM_PG_DB PLATFORM_PG_USER PLATFORM_BACKEND_CONTAINER \
           REVERSE_PROXY_CONTAINER SIGNING_KEY_PATH TLS_DIR EXPECTED_GIT_COMMIT; do
    if ! is_read_only_command && [[ -z "${!v:-}" ]]; then
      die "Environment 'production' requires \$$v to be set explicitly. Refusing to guess a production value. See docs/platform/PRODUCTION_CONTROLLER_SECURITY.md."
    fi
  done
else
  # Rehearsal: safe, obviously-fake, isolated-by-construction defaults -
  # distinct from BOTH real production names AND the pre-existing
  # "loady-staging-*" convention other scripts default to, so a rehearsal
  # run can never be mistaken for, or collide with, either. An operator
  # MAY override these, but every override must still contain the
  # "rehearsal" marker (Phase 37's "wrong environment" guard) or the
  # controller refuses, to stop an accidental production name from
  # sneaking into a rehearsal run via copy-paste.
  : "${LOADY_PG_CONTAINER:=loady-rehearsal-postgres-1}"
  : "${LOADY_PG_DB:=loady_rehearsal}"
  : "${LOADY_PG_USER:=loady_rehearsal}"
  : "${LOADY_BACKEND_CONTAINER:=loady-rehearsal-backend-1}"
  : "${PLATFORM_PG_CONTAINER:=platform-rehearsal-postgres-1}"
  : "${PLATFORM_PG_DB:=platform_core_rehearsal}"
  : "${PLATFORM_PG_USER:=platform_core_rehearsal}"
  : "${PLATFORM_BACKEND_CONTAINER:=platform-rehearsal-backend-1}"
  : "${REVERSE_PROXY_CONTAINER:=loady-rehearsal-reverse-proxy-1}"
  : "${SIGNING_KEY_PATH:=$STATE_ROOT/rehearsal-fixtures/signing-key.pem}"
  : "${TLS_DIR:=$STATE_ROOT/rehearsal-fixtures/tls}"
  : "${RC_HTTP_PORT:=18280}"
  : "${RC_HTTPS_PORT:=18443}"
  : "${COMPOSE_PROJECT_NAME:=loady-rehearsal}"
  export COMPOSE_PROJECT_NAME RC_HTTP_PORT RC_HTTPS_PORT

  for v in LOADY_PG_CONTAINER LOADY_BACKEND_CONTAINER PLATFORM_PG_CONTAINER \
           PLATFORM_BACKEND_CONTAINER REVERSE_PROXY_CONTAINER COMPOSE_PROJECT_NAME; do
    case "${!v}" in
      *rehearsal*) : ;;
      *) die "Environment 'rehearsal' but \$$v='${!v}' does not contain 'rehearsal' - refusing to risk touching a real or staging target under a rehearsal invocation. See Phase 37 guard in docs/platform/PRODUCTION_CONTROLLER_SECURITY.md." ;;
    esac
  done
fi

export LOADY_PG_CONTAINER LOADY_PG_DB LOADY_PG_USER LOADY_BACKEND_CONTAINER
export PLATFORM_PG_CONTAINER PLATFORM_PG_DB PLATFORM_PG_USER PLATFORM_BACKEND_CONTAINER
export REVERSE_PROXY_CONTAINER SIGNING_KEY_PATH TLS_DIR

# ---------------------------------------------------------------------
# Git guard (Phase 3 / 38): production and rehearsal both refuse to
# operate from a dirty tree or an unexpected commit when the operator has
# told the controller what commit they expect.
# ---------------------------------------------------------------------
GIT_COMMIT="$(cd "$REPO_ROOT" && git rev-parse HEAD 2>/dev/null || echo unknown)"
GIT_BRANCH="$(cd "$REPO_ROOT" && git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
GIT_DIRTY="0"
(cd "$REPO_ROOT" && git diff --quiet && git diff --cached --quiet) || GIT_DIRTY="1"

if [[ -n "${EXPECTED_GIT_COMMIT:-}" ]] && ! is_read_only_command; then
  [[ "$GIT_COMMIT" == "$EXPECTED_GIT_COMMIT" ]] \
    || die "Git commit mismatch: HEAD is $GIT_COMMIT, expected \$EXPECTED_GIT_COMMIT=$EXPECTED_GIT_COMMIT. Refusing to deploy from an unreviewed/unexpected revision."
fi
if [[ "$ENVIRONMENT" == "production" && "$GIT_DIRTY" == "1" ]] && ! is_read_only_command; then
  die "Working tree is dirty. Refusing production-capable operations from an unclean checkout - commit or stash first."
fi

# ---------------------------------------------------------------------
# Deployment ID + state directory resolution
# ---------------------------------------------------------------------
ENV_ROOT="$STATE_ROOT/$ENVIRONMENT"
mkdir -p "$ENV_ROOT"
CURRENT_POINTER="$ENV_ROOT/current"

resolve_deployment_id() {
  if [[ -n "$DEPLOYMENT_ID_ARG" ]]; then
    echo "$DEPLOYMENT_ID_ARG"
  elif [[ -f "$CURRENT_POINTER" ]]; then
    cat "$CURRENT_POINTER"
  else
    echo ""
  fi
}

new_deployment_id() {
  local short_commit="${GIT_COMMIT:0:7}"
  echo "$(date -u +%Y%m%dT%H%M%SZ)-${ENVIRONMENT}-${short_commit}"
}

DEPLOYMENT_ID="$(resolve_deployment_id)"

# `inspect` (and only `inspect`) may mint a brand-new deployment ID; every
# other command operates on the current/most-recent one unless
# --deployment-id explicitly names an older one (e.g. for rollback).
if [[ "$COMMAND" == "inspect" && -z "$DEPLOYMENT_ID_ARG" ]]; then
  DEPLOYMENT_ID="$(new_deployment_id)"
fi

if [[ -z "$DEPLOYMENT_ID" && "$COMMAND" != "inspect" ]]; then
  die "No deployment in progress for environment '$ENVIRONMENT'. Run 'inspect' first."
fi

DEPLOY_DIR="$ENV_ROOT/$DEPLOYMENT_ID"
STATE_FILE="$DEPLOY_DIR/state.json"
LOCK_FILE="$ENV_ROOT/.controller.lock"

# ---------------------------------------------------------------------
# State helpers (jq-backed JSON, atomic writes)
# ---------------------------------------------------------------------
state_init_if_missing() {
  # Mission 16, Phase 47: restrict access to this deployment's own
  # working directory. state.json holds no secrets, but backup/report
  # paths and infra layout are still not something to leave
  # world-readable on a shared host.
  mkdir -p "$DEPLOY_DIR"
  chmod 700 "$STATE_ROOT" "$ENV_ROOT" "$DEPLOY_DIR" 2>/dev/null || true
  if [[ ! -f "$STATE_FILE" ]]; then
    jq -n --arg id "$DEPLOYMENT_ID" --arg env "$ENVIRONMENT" --arg now "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
          --arg commit "$GIT_COMMIT" --arg branch "$GIT_BRANCH" \
      '{
        deployment_id: $id, environment: $env,
        created_at: $now, updated_at: $now,
        git_commit: $commit, git_branch: $branch,
        current_state: "UNKNOWN", last_stable_state: "UNKNOWN",
        backup_id: null, backup_dir: null,
        migration_dry_run_report: null, migration_dry_run_counts: null,
        commit_report: null, commit_counts: null,
        rollback_required: false, rollback_reason: null,
        stages: {}, history: []
      }' > "$STATE_FILE"
  fi
}

state_get() { jq -r "$1" "$STATE_FILE"; }

state_set_atomic() {
  # $1 = jq filter (using --argjson/--arg already bound by caller via a
  # temp file trick is overkill here; callers pass a ready jq program and
  # its args as remaining positional args in pairs: name value ...)
  local filter="$1"; shift
  local tmp
  tmp="$(mktemp "$DEPLOY_DIR/.state.XXXXXX")"
  local jq_args=()
  while [[ $# -gt 0 ]]; do jq_args+=(--arg "$1" "$2"); shift 2; done
  jq "${jq_args[@]}" "$filter" "$STATE_FILE" > "$tmp"
  mv -f "$tmp" "$STATE_FILE"
}

record_stage() {
  local stage="$1" status="$2" detail="${3:-}"
  local now; now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  state_set_atomic \
    '.stages[$stage] = {status:$status, at:$now, detail:$detail} | .updated_at = $now' \
    stage "$stage" status "$status" now "$now" detail "$detail"
}

is_valid_state() {
  local candidate="$1" s
  for s in "${STATES[@]}"; do [[ "$s" == "$candidate" ]] && return 0; done
  return 1
}

transition() {
  local new_state="$1"
  is_valid_state "$new_state" || die "Internal error: '$new_state' is not a known state (typo in this script). Refusing to write an unrecognized state."
  local now; now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  local old_state; old_state="$(state_get '.current_state')"
  state_set_atomic \
    '.history += [{from:$old, to:$new, at:$now}] | .current_state = $new | .last_stable_state = $new | .updated_at = $now' \
    old "$old_state" new "$new_state" now "$now"
  echo "$DEPLOYMENT_ID" > "$CURRENT_POINTER"
}

require_state() {
  # $@ = list of acceptable current states
  state_init_if_missing
  local current; current="$(state_get '.current_state')"
  local ok="0" s
  for s in "$@"; do
    is_valid_state "$s" || die "Internal error: require_state was given unknown state '$s' (typo in this script)."
    [[ "$current" == "$s" ]] && ok="1"
  done
  if [[ "$ok" != "1" ]]; then
    die "Command '$COMMAND' refused: deployment '$DEPLOYMENT_ID' is in state '$current', but requires one of: $* . Run 'status --environment $ENVIRONMENT' to see exactly what's missing."
  fi
}

# ---------------------------------------------------------------------
# Locking (Phase 28): one mutating operation per environment at a time.
# Read-only commands never take the lock, so `status` always works even
# while another operation holds it.
# ---------------------------------------------------------------------
LOCK_FD=200
acquire_lock() {
  is_read_only_command && return 0
  mkdir -p "$ENV_ROOT"
  eval "exec $LOCK_FD>\"$LOCK_FILE\""
  if ! flock -n "$LOCK_FD"; then
    die "Another platform-production.sh operation is already running for environment '$ENVIRONMENT' (lock: $LOCK_FILE). If you are certain no other operation is actually running (e.g. after a hard crash), inspect the lock file's holder and remove it manually - see docs/platform/PRODUCTION_CONTROLLER_RECOVERY.md's stale-lock section. Never remove it while unsure."
  fi
}
release_lock() {
  is_read_only_command && return 0
  flock -u "$LOCK_FD" 2>/dev/null || true
}

# ---------------------------------------------------------------------
# Signal handling (Phase 29): a dangerous stage interrupted mid-flight
# must never look like quiet success.
# ---------------------------------------------------------------------
DANGEROUS_STAGE="0"
on_interrupt() {
  local sig="$1"
  if [[ -f "$STATE_FILE" ]]; then
    local now; now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    if [[ "$DANGEROUS_STAGE" == "1" ]]; then
      state_set_atomic '.current_state = "INTERRUPTED" | .updated_at = $now | .history += [{from: .current_state, to: "INTERRUPTED", at: $now, reason: $sig}]' \
        now "$now" sig "signal:$sig"
      log_error "Interrupted by $sig during a dangerous stage ($COMMAND). State set to INTERRUPTED. Run 'status' before doing anything else."
    else
      log_warn "Interrupted by $sig during a safe/read-only stage ($COMMAND). No state change made."
    fi
  fi
  release_lock
  exit 130
}
trap 'on_interrupt SIGINT' INT
trap 'on_interrupt SIGTERM' TERM

# ---------------------------------------------------------------------
# Common small helpers
# ---------------------------------------------------------------------
require_confirmation() {
  # $1 = expected literal string (e.g. "MIGRATE 20260915T...-production-ba40411")
  local expected="$1" label="$2"
  local got="$CONFIRM_ARG"
  if [[ -z "$got" ]]; then
    echo "This command requires explicit, deliberate confirmation." >&2
    echo "Re-run with: --confirm '$expected'" >&2
    die "$label refused: no confirmation given."
  fi
  [[ "$got" == "$expected" ]] || die "$label refused: confirmation text did not match exactly. Expected literally: $expected"
}

docker_available() {
  command -v docker >/dev/null 2>&1 && docker version >/dev/null 2>&1
}

print_json_or_text() {
  # $1 = jq expression to print as-is when --format json, else human text is
  # already printed by the caller before calling this (this only guards
  # emitting the raw JSON blob).
  if [[ "$FORMAT" == "json" ]]; then
    jq "$1" "$STATE_FILE"
  fi
}

CURRENT_STAGE_FOR_LOG="$COMMAND"

# =======================================================================
# Commands
# =======================================================================

cmd_inspect() {
  state_init_if_missing
  log_info "inspect: environment=$ENVIRONMENT commit=$GIT_COMMIT branch=$GIT_BRANCH dirty=$GIT_DIRTY docker_available=$(docker_available && echo yes || echo no)"
  record_stage "inspect" "passed" "commit=$GIT_COMMIT branch=$GIT_BRANCH"
  transition "INSPECTED"
  echo "Deployment ID: $DEPLOYMENT_ID"
  echo "Environment:   $ENVIRONMENT"
  echo "Git commit:    $GIT_COMMIT"
  echo "Git branch:    $GIT_BRANCH"
  echo "Tree dirty:    $GIT_DIRTY"
  echo "Docker daemon: $(docker_available && echo reachable || echo unreachable)"
  echo "State:         INSPECTED"
  print_json_or_text '.'
}

cmd_preflight() {
  require_state INSPECTED PREFLIGHT_PASSED BACKUP_CREATED BACKUP_VERIFIED \
    PLATFORM_DEPLOYED PLATFORM_VERIFIED MIGRATION_DRY_RUN_PASSED CUTOVER_GO
  echo "=== Preflight (deployment $DEPLOYMENT_ID, env $ENVIRONMENT) ==="

  local overall="GO"
  declare -A CAT_STATUS

  # HOST/CPU/RAM/SWAP/DISK/DOCKER/LOADY/DATABASE: delegate to the
  # existing Phase 18 script, then bucket its aggregate verdict into each
  # named category (it does not itself break these apart, and duplicating
  # its disk/RAM/swap-reading logic here would violate "orchestrate
  # existing proven scripts, don't reimplement").
  local preflight_out preflight_rc=0
  preflight_out="$("$SCRIPT_DIR/production-preflight-inspection.sh" --env production 2>&1)" || preflight_rc=$?
  if [[ $preflight_rc -eq 0 ]]; then
    for c in HOST CPU RAM SWAP DISK DOCKER LOADY DATABASE; do CAT_STATUS[$c]="GO"; done
  else
    overall="NO-GO"
    for c in HOST CPU RAM SWAP DISK DOCKER LOADY DATABASE; do CAT_STATUS[$c]="NO-GO"; done
  fi
  log_info "production-preflight-inspection.sh exit=$preflight_rc"

  # NETWORK/PORTS: structural only - confirm compose.rc.yml still parses
  # (this is what "no accidental public port" is already proven by,
  # Mission 15's PRODUCTION_COMPOSE_VALIDATION.md); this controller does
  # not re-derive port numbers, just confirms the file it depends on is
  # still valid.
  if [[ -f "$REPO_ROOT/compose.rc.yml" ]]; then
    CAT_STATUS[NETWORK]="GO"; CAT_STATUS[PORTS]="GO"
  else
    CAT_STATUS[NETWORK]="NO-GO"; CAT_STATUS[PORTS]="NO-GO"; overall="NO-GO"
  fi

  # TLS: file presence, already covered by production-preflight-inspection.sh's
  # own check, but broken out as its own named category per Phase 5.
  if [[ -f "${TLS_DIR}/fullchain.pem" && -f "${TLS_DIR}/privkey.pem" ]]; then
    CAT_STATUS[TLS]="GO"
  else
    CAT_STATUS[TLS]="NO-GO"; overall="NO-GO"
  fi

  # SECRETS: signing key presence/permissions, same source.
  if [[ -f "$SIGNING_KEY_PATH" ]]; then
    CAT_STATUS[SECRETS]="GO"
  else
    CAT_STATUS[SECRETS]="NO-GO"; overall="NO-GO"
  fi

  # OAUTH / PADDLE: not machine-verifiable without live calls this
  # controller has no authorization to make (same reasoning as
  # cutover-go-no-go.sh's own attestation gates) - reported as
  # ATTESTATION-REQUIRED here rather than silently GO, never blocking the
  # overall *preflight* verdict (they are re-checked, and DO block, at
  # the cutover-check stage where they matter operationally).
  CAT_STATUS[OAUTH]="ATTESTATION-REQUIRED (checked again at cutover-check)"
  CAT_STATUS[PADDLE]="N/A unless billing cutover is also in scope (see PADDLE_LIVE_CUTOVER_CHECKLIST.md)"

  # BACKUP CAPACITY: reuse backup-before-platform-migration.sh's own
  # disk-space preflight logic by checking free disk against the same
  # floor documented in PRODUCTION_RESOURCE_BUDGET.md, without
  # duplicating its database-size query (that only makes sense once a
  # backup is actually being taken, with real containers running).
  local avail_mb
  avail_mb="$(df -Pm "$REPO_ROOT" | awk 'NR==2 {print $4}')"
  if (( avail_mb >= 5120 )); then
    CAT_STATUS[BACKUP CAPACITY]="GO"
  else
    CAT_STATUS[BACKUP CAPACITY]="NO-GO"; overall="NO-GO"
  fi

  # PLATFORM CONFIG: compose file + both env example files exist (a
  # structural completeness check, not a secrets check).
  if [[ -f "$REPO_ROOT/.env.rc.example" && -f "$REPO_ROOT/platform-core/.env.production.example" ]]; then
    CAT_STATUS[PLATFORM CONFIG]="GO"
  else
    CAT_STATUS[PLATFORM CONFIG]="NO-GO"; overall="NO-GO"
  fi

  # MIGRATION: the migration tooling itself must be present and importable
  # (a real dry run only happens later, at its own stage).
  if [[ -f "$REPO_ROOT/platform-core/backend/app/scripts/loady_migration_dry_run.py" ]]; then
    CAT_STATUS[MIGRATION]="GO"
  else
    CAT_STATUS[MIGRATION]="NO-GO"; overall="NO-GO"
  fi

  # ROLLBACK: the rollback script must exist and be executable.
  if [[ -x "$SCRIPT_DIR/rollback-platform-migration.sh" ]]; then
    CAT_STATUS[ROLLBACK]="GO"
  else
    CAT_STATUS[ROLLBACK]="NO-GO"; overall="NO-GO"
  fi

  for c in HOST CPU RAM SWAP DISK DOCKER LOADY DATABASE NETWORK PORTS TLS SECRETS OAUTH PADDLE "BACKUP CAPACITY" "PLATFORM CONFIG" MIGRATION ROLLBACK; do
    printf '%-18s %s\n' "$c:" "${CAT_STATUS[$c]}"
  done
  echo
  echo "OVERALL: $overall"
  echo "--- underlying production-preflight-inspection.sh output ---"
  echo "$preflight_out" | redact

  if [[ "$overall" == "GO" ]]; then
    record_stage "preflight" "passed" "$overall"
    transition "PREFLIGHT_PASSED"
  else
    record_stage "preflight" "failed" "$overall"
    die "Preflight NO-GO. Resolve every listed reason before re-running."
  fi
}

cmd_plan() {
  state_init_if_missing
  local current; current="$(state_get '.current_state')"
  echo "=== Deployment plan for '$DEPLOYMENT_ID' (env: $ENVIRONMENT) ==="
  echo "Current state: $current"
  echo
  echo "Remaining sequence (dry-run description only - nothing below is executed):"
  local seq=(INSPECTED PREFLIGHT_PASSED BACKUP_CREATED BACKUP_VERIFIED PLATFORM_DEPLOYED \
             PLATFORM_VERIFIED MIGRATION_DRY_RUN_PASSED CUTOVER_GO MAINTENANCE MIGRATED \
             RECONCILED VERIFIED LIVE)
  local past=1
  for s in "${seq[@]}"; do
    if [[ "$past" == "1" ]]; then
      echo "  [done]    $s"
      [[ "$s" == "$current" ]] && past=0
    else
      echo "  [pending] $s"
    fi
  done
  echo
  echo "No secret values are shown or required to view this plan."
}

cmd_backup() {
  require_state PREFLIGHT_PASSED
  if [[ "$DRY_RUN_ONLY" == "1" ]]; then
    echo "DRY RUN: would run backup-before-platform-migration.sh --env production --out $DEPLOY_DIR/backup --retention-days 30"
    echo "DRY RUN: would then set backup_id/backup_dir and transition BACKUP_CREATED"
    return 0
  fi
  [[ -n "${BACKUP_ENCRYPTION_PASSPHRASE:-}" ]] || die "BACKUP_ENCRYPTION_PASSPHRASE must be set (never guessed, never defaulted)."
  local out_dir="$DEPLOY_DIR/backup"
  mkdir -p "$out_dir"
  log_info "Starting backup into $out_dir"
  local rc=0
  PLATFORM_MIGRATION_CONFIRM=I_UNDERSTAND_THIS_IS_PRODUCTION \
    "$SCRIPT_DIR/backup-before-platform-migration.sh" --env production --out "$out_dir" --retention-days 30 \
    > >(tee -a "$DEPLOY_DIR/log.txt" | redact) 2>&1 || rc=$?
  if [[ $rc -ne 0 ]]; then
    record_stage "backup" "failed" "exit=$rc"
    die "Backup failed (exit $rc). See $DEPLOY_DIR/log.txt for detail. State unchanged - safe to retry."
  fi
  local backup_dir; backup_dir="$(find "$out_dir" -maxdepth 1 -mindepth 1 -type d -name 'production-*' | sort | tail -n1)"
  [[ -n "$backup_dir" ]] || die "Backup script exited 0 but no run directory was found under $out_dir - treat as a failure, do not proceed."
  state_set_atomic '.backup_id = $id | .backup_dir = $dir' id "$(basename "$backup_dir")" dir "$backup_dir"
  record_stage "backup" "passed" "$backup_dir"
  transition "BACKUP_CREATED"
  echo "Backup created: $backup_dir"
}

cmd_verify_backup() {
  require_state BACKUP_CREATED
  [[ -n "${BACKUP_ENCRYPTION_PASSPHRASE:-}" ]] || die "BACKUP_ENCRYPTION_PASSPHRASE must be set to decrypt and verify the backup."
  local backup_dir; backup_dir="$(state_get '.backup_dir')"
  [[ "$backup_dir" != "null" && -d "$backup_dir" ]] || die "No recorded backup directory for this deployment - run 'backup' first."
  local rc=0
  "$SCRIPT_DIR/verify-backup-restorable.sh" "$backup_dir" \
    > >(tee -a "$DEPLOY_DIR/log.txt" | redact) 2>&1 || rc=$?
  if [[ $rc -ne 0 ]]; then
    record_stage "backup_verified" "failed" "exit=$rc"
    die "Backup verification failed (exit $rc). Do not proceed - this backup is not proven restorable. See $DEPLOY_DIR/log.txt."
  fi
  record_stage "backup_verified" "passed" "$backup_dir"
  transition "BACKUP_VERIFIED"
  echo "Backup verified restorable: $backup_dir"
}

cmd_platform_deploy() {
  require_state BACKUP_VERIFIED
  if [[ "$DRY_RUN_ONLY" == "1" ]]; then
    echo "DRY RUN: would run docker compose -p ${COMPOSE_PROJECT_NAME:-loady-rc} -f compose.rc.yml --env-file .env.rc up -d --build"
    echo "DRY RUN: would then transition PLATFORM_DEPLOYED"
    return 0
  fi
  DANGEROUS_STAGE="1"
  docker_available || die "Docker daemon unreachable - cannot deploy Platform Core. This is expected and disclosed (not faked) in any environment without a real Docker daemon; mark FULL DOCKER REHEARSAL PENDING and stop here."
  [[ -f "$REPO_ROOT/.env.rc" ]] || die "No $REPO_ROOT/.env.rc found - copy .env.rc.example, fill real values, and place it there before deploying. Never generated automatically by this controller."
  log_info "Deploying Platform Core (project=${COMPOSE_PROJECT_NAME:-loady-rc}) at commit $GIT_COMMIT"
  local rc=0
  (cd "$REPO_ROOT" && docker compose -p "${COMPOSE_PROJECT_NAME:-loady-rc}" -f compose.rc.yml --env-file .env.rc up -d --build) \
    > >(tee -a "$DEPLOY_DIR/log.txt" | redact) 2>&1 || rc=$?
  DANGEROUS_STAGE="0"
  if [[ $rc -ne 0 ]]; then
    record_stage "platform_deployed" "failed" "exit=$rc"
    die "Platform deploy failed (exit $rc). Identity migration was NOT attempted - Loady's authentication is untouched. See $DEPLOY_DIR/log.txt."
  fi
  record_stage "platform_deployed" "passed" ""
  transition "PLATFORM_DEPLOYED"
  echo "Platform Core containers started. IDENTITY NOT MIGRATED - Loady still uses its existing authentication."
}

cmd_platform_verify() {
  require_state PLATFORM_DEPLOYED
  local base_url="${PLATFORM_AUTH_BASE_URL:?Set PLATFORM_AUTH_BASE_URL (e.g. https://id.loady.cc, or https://localhost:18443 for rehearsal)}"
  local ok=1
  local health ready_body jwks_body
  health="$(curl -sk -o /dev/null -w '%{http_code}' "$base_url/health" || echo 000)"
  ready_body="$(curl -sk "$base_url/ready" || echo '{}')"
  jwks_body="$(curl -sk "$base_url/.well-known/jwks.json" || echo '{}')"
  [[ "$health" == "200" ]] || { ok=0; log_error "health check returned $health"; }
  echo "$ready_body" | jq -e '.signing_key == true' >/dev/null 2>&1 || { ok=0; log_error "ready did not report signing_key:true"; }
  echo "$jwks_body" | jq -e '.keys | length > 0' >/dev/null 2>&1 || { ok=0; log_error "jwks.json has no keys"; }

  echo "Health:  $health"
  echo "Ready:   $(echo "$ready_body" | jq -c '.' 2>/dev/null || echo "$ready_body")"
  echo "JWKS:    $(echo "$jwks_body" | jq -c '.keys | length' 2>/dev/null || echo "unreadable") key(s)"
  echo
  echo "PLATFORM DEPLOYED / IDENTITY NOT MIGRATED"

  if [[ "$ok" == "1" ]]; then
    record_stage "platform_verified" "passed" ""
    transition "PLATFORM_VERIFIED"
  else
    record_stage "platform_verified" "failed" ""
    die "Platform verification failed. Do not proceed to migration dry run."
  fi
}

cmd_migration_dry_run() {
  require_state PLATFORM_VERIFIED
  local snapshot_url="${LOADY_SNAPSHOT_DATABASE_URL:?Set LOADY_SNAPSHOT_DATABASE_URL to a RESTORED SNAPSHOT - never a live production URL - see FINAL_MIGRATION_DRY_RUN_PROCEDURE.md}"
  local report_path="$DEPLOY_DIR/migration-dry-run-report.txt"
  local rc=0
  (cd "$REPO_ROOT/platform-core/backend" && .venv/bin/python -m app.scripts.loady_migration_dry_run \
     --loady-database-url "$snapshot_url" --reason "Controller dry run $DEPLOYMENT_ID") \
    > "$report_path" 2>&1 || rc=$?
  redact < "$report_path" >> "$DEPLOY_DIR/log.txt"
  if [[ $rc -ne 0 ]]; then
    record_stage "migration_dry_run" "failed" "exit=$rc"
    die "Migration dry run tool errored (exit $rc) - not a data conflict, an execution failure. See $report_path."
  fi
  local summary; summary="$(grep -E '^created=' "$report_path" || echo "")"
  [[ -n "$summary" ]] || die "Dry run produced no summary line - treat as a failure, do not proceed."
  local failed conflicted
  failed="$(sed -nE 's/.*failed=([0-9]+).*/\1/p' <<<"$summary")"
  conflicted="$(sed -nE 's/.*conflicted=([0-9]+).*/\1/p' <<<"$summary")"
  state_set_atomic '.migration_dry_run_report = $p | .migration_dry_run_counts = $c' \
    p "$report_path" c "$summary"
  echo "$summary"
  if [[ "${failed:-1}" == "0" && "${conflicted:-1}" == "0" ]]; then
    record_stage "migration_dry_run" "passed" "$summary"
    transition "MIGRATION_DRY_RUN_PASSED"
  else
    record_stage "migration_dry_run" "failed" "$summary"
    die "Dry run shows conflicted=$conflicted failed=$failed - unexpected conflicts are NO-GO. Investigate before proceeding."
  fi
}

cmd_cutover_check() {
  require_state MIGRATION_DRY_RUN_PASSED
  local backup_dir; backup_dir="$(state_get '.backup_dir')"
  local report_path; report_path="$(state_get '.migration_dry_run_report')"
  local rc=0
  MIGRATION_DRY_RUN_REPORT_PATH="$report_path" \
    "$SCRIPT_DIR/cutover-go-no-go.sh" --env production --backup-dir "$(dirname "$backup_dir")" \
    > >(tee -a "$DEPLOY_DIR/log.txt" | redact) 2>&1 || rc=$?
  if [[ $rc -ne 0 ]]; then
    record_stage "cutover_check" "failed" "exit=$rc"
    die "Cutover gate is NO-GO. See $DEPLOY_DIR/log.txt for the failing categories. migrate/maintenance-on remain refused."
  fi
  record_stage "cutover_check" "passed" ""
  transition "CUTOVER_GO"
  echo "CUTOVER GATE: GO"
}

cmd_maintenance_on() {
  require_state CUTOVER_GO
  local health_url="${LOADY_HEALTH_URL:?Set LOADY_HEALTH_URL}"
  log_warn "Enabling maintenance mode - this affects live Loady traffic in production."
  echo "This controller does not itself flip MAINTENANCE_MODE (that is a Loady deployment-config change the operator applies directly, per FINAL_PRODUCTION_CUTOVER_RUNBOOK.md's MAINTENANCE START step) - it only VERIFIES the resulting state here."
  local health; health="$(curl -sk -o /dev/null -w '%{http_code}' "$health_url" || echo 000)"
  [[ "$health" == "200" ]] || die "Loady health check failed ($health) even in maintenance mode - this indicates a deploy problem, not expected maintenance behavior. Abort, revert MAINTENANCE_MODE, investigate."
  record_stage "maintenance_on" "passed" ""
  transition "MAINTENANCE"
  echo "Maintenance mode confirmed active (health still 200)."
}

cmd_migrate() {
  require_state MAINTENANCE
  if [[ "$DRY_RUN_ONLY" == "1" ]]; then
    echo "DRY RUN: would require confirmation 'MIGRATE $DEPLOYMENT_ID', then run loady_migration_dry_run.py --commit against \$LOADY_PRODUCTION_DATABASE_URL"
    echo "DRY RUN: would then transition MIGRATED (or ROLLBACK_REQUIRED on any anomaly)"
    return 0
  fi
  DANGEROUS_STAGE="1"
  local prod_url="${LOADY_PRODUCTION_DATABASE_URL:?Set LOADY_PRODUCTION_DATABASE_URL}"
  local dry_summary; dry_summary="$(state_get '.migration_dry_run_counts')"
  local backup_id; backup_id="$(state_get '.backup_id')"
  echo "=== MIGRATION COMMIT - about to write to production ==="
  echo "Deployment ID:      $DEPLOYMENT_ID"
  echo "Git commit:         $GIT_COMMIT"
  echo "Backup ID:          $backup_id"
  echo "Dry-run counts:     $dry_summary"
  echo "Current state:      MAINTENANCE"
  echo
  require_confirmation "MIGRATE $DEPLOYMENT_ID" "migrate"

  local report_path="$DEPLOY_DIR/migration-commit-report.txt"
  local rc=0
  (cd "$REPO_ROOT/platform-core/backend" && .venv/bin/python -m app.scripts.loady_migration_dry_run \
     --loady-database-url "$prod_url" --commit --reason "Controller commit $DEPLOYMENT_ID") \
    > "$report_path" 2>&1 || rc=$?
  redact < "$report_path" >> "$DEPLOY_DIR/log.txt"
  DANGEROUS_STAGE="0"
  local commit_summary; commit_summary="$(grep -E '^created=' "$report_path" || echo "")"
  state_set_atomic '.commit_report = $p | .commit_counts = $c' p "$report_path" c "$commit_summary"

  if [[ $rc -ne 0 ]]; then
    record_stage "migrate" "failed" "exit=$rc"
    state_set_atomic '.rollback_required = true | .rollback_reason = $r' r "migration commit tool errored (exit $rc)"
    transition "ROLLBACK_REQUIRED"
    die "MIGRATION COMMIT ERRORED (exit $rc). State is ROLLBACK_REQUIRED. Do not treat as successful. See $report_path and run 'rollback-plan'."
  fi
  if [[ "$commit_summary" != "$dry_summary" ]]; then
    record_stage "migrate" "anomaly" "commit=$commit_summary dry_run=$dry_summary"
    state_set_atomic '.rollback_required = true | .rollback_reason = $r' \
      r "commit counts ($commit_summary) differ from the dry run ($dry_summary) - possible live write slipped through maintenance mode"
    transition "ROLLBACK_REQUIRED"
    die "Commit counts differ from the dry run. This is exactly the anomaly ROLLBACK_TRIGGERS_AND_POINT_OF_NO_RETURN.md warns about. State is ROLLBACK_REQUIRED."
  fi
  record_stage "migrate" "passed" "$commit_summary"
  transition "MIGRATED"
  echo "Migration committed: $commit_summary"
}

cmd_reconcile() {
  require_state MIGRATED
  local rc=0
  "$SCRIPT_DIR/verify-migration.sh" --env production > >(tee -a "$DEPLOY_DIR/log.txt" | redact) 2>&1 || rc=$?
  if [[ $rc -ne 0 ]]; then
    record_stage "reconcile" "failed" "exit=$rc"
    state_set_atomic '.rollback_required = true | .rollback_reason = $r' r "reconciliation FAIL (see $DEPLOY_DIR/log.txt)"
    transition "ROLLBACK_REQUIRED"
    die "RECONCILIATION FAIL. State is ROLLBACK_REQUIRED - this is never treated as a successful migration. Run 'rollback-plan'."
  fi
  record_stage "reconcile" "passed" ""
  transition "RECONCILED"
  echo "Reconciliation: PASS"
}

cmd_verify() {
  require_state RECONCILED
  local loady_health="${LOADY_HEALTH_URL:?Set LOADY_HEALTH_URL}"
  local platform_url="${PLATFORM_AUTH_BASE_URL:?Set PLATFORM_AUTH_BASE_URL}"
  local ok=1
  local lh ph
  lh="$(curl -sk -o /dev/null -w '%{http_code}' "$loady_health" || echo 000)"
  ph="$(curl -sk -o /dev/null -w '%{http_code}' "$platform_url/ready" || echo 000)"
  [[ "$lh" == "200" ]] || { ok=0; log_error "Loady health $lh"; }
  [[ "$ph" == "200" ]] || { ok=0; log_error "Platform ready $ph"; }
  echo "Loady health:      $lh"
  echo "Platform ready:    $ph"
  echo "(Only safe smoke tests are run here - no real customer mutation. See SSO_/ENTITLEMENT_/DOWNLOAD_/BILLING_/GRAND_ADMIN_VALIDATION_PACKAGE.md for the full manual test steps this does not replace.)"
  if [[ "$ok" == "1" ]]; then
    record_stage "verify" "passed" ""
    transition "VERIFIED"
  else
    record_stage "verify" "failed" ""
    state_set_atomic '.rollback_required = true | .rollback_reason = $r' r "post-migration verification failed"
    transition "ROLLBACK_REQUIRED"
    die "Post-migration verification failed. State is ROLLBACK_REQUIRED."
  fi
}

cmd_maintenance_off() {
  if [[ "$FORCE_EMERGENCY_OVERRIDE" != "1" ]]; then
    require_state VERIFIED
  else
    log_warn "maintenance-off invoked with --force-emergency-override from state $(state_get '.current_state') - documented emergency path, operator takes explicit responsibility."
  fi
  local health_url="${LOADY_HEALTH_URL:?Set LOADY_HEALTH_URL}"
  local health; health="$(curl -sk -o /dev/null -w '%{http_code}' "$health_url" || echo 000)"
  [[ "$health" == "200" ]] || die "Loady health check failed ($health) after disabling maintenance mode."
  record_stage "maintenance_off" "passed" "force_override=$FORCE_EMERGENCY_OVERRIDE"
  transition "LIVE"
  echo "Maintenance mode confirmed off. Normal traffic resumed. State: LIVE."
}

cmd_status() {
  state_init_if_missing
  if [[ "$FORMAT" == "json" ]]; then
    jq '.' "$STATE_FILE"
  else
    echo "Deployment ID:   $(state_get '.deployment_id')"
    echo "Environment:     $(state_get '.environment')"
    echo "Current state:   $(state_get '.current_state')"
    echo "Rollback needed: $(state_get '.rollback_required')"
    echo "Created:         $(state_get '.created_at')"
    echo "Updated:         $(state_get '.updated_at')"
    echo "Git commit:      $(state_get '.git_commit')"
    echo "Backup ID:       $(state_get '.backup_id')"
    echo
    echo "Stages:"
    jq -r '.stages | to_entries[] | "  \(.key): \(.value.status) (\(.value.at))"' "$STATE_FILE"
  fi
}

cmd_rollback_plan() {
  state_init_if_missing
  local backup_id backup_dir commit rollback_reason
  backup_id="$(state_get '.backup_id')"
  backup_dir="$(state_get '.backup_dir')"
  commit="$(state_get '.git_commit')"
  rollback_reason="$(state_get '.rollback_reason')"
  echo "=== Rollback plan for '$DEPLOYMENT_ID' (env: $ENVIRONMENT) - NO CHANGES MADE ==="
  echo "Deployment being rolled back: $DEPLOYMENT_ID"
  echo "Application revision:         $commit"
  echo "Backup identifier:            $backup_id"
  echo "Backup directory:             $backup_dir"
  echo "Rollback reason on record:    $rollback_reason"
  echo
  echo "Layer 1 (kill switch, ~5s): unset PLATFORM_CLIENT_ID/SECRET in Loady's env, restart Loady backend."
  echo "Layer 2 (full restore, ~110s mechanical + backup retrieval time): restore $backup_dir into Loady's Postgres."
  echo
  echo "Database restore required:    yes, if migration commit already ran (current_state: $(state_get '.current_state'))"
  echo "Proxy rollback:                none required (identity-only cutover does not change reverse-proxy routing)"
  echo "Maintenance implications:      re-enable maintenance mode before restoring, per FINAL_PRODUCTION_ROLLBACK_RUNBOOK.md"
  echo "Verification sequence after:   Loady login (never-migrated + migrated account), history count, usage count, plan distribution - see FINAL_PRODUCTION_ROLLBACK_RUNBOOK.md"
  echo
  echo "See docs/platform/FINAL_PRODUCTION_ROLLBACK_RUNBOOK.md and ROLLBACK_TRIGGERS_AND_POINT_OF_NO_RETURN.md for full detail."
}

cmd_rollback() {
  state_init_if_missing
  local current; current="$(state_get '.current_state')"
  case "$current" in
    MIGRATED|RECONCILED|VERIFIED|ROLLBACK_REQUIRED|INTERRUPTED) : ;;
    *) die "Rollback refused: current state is '$current', which has nothing migrated to roll back. If you mean to abandon a pre-migration attempt, the kill switch alone (unset PLATFORM_CLIENT_ID) is sufficient and needs no confirmation dance." ;;
  esac
  if [[ "$DRY_RUN_ONLY" == "1" ]]; then
    echo "DRY RUN: see 'rollback-plan' for the full no-changes preview of what this would do."
    cmd_rollback_plan
    return 0
  fi
  DANGEROUS_STAGE="1"
  require_confirmation "ROLLBACK $DEPLOYMENT_ID" "rollback"

  local backup_dir; backup_dir="$(state_get '.backup_dir')"
  local needs_restore="1"
  # kill switch always runs first, regardless of restore need
  local rc=0
  [[ -n "${LOADY_ENV_FILE:-}" ]] || die "Set LOADY_ENV_FILE for the kill-switch layer."
  "$SCRIPT_DIR/rollback-platform-migration.sh" --env production --layer kill-switch --env-file "$LOADY_ENV_FILE" \
    > >(tee -a "$DEPLOY_DIR/log.txt" | redact) 2>&1 || rc=$?
  [[ $rc -eq 0 ]] || { record_stage "rollback" "failed" "kill-switch exit=$rc"; die "Kill-switch layer failed (exit $rc)."; }

  if [[ "$needs_restore" == "1" ]]; then
    local got2="$CONFIRM_ARG2"
    [[ -n "$got2" ]] || die "Database restore is required for this rollback. Re-run with --confirm-restore 'RESTORE-DATABASE $DEPLOYMENT_ID' after reviewing 'rollback-plan'."
    [[ "$got2" == "RESTORE-DATABASE $DEPLOYMENT_ID" ]] || die "Restore confirmation text did not match exactly."
    [[ -n "${BACKUP_ENCRYPTION_PASSPHRASE:-}" ]] || die "BACKUP_ENCRYPTION_PASSPHRASE required to decrypt the backup for restore."
    rc=0
    "$SCRIPT_DIR/rollback-platform-migration.sh" --env production --layer full-restore \
      --backup-dir "$backup_dir" --env-file "$LOADY_ENV_FILE" \
      > >(tee -a "$DEPLOY_DIR/log.txt" | redact) 2>&1 || rc=$?
    [[ $rc -eq 0 ]] || { record_stage "rollback" "failed" "full-restore exit=$rc"; die "Full-restore layer failed (exit $rc). Diagnostics were NOT deleted - collect-diagnostics before retrying."; }
  fi
  DANGEROUS_STAGE="0"
  record_stage "rollback" "passed" "restore=$needs_restore"
  transition "ROLLED_BACK"
  echo "Rollback complete. State: ROLLED_BACK. Run 'verify' equivalents manually per FINAL_PRODUCTION_ROLLBACK_RUNBOOK.md's post-rollback checklist."
}

cmd_collect_diagnostics() {
  state_init_if_missing
  local bundle_dir
  bundle_dir="$DEPLOY_DIR/diagnostics-$(date -u +%Y%m%dT%H%M%SZ)"
  mkdir -p "$bundle_dir"
  {
    echo "# Diagnostic bundle - $DEPLOYMENT_ID ($ENVIRONMENT)"
    echo "Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo
    echo "## State machine"
    jq '.' "$STATE_FILE"
    echo
    echo "## Git"
    echo "commit=$GIT_COMMIT branch=$GIT_BRANCH dirty=$GIT_DIRTY"
    echo
    echo "## Container states (if Docker reachable)"
    if docker_available; then
      docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}' 2>&1 | redact
    else
      echo "(Docker daemon unreachable - not collected)"
    fi
    echo
    echo "## Resource snapshot"
    df -Pm "$REPO_ROOT" 2>&1
    free -m 2>&1 || true
    echo
    echo "## Recent log tail (already redacted at write time)"
    tail -n 100 "$DEPLOY_DIR/log.txt" 2>/dev/null || echo "(no log yet)"
  } > "$bundle_dir/bundle.txt"
  (
    cd "$bundle_dir"
    if command -v sha256sum >/dev/null 2>&1; then
      sha256sum bundle.txt > CHECKSUMS.sha256
    else
      shasum -a 256 bundle.txt > CHECKSUMS.sha256
    fi
  )
  echo "Diagnostic bundle written: $bundle_dir/bundle.txt"
  echo "Never includes: .env contents, tokens, password hashes, private keys, OAuth secrets, DB passwords, raw customer data."
}

# =======================================================================
# Dispatch
# =======================================================================
acquire_lock
trap 'release_lock' EXIT

case "$COMMAND" in
  inspect)              cmd_inspect ;;
  preflight)             cmd_preflight ;;
  plan)                  cmd_plan ;;
  backup)                cmd_backup ;;
  verify-backup)         cmd_verify_backup ;;
  platform-deploy)       cmd_platform_deploy ;;
  platform-verify)       cmd_platform_verify ;;
  migration-dry-run)     cmd_migration_dry_run ;;
  cutover-check)         cmd_cutover_check ;;
  maintenance-on)        cmd_maintenance_on ;;
  migrate)               cmd_migrate ;;
  reconcile)             cmd_reconcile ;;
  verify)                cmd_verify ;;
  maintenance-off)       cmd_maintenance_off ;;
  status)                cmd_status ;;
  rollback-plan)         cmd_rollback_plan ;;
  rollback)              cmd_rollback ;;
  collect-diagnostics)   cmd_collect_diagnostics ;;
  *) die "Unknown command: $COMMAND" ;;
esac
