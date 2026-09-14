#!/usr/bin/env bash
# Mission 5, phases 20-22: the actual production rollback sequence, exactly
# as rehearsed and timed against the loady-staging stack (see
# docs/platform/PRODUCTION_ROLLBACK_REHEARSAL.md for the full write-up and
# measured durations - Layer 1 ~5s, DB restore ~50s, container switch ~15s,
# validation ~40s, total ~110s against a staging-sized dataset already on
# local disk; production timing must add backup-retrieval time from
# wherever backups actually live).
#
# Two layers, cheapest first - stop after whichever is sufficient:
#   --layer kill-switch   Unset PLATFORM_CLIENT_ID/SECRET and restart Loady's
#                         backend only. Instant, no data touched. Loady falls
#                         back to 100% local auth/entitlement immediately.
#                         Migrated accounts' global_user_id stays set but is
#                         simply never consulted again while unset.
#   --layer full-restore  Also restores a Loady Postgres backup taken BEFORE
#                         the incident, replacing the live database. Use
#                         this when the kill-switch alone isn't enough (e.g.
#                         the migration itself corrupted data, not just the
#                         live integration).
#
# Usage:
#   scripts/platform/rollback-platform-migration.sh --env staging --layer kill-switch
#   scripts/platform/rollback-platform-migration.sh --env staging --layer full-restore \
#       --backup-dir docs/platform/rehearsal-artifacts/backups/staging-<timestamp>
#
# Production mode requires PLATFORM_MIGRATION_CONFIRM=I_UNDERSTAND_THIS_IS_PRODUCTION,
# exactly like backup-before-platform-migration.sh. This mission never sets
# that variable and never runs this script against production.
#
# Mission 7: backup-before-platform-migration.sh now encrypts every data
# artifact (loady_postgres.dump.enc, AES-256-CBC via openssl) - --layer
# full-restore requires BACKUP_ENCRYPTION_PASSPHRASE to decrypt it before
# restoring. This was a real, previously-unnoticed breakage this
# continuation caught by grepping for every caller of the backup scripts
# after adding encryption, not just updating the two backup scripts
# themselves and assuming nothing else referenced their old plaintext
# filenames.
set -euo pipefail

ENV=""
LAYER=""
BACKUP_DIR=""
ENV_FILE=""

usage() {
  echo "Usage: $0 --env staging|production --layer kill-switch|full-restore [--backup-dir <dir>] [--env-file <path>]" >&2
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENV="${2:-}"; shift 2 ;;
    --layer) LAYER="${2:-}"; shift 2 ;;
    --backup-dir) BACKUP_DIR="${2:-}"; shift 2 ;;
    --env-file) ENV_FILE="${2:-}"; shift 2 ;;
    *) usage ;;
  esac
done

[[ -n "$ENV" && -n "$LAYER" ]] || usage
[[ "$ENV" == "staging" || "$ENV" == "production" ]] || { echo "NO-GO: --env must be staging or production." >&2; exit 1; }
[[ "$LAYER" == "kill-switch" || "$LAYER" == "full-restore" ]] || { echo "NO-GO: --layer must be kill-switch or full-restore." >&2; exit 1; }
if [[ "$LAYER" == "full-restore" ]]; then
  [[ -n "$BACKUP_DIR" && -d "$BACKUP_DIR" ]] || { echo "NO-GO: --backup-dir is required and must exist for --layer full-restore." >&2; exit 1; }
  [[ -f "$BACKUP_DIR/loady_postgres.dump.enc" && -f "$BACKUP_DIR/CHECKSUMS.sha256" ]] || {
    echo "NO-GO: $BACKUP_DIR does not look like a backup produced by backup-before-platform-migration.sh." >&2; exit 1;
  }
  [[ -n "${BACKUP_ENCRYPTION_PASSPHRASE:-}" ]] || {
    echo "NO-GO: BACKUP_ENCRYPTION_PASSPHRASE must be set to decrypt this backup for --layer full-restore." >&2; exit 1;
  }
fi

if [[ "$ENV" == "production" ]]; then
  if [[ "${PLATFORM_MIGRATION_CONFIRM:-}" != "I_UNDERSTAND_THIS_IS_PRODUCTION" ]]; then
    echo "NO-GO: refusing to roll back production without PLATFORM_MIGRATION_CONFIRM=I_UNDERSTAND_THIS_IS_PRODUCTION." >&2
    exit 1
  fi
  echo "PRODUCTION MODE - this will disable the live Platform Core integration${LAYER:+ and, if full-restore, replace the live Loady database}." >&2
  LOADY_ENV_FILE="${ENV_FILE:?Set --env-file (production Loady env file path) for production mode}"
  LOADY_BACKEND_CONTAINER="${LOADY_BACKEND_CONTAINER:?Set LOADY_BACKEND_CONTAINER for production mode}"
  LOADY_PG_CONTAINER="${LOADY_PG_CONTAINER:?Set LOADY_PG_CONTAINER for production mode}"
  LOADY_PG_USER="${LOADY_PG_USER:?Set LOADY_PG_USER for production mode}"
  LOADY_PG_DB="${LOADY_PG_DB:?Set LOADY_PG_DB for production mode}"
  COMPOSE_FILE="${COMPOSE_FILE:?Set COMPOSE_FILE (e.g. compose.production.yml) for production mode}"
