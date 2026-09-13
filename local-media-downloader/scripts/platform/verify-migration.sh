#!/usr/bin/env bash
# Mission 5, phase 25: post-commit reconciliation checks, automating what
# was done by hand in phase 9 - see docs/platform/PRODUCTION_REHEARSAL_PLAN.md.
# Prints PASS/FAIL per check and a final PASS/FAIL summary; exits non-zero
# on any failure. Read-only - never writes to either database.
#
# Usage: scripts/platform/verify-migration.sh --env staging|production
set -euo pipefail

ENV=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENV="${2:-}"; shift 2 ;;
    *) echo "Usage: $0 --env staging|production" >&2; exit 2 ;;
  esac
done
[[ "$ENV" == "staging" || "$ENV" == "production" ]] || { echo "Usage: $0 --env staging|production" >&2; exit 2; }

if [[ "$ENV" == "staging" ]]; then
  LOADY_PG="loady-staging-postgres-1"; LOADY_USER="loady_staging"; LOADY_DB="loady_staging"
  PLATFORM_PG="platform-core-staging-postgres-1"; PLATFORM_USER="platform_core_staging"; PLATFORM_DB="platform_core_staging"
else
  LOADY_PG="${LOADY_PG_CONTAINER:?Set LOADY_PG_CONTAINER}"; LOADY_USER="${LOADY_PG_USER:?Set LOADY_PG_USER}"; LOADY_DB="${LOADY_PG_DB:?Set LOADY_PG_DB}"
  PLATFORM_PG="${PLATFORM_PG_CONTAINER:?Set PLATFORM_PG_CONTAINER}"; PLATFORM_USER="${PLATFORM_PG_USER:?Set PLATFORM_PG_USER}"; PLATFORM_DB="${PLATFORM_PG_DB:?Set PLATFORM_PG_DB}"
fi

FAILED=0
check() {  # check "description" <expected_comparator> <query-against-loady-or-platform>
  local desc="$1" ; local value="$2"
  echo "  $desc: $value"
}

fail() {
  echo "  FAIL: $1"
  FAILED=1
}

loady_q() { docker exec "$LOADY_PG" psql -U "$LOADY_USER" -d "$LOADY_DB" -tAc "$1"; }
platform_q() { docker exec "$PLATFORM_PG" psql -U "$PLATFORM_USER" -d "$PLATFORM_DB" -tAc "$1"; }

echo "=== Migration reconciliation: $ENV ==="

TOTAL_USERS=$(loady_q "SELECT count(*) FROM users")
LINKED_USERS=$(loady_q "SELECT count(*) FROM users WHERE global_user_id IS NOT NULL")
DISTINCT_GLOBAL_IDS=$(loady_q "SELECT count(DISTINCT global_user_id) FROM users WHERE global_user_id IS NOT NULL")
check "Total Loady users" "$TOTAL_USERS"
check "Loady users linked (global_user_id set)" "$LINKED_USERS"

if [[ "$LINKED_USERS" != "$DISTINCT_GLOBAL_IDS" ]]; then
  fail "global_user_id is not unique per Loady user ($LINKED_USERS linked but only $DISTINCT_GLOBAL_IDS distinct global_user_id values) - possible duplicate local account linkage."
fi

PLATFORM_USERS=$(platform_q "SELECT count(*) FROM users")
PLATFORM_ENTITLEMENTS=$(platform_q "SELECT count(*) FROM entitlements")
PLATFORM_PAYMENTS=$(platform_q "SELECT count(*) FROM payment_records")
check "Platform Core users" "$PLATFORM_USERS"
check "Platform Core entitlements" "$PLATFORM_ENTITLEMENTS"
check "Platform Core payment_records (must be 0 - migration never creates revenue)" "$PLATFORM_PAYMENTS"

if [[ "$PLATFORM_PAYMENTS" != "0" ]]; then
  fail "payment_records is non-zero ($PLATFORM_PAYMENTS) - the migration must never create a PaymentRecord. Investigate before trusting this migration."
fi

# Every linked Loady user's global_user_id must resolve to a real Platform
# Core user - an orphaned link is exactly the "conflicted" edge case this
# mission's synthetic dataset deliberately includes (already_linked_edge).
# Plain set difference in the shell rather than a cross-database dblink
# query, so this works without any Postgres extension being installed.
LOADY_GLOBAL_IDS_FILE="$(mktemp)"
PLATFORM_USER_IDS_FILE="$(mktemp)"
trap 'rm -f "$LOADY_GLOBAL_IDS_FILE" "$PLATFORM_USER_IDS_FILE"' EXIT
loady_q "SELECT global_user_id FROM users WHERE global_user_id IS NOT NULL ORDER BY 1" > "$LOADY_GLOBAL_IDS_FILE"
platform_q "SELECT id FROM users ORDER BY 1" > "$PLATFORM_USER_IDS_FILE"
ORPHANED_IDS="$(comm -23 <(sort "$LOADY_GLOBAL_IDS_FILE") <(sort "$PLATFORM_USER_IDS_FILE"))"
ORPHANED_COUNT="$(echo -n "$ORPHANED_IDS" | grep -c . || true)"
check "Orphaned global_user_id links (Loady points at a nonexistent Platform Core user)" "$ORPHANED_COUNT"
if [[ "$ORPHANED_COUNT" -gt 0 ]]; then
  fail "$ORPHANED_COUNT Loady account(s) have a global_user_id with no matching Platform Core user: $ORPHANED_IDS"
fi

echo
if [[ "$FAILED" -eq 0 ]]; then
  echo "RECONCILIATION: PASS"
  exit 0
else
  echo "RECONCILIATION: FAIL"
  exit 1
fi
