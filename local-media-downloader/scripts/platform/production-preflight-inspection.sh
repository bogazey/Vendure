#!/usr/bin/env bash
# Mission 15, Phase 18: read-only production preflight inspection.
#
# Distinct from, and runs BEFORE, scripts/platform/preflight-production-migration.sh:
# that script asks "is the already-running Platform Core + Loady stack
# healthy enough to run the identity migration right now" - this script
# asks the earlier, broader question "is this HOST fit to run the combined
# stack at all" (Docker/Compose versions, disk/RAM/swap/load, volumes,
# container health, DB connectivity, basic record-count sanity, required
# file presence/permissions). Run this one first; a NO-GO here means don't
# even attempt to bring the stack up, let alone migrate anything.
#
# READ-ONLY, always. This script MUST NEVER:
#   - modify any service, container, volume, or file
#   - restart/stop/start any container
#   - print the CONTENTS of any env file, secret, password hash, or token
#   - run a database migration
# It only inspects state and prints a GO/NO-GO verdict with reasons.
#
# Usage:
#   scripts/platform/production-preflight-inspection.sh --env staging
#   scripts/platform/production-preflight-inspection.sh --env production
#       (requires LOADY_PG_CONTAINER, LOADY_BACKEND_CONTAINER,
#        PLATFORM_PG_CONTAINER, PLATFORM_BACKEND_CONTAINER,
#        REVERSE_PROXY_CONTAINER, SIGNING_KEY_PATH, TLS_DIR env vars - all
#        :?-mandatory, exactly like preflight-production-migration.sh's own
#        convention, so there is no silently-guessed production value)
set -euo pipefail

ENV=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENV="${2:-}"; shift 2 ;;
    *) echo "Usage: $0 --env staging|production" >&2; exit 2 ;;
  esac
done
[[ "$ENV" == "staging" || "$ENV" == "production" ]] || { echo "NO-GO: --env must be 'staging' or 'production'." >&2; exit 1; }

REASONS=()
fail() { REASONS+=("$1"); }

if [[ "$ENV" == "production" ]]; then
  LOADY_PG_CONTAINER="${LOADY_PG_CONTAINER:?Set LOADY_PG_CONTAINER}"
  LOADY_BACKEND_CONTAINER="${LOADY_BACKEND_CONTAINER:?Set LOADY_BACKEND_CONTAINER}"
  PLATFORM_PG_CONTAINER="${PLATFORM_PG_CONTAINER:?Set PLATFORM_PG_CONTAINER}"
  PLATFORM_BACKEND_CONTAINER="${PLATFORM_BACKEND_CONTAINER:?Set PLATFORM_BACKEND_CONTAINER}"
  REVERSE_PROXY_CONTAINER="${REVERSE_PROXY_CONTAINER:?Set REVERSE_PROXY_CONTAINER}"
  SIGNING_KEY_PATH="${SIGNING_KEY_PATH:?Set SIGNING_KEY_PATH}"
  TLS_DIR="${TLS_DIR:?Set TLS_DIR}"
  EXPECTED_VOLUMES=(loady-rc_app-data loady-rc_media-data loady-rc_postgres-data loady-rc_platform-postgres-data)
  MIN_FREE_DISK_MB=$((5 * 1024))
  MIN_FREE_RAM_MB=$((2 * 1024))
else
  LOADY_PG_CONTAINER="loady-staging-postgres-1"
  LOADY_BACKEND_CONTAINER="loady-staging-backend-1"
  PLATFORM_PG_CONTAINER="platform-core-staging-postgres-1"
  PLATFORM_BACKEND_CONTAINER="platform-core-staging-backend-1"
  REVERSE_PROXY_CONTAINER="loady-staging-reverse-proxy-1"
  SIGNING_KEY_PATH="${SIGNING_KEY_PATH:-./platform-core/secrets/staging-signing-key.pem}"
  TLS_DIR="${TLS_DIR:-./secrets/tls}"
  EXPECTED_VOLUMES=()
  MIN_FREE_DISK_MB=$((1 * 1024))
  MIN_FREE_RAM_MB=$((512))
fi

echo "==> [1/10] Docker / Compose versions"
if ! command -v docker >/dev/null 2>&1; then
  fail "docker CLI not found on PATH."
else
  DOCKER_VERSION="$(docker version --format '{{.Server.Version}}' 2>/dev/null || echo "unreachable")"
  echo "    Docker server version: $DOCKER_VERSION"
  [[ "$DOCKER_VERSION" == "unreachable" ]] && fail "Docker daemon unreachable."
  COMPOSE_VERSION="$(docker compose version --short 2>/dev/null || echo "unavailable")"
  echo "    Compose version: $COMPOSE_VERSION"
  [[ "$COMPOSE_VERSION" == "unavailable" ]] && fail "docker compose plugin not available."
fi

echo "==> [2/10] Disk / RAM / swap / load"
AVAILABLE_DISK_MB="$(df -Pm / | awk 'NR==2 {print $4}')"
echo "    Free disk on /: ${AVAILABLE_DISK_MB} MiB (floor: ${MIN_FREE_DISK_MB} MiB)"
(( AVAILABLE_DISK_MB < MIN_FREE_DISK_MB )) && fail "Free disk ${AVAILABLE_DISK_MB}MiB below floor ${MIN_FREE_DISK_MB}MiB."

