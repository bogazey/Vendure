#!/usr/bin/env bash
# Mission 15, Phase 25: the final cutover GO/NO-GO gate.
#
# Aggregates every category Phase 25 requires into ONE verdict: exactly
# GO or NO-GO, never an ambiguous state for a mandatory condition. Human-
# readable (plain text to stdout) and machine-readable (--json emits a
# single JSON object with a "verdict" key and a "categories" object).
#
# This gate does not reimplement checks that already exist elsewhere -
# it calls production-preflight-inspection.sh (Phase 18) and inspects
# real filesystem state for backups/rollback-readiness. Some categories
# (OAUTH redirect URI correctness against the real registered client,
# PADDLE Sandbox-parity sign-off) cannot be verified by any script this
# mission can run without live credentials/network access this
# environment does not have - those require an explicit operator
# ATTESTATION env var, set only after the operator has actually performed
# the corresponding manual check documented in this gate's own category
# description. An unset attestation is always NO-GO for that category -
# never a silent pass.
#
# Usage:
#   scripts/platform/cutover-go-no-go.sh --env production --backup-dir <dir> [--json]
#
# Required env vars (production mode) - identical set to
# production-preflight-inspection.sh, plus the ones noted per category
# below. See docs/platform/PRODUCTION_GO_NO_GO_GATE.md for the full
# category-by-category description.
set -euo pipefail

ENV=""
BACKUP_DIR=""
JSON_OUTPUT="0"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENV="${2:-}"; shift 2 ;;
    --backup-dir) BACKUP_DIR="${2:-}"; shift 2 ;;
    --json) JSON_OUTPUT="1"; shift 1 ;;
    *) echo "Usage: $0 --env staging|production --backup-dir <dir> [--json]" >&2; exit 2 ;;
  esac
