#!/usr/bin/env bash
# Mission 5, phase 26: single GO/NO-GO preflight. Prints exactly one of:
#   GO
# or
#   NO-GO:
#   <reasons, one per line>
# Never both, never neither - see docs/platform/PRODUCTION_GO_NO_GO.md.
#
# Usage: scripts/platform/preflight-production-migration.sh --env staging|production
#
# Staging mode checks the actual loady-staging/platform-core-staging
# containers on this machine. Production mode checks the equivalent real
# containers/URLs, supplied via env vars (never hardcoded) - this mission
# only ever runs the staging mode; production mode is written for a real
# operator to use later, not executed here.
set -euo pipefail

ENV=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENV="${2:-}"; shift 2 ;;
    *) echo "Usage: $0 --env staging|production" >&2; exit 2 ;;
  esac
done
[[ "$ENV" == "staging" || "$ENV" == "production" ]] || { echo "Usage: $0 --env staging|production" >&2; exit 2; }

REASONS=()
check() {  # check "description" <command...>
  local desc="$1"; shift
  if ! "$@" >/dev/null 2>&1; then
    REASONS+=("$desc")
  fi
}

if [[ "$ENV" == "staging" ]]; then
  LOADY_BACKEND="loady-staging-backend-1"
  LOADY_HEALTH_URL="http://localhost:8090/api/health"
  PLATFORM_READY_URL="https://localhost:8443/ready"
  PLATFORM_BACKEND="platform-core-staging-backend-1"
  EXPECTED_BRANCH="unified-platform-v1"
else
  LOADY_BACKEND="${LOADY_BACKEND_CONTAINER:?Set LOADY_BACKEND_CONTAINER for production mode}"
  LOADY_HEALTH_URL="${LOADY_HEALTH_URL:?Set LOADY_HEALTH_URL for production mode}"
  PLATFORM_READY_URL="${PLATFORM_READY_URL:?Set PLATFORM_READY_URL for production mode}"
  PLATFORM_BACKEND="${PLATFORM_BACKEND_CONTAINER:?Set PLATFORM_BACKEND_CONTAINER for production mode}"
  EXPECTED_BRANCH="${EXPECTED_BRANCH:?Set EXPECTED_BRANCH for production mode}"
fi

# 1. Git: expected branch, clean working tree.
ACTUAL_BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")"
[[ "$ACTUAL_BRANCH" == "$EXPECTED_BRANCH" ]] || REASONS+=("Not on expected branch '$EXPECTED_BRANCH' (currently '$ACTUAL_BRANCH').")
if ! git diff --quiet || ! git diff --cached --quiet; then
  REASONS+=("Working tree is not clean - uncommitted changes present.")
fi

# 2. Docker available.
check "Docker daemon is not reachable." docker info

# 3. Disk space (require at least 5 GiB free on the filesystem holding Docker data).
AVAIL_KB="$(df -Pk / | tail -1 | awk '{print $4}')"
if [[ -n "$AVAIL_KB" ]] && (( AVAIL_KB < 5 * 1024 * 1024 )); then
  REASONS+=("Less than 5 GiB free disk space (${AVAIL_KB}KB available).")
fi

# 4. Containers running and healthy.
for c in "$LOADY_BACKEND" "$PLATFORM_BACKEND"; do
  STATUS="$(docker inspect -f '{{.State.Health.Status}}' "$c" 2>/dev/null || echo "missing")"
  if [[ "$STATUS" != "healthy" ]]; then
    REASONS+=("Container '$c' is not healthy (status: $STATUS).")
  fi
done

# 5. Loady health / Platform Core readiness endpoints.
check "Loady health endpoint ($LOADY_HEALTH_URL) did not return success." curl -fsS "$LOADY_HEALTH_URL"
check "Platform Core readiness endpoint ($PLATFORM_READY_URL) did not return success." curl -fsSk "$PLATFORM_READY_URL"

# 6. Signing key + encryption key configured (Platform Core readiness already
#    reports signing_key; token encryption key presence is checked via env
#    var name only, never its value).
READY_JSON="$(curl -fsSk "$PLATFORM_READY_URL" 2>/dev/null || echo '{}')"
if ! echo "$READY_JSON" | grep -q '"signing_key":true'; then
  REASONS+=("Platform Core readiness does not report signing_key:true.")
fi
if ! docker exec "$LOADY_BACKEND" printenv PLATFORM_TOKEN_ENCRYPTION_KEY >/dev/null 2>&1; then
  REASONS+=("PLATFORM_TOKEN_ENCRYPTION_KEY is not set on $LOADY_BACKEND.")
fi

# 7. Required OAuth client exists (Loady's own platform-auth status endpoint
#    reports this without needing any credentials).
STATUS_JSON="$(curl -fsS "${LOADY_HEALTH_URL%/api/health}/api/auth/platform/status" 2>/dev/null || echo '{}')"
if ! echo "$STATUS_JSON" | grep -q '"enabled":true'; then
  REASONS+=("Loady reports Platform Core integration not enabled (missing/invalid PLATFORM_CLIENT_ID).")
fi

# 8. No unexpected failed Alembic migrations (both sides on their head revision).
for pair in "$LOADY_BACKEND" "$PLATFORM_BACKEND"; do
  OUT="$(docker exec "$pair" python -m alembic current 2>&1 || true)"
  if ! echo "$OUT" | grep -q "(head)"; then
    REASONS+=("$pair is not at its alembic head revision (or alembic check failed): $OUT")
  fi
done

# 9. Backup destination reachable (staging: local rehearsal-artifacts dir;
#    production: operator-supplied, must already exist and be writable).
BACKUP_DEST="${BACKUP_DEST:-docs/platform/rehearsal-artifacts/backups}"
if [[ ! -d "$BACKUP_DEST" ]] || [[ ! -w "$BACKUP_DEST" ]]; then
  REASONS+=("Backup destination '$BACKUP_DEST' does not exist or is not writable.")
fi

if [[ ${#REASONS[@]} -eq 0 ]]; then
  echo "GO"
  exit 0
else
  echo "NO-GO:"
  for r in "${REASONS[@]}"; do
    echo "  - $r"
  done
  exit 1
fi