if command -v free >/dev/null 2>&1; then
  AVAILABLE_RAM_MB="$(free -m | awk '/^Mem:/ {print $7}')"
  SWAP_USED_MB="$(free -m | awk '/^Swap:/ {print $3}')"
  echo "    Available RAM: ${AVAILABLE_RAM_MB} MiB (floor: ${MIN_FREE_RAM_MB} MiB); swap used: ${SWAP_USED_MB} MiB"
  [[ -n "$AVAILABLE_RAM_MB" ]] && (( AVAILABLE_RAM_MB < MIN_FREE_RAM_MB )) && fail "Available RAM ${AVAILABLE_RAM_MB}MiB below floor ${MIN_FREE_RAM_MB}MiB."
  [[ -n "$SWAP_USED_MB" ]] && (( SWAP_USED_MB > 0 )) && fail "Active swap usage (${SWAP_USED_MB}MiB) detected - host has no real memory margin."
else
  fail "'free' command not available - cannot verify RAM/swap headroom."
fi

if [[ -r /proc/loadavg ]]; then
  LOAD_1MIN="$(awk '{print $1}' /proc/loadavg)"
  NPROC="$(nproc 2>/dev/null || echo 1)"
  echo "    1-minute load average: $LOAD_1MIN (host reports $NPROC CPU(s))"
  if awk -v l="$LOAD_1MIN" -v n="$NPROC" 'BEGIN{exit !(l >= n)}'; then
    fail "1-minute load average ($LOAD_1MIN) is at or above CPU count ($NPROC) - host already busy."
  fi
else
  fail "/proc/loadavg not readable - cannot verify load average."
fi

echo "==> [3/10] Container health"
for c in "$LOADY_PG_CONTAINER" "$LOADY_BACKEND_CONTAINER" "$PLATFORM_PG_CONTAINER" "$PLATFORM_BACKEND_CONTAINER" "$REVERSE_PROXY_CONTAINER"; do
  STATUS="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$c" 2>/dev/null || echo "missing")"
  echo "    $c: $STATUS"
  [[ "$STATUS" == "healthy" || "$STATUS" == "running" ]] || fail "Container '$c' is not healthy/running (status: $STATUS)."
done

echo "==> [4/10] Volume names"
if [[ ${#EXPECTED_VOLUMES[@]} -gt 0 ]]; then
  EXISTING_VOLUMES="$(docker volume ls --format '{{.Name}}' 2>/dev/null || echo "")"
  for v in "${EXPECTED_VOLUMES[@]}"; do
    if grep -qx "$v" <<<"$EXISTING_VOLUMES"; then
      echo "    $v: present"
    else
      fail "Expected volume '$v' not found."
    fi
  done
else
  echo "    (skipped - no fixed volume-name convention for staging)"
fi

echo "==> [5/10] Database connectivity (pg_isready only - no query beyond a plain SELECT count)"
for pair in "$LOADY_PG_CONTAINER|Loady" "$PLATFORM_PG_CONTAINER|Platform Core"; do
  container="${pair%%|*}"; label="${pair##*|}"
  if docker exec "$container" pg_isready >/dev/null 2>&1; then
    echo "    $label Postgres ($container): ready"
  else
    fail "$label Postgres ($container) is not ready."
  fi
done

echo "==> [6/10] Record-count sanity (counts only - never row contents, never hashes/tokens)"
loady_count() { docker exec "$LOADY_PG_CONTAINER" psql -tAc "SELECT count(*) FROM $1;" 2>/dev/null | tr -d '[:space:]'; }
platform_count() { docker exec "$PLATFORM_PG_CONTAINER" psql -tAc "SELECT count(*) FROM $1;" 2>/dev/null | tr -d '[:space:]'; }
LOADY_USERS="$(loady_count users || echo "")"
PLATFORM_USERS="$(platform_count users || echo "")"
echo "    Loady users: ${LOADY_USERS:-unavailable}; Platform Core users: ${PLATFORM_USERS:-unavailable}"
[[ -z "$LOADY_USERS" ]] && fail "Could not read Loady users count."
[[ -z "$PLATFORM_USERS" ]] && fail "Could not read Platform Core users count."

echo "==> [7/10] Required file presence + permissions (paths and modes only - never contents)"
if [[ -f "$SIGNING_KEY_PATH" ]]; then
  MODE="$(stat -c '%a' "$SIGNING_KEY_PATH" 2>/dev/null || echo "unknown")"
  echo "    Signing key present, mode: $MODE"
  [[ "$MODE" == "600" ]] || fail "Signing key '$SIGNING_KEY_PATH' is not mode 600 (found: $MODE)."
else
  fail "Signing key not found at '$SIGNING_KEY_PATH'."
fi

for f in "$TLS_DIR/fullchain.pem" "$TLS_DIR/privkey.pem"; do
  if [[ -f "$f" ]]; then
    echo "    TLS file present: $f"
  else
    fail "TLS file missing: $f"
  fi
done

echo "==> [8/10] Alembic head (both services)"
for pair in "$LOADY_BACKEND_CONTAINER|Loady" "$PLATFORM_BACKEND_CONTAINER|Platform Core"; do
  container="${pair%%|*}"; label="${pair##*|}"
  CURRENT="$(docker exec "$container" python -m alembic current 2>&1 || echo "unavailable")"
  echo "    $label alembic current: $CURRENT"
  [[ "$CURRENT" == *"(head)"* ]] || fail "$label is not at its Alembic head revision."
done

echo "==> [9/10] Docker Compose config validity (structural parse only, no daemon call beyond what's already been made above)"
echo "    (assumed already validated separately via 'docker compose config' - see PRODUCTION_COMPOSE_VALIDATION.md; not re-run here to avoid requiring the real .env files on this invocation)"

echo "==> [10/10] Verdict"
if [[ ${#REASONS[@]} -eq 0 ]]; then
  echo "GO"
  exit 0
else
  echo "NO-GO:"
  for r in "${REASONS[@]}"; do echo "  - $r"; done
  exit 1
fi