done
[[ "$ENV" == "staging" || "$ENV" == "production" ]] || { echo "NO-GO: --env must be 'staging' or 'production'." >&2; exit 1; }
[[ -n "$BACKUP_DIR" ]] || { echo "NO-GO: --backup-dir is required." >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

declare -A CATEGORY_STATUS
declare -A CATEGORY_REASON

set_result() {
  local category="$1" status="$2" reason="${3:-}"
  CATEGORY_STATUS["$category"]="$status"
  CATEGORY_REASON["$category"]="$reason"
}

# --- HOST, DATABASE, SECRETS (partial), PLATFORM, LOADY: delegate to the
# Phase 18 read-only inspection, which already covers Docker/Compose
# versions, disk/RAM/swap/load, container health, volume names, DB
# connectivity, record-count sanity, and signing-key/TLS file presence.
if PREFLIGHT_OUTPUT="$(bash "$SCRIPT_DIR/production-preflight-inspection.sh" --env "$ENV" 2>&1)"; then
  set_result "HOST" "GO" ""
  set_result "DATABASE" "GO" ""
  set_result "PLATFORM" "GO" ""
  set_result "LOADY" "GO" ""
  set_result "SECRETS" "GO" "(signing key + TLS file presence/permissions only - see PRODUCTION_SECRET_STORAGE_PLAN.md for what this does not cover)"
else
  REASON="$(grep -A100 "^NO-GO:" <<<"$PREFLIGHT_OUTPUT" | tail -n +2 | sed 's/^/    /')"
  set_result "HOST" "NO-GO" "production-preflight-inspection.sh reported NO-GO:
$REASON"
  set_result "DATABASE" "NO-GO" "see HOST category"
  set_result "PLATFORM" "NO-GO" "see HOST category"
  set_result "LOADY" "NO-GO" "see HOST category"
  set_result "SECRETS" "NO-GO" "see HOST category"
fi

# --- RESOURCE CAPACITY: same underlying script covers disk/RAM/swap/load
# already folded into HOST above; kept as its own category per Phase 25's
# explicit list, referencing the same evidence rather than re-running it.
CATEGORY_STATUS["RESOURCE CAPACITY"]="${CATEGORY_STATUS[HOST]}"
CATEGORY_REASON["RESOURCE CAPACITY"]="Same evidence as HOST (disk/RAM/swap/load are inspected together) - see PRODUCTION_RESOURCE_BUDGET.md for the thresholds used."

# --- BACKUPS: a backup for this environment must exist, be recent (last
# 24 hours), and have a checksum manifest present (never assume success
# from a directory merely existing).
LATEST_BACKUP="$(find "$BACKUP_DIR" -maxdepth 1 -mindepth 1 -type d -name "${ENV}-*" 2>/dev/null | sort | tail -n1)"
if [[ -z "$LATEST_BACKUP" ]]; then
  set_result "BACKUPS" "NO-GO" "No backup found under $BACKUP_DIR for env '$ENV'."
elif [[ ! -f "$LATEST_BACKUP/CHECKSUMS.sha256" ]]; then
  set_result "BACKUPS" "NO-GO" "Latest backup ($LATEST_BACKUP) has no CHECKSUMS.sha256 - never trust an unchecksummed backup."
else
  BACKUP_AGE_SECONDS=$(( $(date +%s) - $(stat -c %Y "$LATEST_BACKUP" 2>/dev/null || echo 0) ))
  if (( BACKUP_AGE_SECONDS > 86400 )); then
    set_result "BACKUPS" "NO-GO" "Latest backup ($LATEST_BACKUP) is more than 24 hours old ($((BACKUP_AGE_SECONDS / 3600))h) - take a fresh one before cutover."
  else
    set_result "BACKUPS" "GO" "Latest backup: $LATEST_BACKUP (age: $((BACKUP_AGE_SECONDS / 60)) min)"
  fi
fi

# --- ROLLBACK READINESS: the rollback script must exist, be executable,
# and a backup (checked above) must exist for it to restore from.
ROLLBACK_SCRIPT="$SCRIPT_DIR/rollback-platform-migration.sh"
if [[ ! -x "$ROLLBACK_SCRIPT" ]]; then
  set_result "ROLLBACK READINESS" "NO-GO" "$ROLLBACK_SCRIPT missing or not executable."
elif [[ "${CATEGORY_STATUS[BACKUPS]}" != "GO" ]]; then
  set_result "ROLLBACK READINESS" "NO-GO" "No valid backup to roll back to (see BACKUPS)."
else
  set_result "ROLLBACK READINESS" "GO" "Rollback script present and executable; a valid backup exists to restore from."
fi

# --- MIGRATION: requires an explicit attestation that today's dry run
# (Phase 24 procedure) was reviewed and showed failed=0 and conflicted=0
# (or every conflict individually resolved). This cannot be verified by
# this script without access to the real dry-run report file, which the
# operator names explicitly.
if [[ -n "${MIGRATION_DRY_RUN_REPORT_PATH:-}" ]]; then
  if [[ -f "$MIGRATION_DRY_RUN_REPORT_PATH" ]] && grep -q "failed=0" "$MIGRATION_DRY_RUN_REPORT_PATH" && grep -q "conflicted=0" "$MIGRATION_DRY_RUN_REPORT_PATH"; then
    set_result "MIGRATION" "GO" "Dry-run report at $MIGRATION_DRY_RUN_REPORT_PATH shows failed=0 conflicted=0."
  else
    set_result "MIGRATION" "NO-GO" "Dry-run report at $MIGRATION_DRY_RUN_REPORT_PATH does not show failed=0 conflicted=0 (or file missing) - see FINAL_MIGRATION_DRY_RUN_PROCEDURE.md."
  fi
else
  set_result "MIGRATION" "NO-GO" "MIGRATION_DRY_RUN_REPORT_PATH not set - run today's dry run first and point this gate at its saved report."
fi

# --- OAUTH: cannot be verified without a live call to Platform Core's
# registered client record; requires an explicit operator attestation.
if [[ "${OAUTH_REDIRECT_URI_VERIFIED:-}" == "yes" ]]; then
  set_result "OAUTH" "GO" "Operator attested OAUTH_REDIRECT_URI_VERIFIED=yes (Loady's registered redirect_uri manually confirmed against production)."
else
  set_result "OAUTH" "NO-GO" "Set OAUTH_REDIRECT_URI_VERIFIED=yes only after manually confirming the registered Loady OAuth client's redirect_uri matches production - see PRODUCTION_DEPLOYMENT_SEQUENCING.md step 7."
fi

# --- PADDLE: not part of this identity cutover's authoritative path
# (checkout/webhooks stay on Loady's side per Decision #6) - N/A unless
# the separate billing cutover (BILLING_CUTOVER_RUNBOOK.md) is also in
# scope for this run, signaled by an explicit env var.
if [[ "${BILLING_CUTOVER_IN_SCOPE:-no}" == "no" ]]; then
  set_result "PADDLE" "N/A" "Billing cutover is a separate, later effort (BILLING_CUTOVER_RUNBOOK.md) - not part of this identity-migration cutover."
elif [[ "${PADDLE_SANDBOX_PARITY_VERIFIED:-}" == "yes" ]]; then
  set_result "PADDLE" "GO" "Operator attested Sandbox parity per BILLING_CUTOVER_RUNBOOK.md Stage 2b."
else
  set_result "PADDLE" "NO-GO" "BILLING_CUTOVER_IN_SCOPE=yes but PADDLE_SANDBOX_PARITY_VERIFIED is not 'yes'."
fi

OVERALL="GO"
for category in "${!CATEGORY_STATUS[@]}"; do
  if [[ "${CATEGORY_STATUS[$category]}" == "NO-GO" ]]; then
    OVERALL="NO-GO"
  fi
done

if [[ "$JSON_OUTPUT" == "1" ]]; then
  printf '{\n  "overall": "%s",\n  "categories": {\n' "$OVERALL"
  first=1
  for category in "HOST" "DATABASE" "PLATFORM" "LOADY" "SECRETS" "RESOURCE CAPACITY" "BACKUPS" "ROLLBACK READINESS" "MIGRATION" "OAUTH" "PADDLE"; do
    [[ $first -eq 0 ]] && printf ',\n'
    first=0
    ESCAPED_REASON="$(printf '%s' "${CATEGORY_REASON[$category]}" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')"
    printf '    "%s": {"status": "%s", "reason": %s}' "$category" "${CATEGORY_STATUS[$category]}" "$ESCAPED_REASON"
  done
  printf '\n  }\n}\n'
else
  echo "=== Cutover GO/NO-GO Gate (env: $ENV) ==="
  for category in "HOST" "DATABASE" "PLATFORM" "LOADY" "SECRETS" "RESOURCE CAPACITY" "BACKUPS" "ROLLBACK READINESS" "MIGRATION" "OAUTH" "PADDLE"; do
    printf "%-20s %s\n" "$category:" "${CATEGORY_STATUS[$category]}"
    [[ -n "${CATEGORY_REASON[$category]}" ]] && echo "    ${CATEGORY_REASON[$category]}"
  done
  echo
  echo "OVERALL: $OVERALL"
fi

[[ "$OVERALL" == "GO" ]]