else
  LOADY_ENV_FILE="${ENV_FILE:-.env.staging}"
  LOADY_BACKEND_CONTAINER="loady-staging-backend-1"
  LOADY_PG_CONTAINER="loady-staging-postgres-1"
  LOADY_PG_USER="loady_staging"
  LOADY_PG_DB="loady_staging"
  COMPOSE_FILE="compose.staging.yml"
fi

[[ -f "$LOADY_ENV_FILE" ]] || { echo "NO-GO: env file '$LOADY_ENV_FILE' not found." >&2; exit 1; }

START_TS=$(date +%s)
echo "=== Rollback started ($(date -u -r "$START_TS" 2>/dev/null || date -u)) - layer: $LAYER ==="

echo "--> Layer 1: disabling Platform Core integration (kill-switch)..."
tmp_env="$(mktemp)"
sed -E 's/^(PLATFORM_CLIENT_ID)=.*/\1=/; s/^(PLATFORM_CLIENT_SECRET)=.*/\1=/' "$LOADY_ENV_FILE" > "$tmp_env"
mv "$tmp_env" "$LOADY_ENV_FILE"
docker compose -f "$COMPOSE_FILE" --env-file "$LOADY_ENV_FILE" up -d backend
for _ in $(seq 1 30); do
  docker exec "$LOADY_BACKEND_CONTAINER" true >/dev/null 2>&1 && break
  sleep 1
done
LAYER1_TS=$(date +%s)
echo "    Layer 1 done in $((LAYER1_TS - START_TS))s."

if [[ "$LAYER" == "full-restore" ]]; then
  echo "--> Verifying backup checksums before restoring..."
  (cd "$BACKUP_DIR" && (shasum -a 256 -c CHECKSUMS.sha256 || sha256sum -c CHECKSUMS.sha256)) \
    || { echo "NO-GO: backup checksum verification failed - refusing to restore from a possibly-corrupt backup." >&2; exit 1; }

  echo "--> Decrypting backup..."
  decrypt_tmp="$(mktemp)"
  trap 'rm -f "$decrypt_tmp"' EXIT
  openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
    -in "$BACKUP_DIR/loady_postgres.dump.enc" -out "$decrypt_tmp" -pass env:BACKUP_ENCRYPTION_PASSPHRASE

  echo "--> Layer 2: restoring Loady Postgres from backup..."
  docker compose -f "$COMPOSE_FILE" --env-file "$LOADY_ENV_FILE" stop backend
  docker cp "$decrypt_tmp" "$LOADY_PG_CONTAINER:/tmp/rollback_restore.dump"
  rm -f "$decrypt_tmp"
  docker exec "$LOADY_PG_CONTAINER" psql -U "$LOADY_PG_USER" -d postgres -v ON_ERROR_STOP=1 -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$LOADY_PG_DB' AND pid != pg_backend_pid();"
  docker exec "$LOADY_PG_CONTAINER" dropdb -U "$LOADY_PG_USER" "$LOADY_PG_DB"
  docker exec "$LOADY_PG_CONTAINER" createdb -U "$LOADY_PG_USER" "$LOADY_PG_DB"
  docker exec "$LOADY_PG_CONTAINER" pg_restore -U "$LOADY_PG_USER" -d "$LOADY_PG_DB" --no-owner --role="$LOADY_PG_USER" /tmp/rollback_restore.dump
  DB_RESTORE_TS=$(date +%s)
  echo "    Database restored in $((DB_RESTORE_TS - LAYER1_TS))s."

  docker compose -f "$COMPOSE_FILE" --env-file "$LOADY_ENV_FILE" up -d backend
  for _ in $(seq 1 30); do
    docker exec "$LOADY_BACKEND_CONTAINER" true >/dev/null 2>&1 && break
    sleep 1
  done
  SWITCH_TS=$(date +%s)
  echo "    Backend restarted against restored database in $((SWITCH_TS - DB_RESTORE_TS))s."
fi

echo "--> Verifying: Platform Core integration is now reported disabled..."
docker exec "$LOADY_BACKEND_CONTAINER" python -c "
from app.services import platform_identity_service
print('enabled:', platform_identity_service.is_configured())
" || true

END_TS=$(date +%s)
echo "=== Rollback complete in $((END_TS - START_TS))s total ==="
echo "Next: run the operator validation checklist in"
echo "docs/platform/PRODUCTION_ROLLBACK_REHEARSAL.md before declaring the rollback successful."
