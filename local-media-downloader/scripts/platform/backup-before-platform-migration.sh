#!/usr/bin/env bash
# Mission 5, phase 5 / phase 25: full pre-migration backup of everything
# needed to return to the pre-Platform-Core state - Loady's Postgres, its
# separate history/settings SQLite file, and Platform Core's Postgres (if
# already initialized). Writes a config/migration-version inventory
# alongside the data (never secret values), and a SHA-256 checksum manifest
# so PRODUCTION_ROLLBACK_REHEARSAL.md / verify-migration.sh can prove every
# artifact is intact before anyone trusts it as a restore point.
#
# Usage:
#   scripts/platform/backup-before-platform-migration.sh --env staging --out /path/to/backup/dir
#   scripts/platform/backup-before-platform-migration.sh --env production --out ... \
#       (refuses unless PLATFORM_MIGRATION_CONFIRM=I_UNDERSTAND_THIS_IS_PRODUCTION is set -
#        this mission never sets that variable and never runs this script in production mode)
set -euo pipefail

ENV=""
OUT_DIR=""

usage() {
  echo "Usage: $0 --env staging|production --out <backup-dir>" >&2
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENV="${2:-}"; shift 2 ;;
    --out) OUT_DIR="${2:-}"; shift 2 ;;
    *) usage ;;
  esac
done

[[ -n "$ENV" && -n "$OUT_DIR" ]] || usage
[[ "$ENV" == "staging" || "$ENV" == "production" ]] || { echo "NO-GO: --env must be 'staging' or 'production', got '$ENV'." >&2; exit 1; }

if [[ "$ENV" == "production" ]]; then
  if [[ "${PLATFORM_MIGRATION_CONFIRM:-}" != "I_UNDERSTAND_THIS_IS_PRODUCTION" ]]; then
    echo "NO-GO: refusing to back up production without PLATFORM_MIGRATION_CONFIRM=I_UNDERSTAND_THIS_IS_PRODUCTION set explicitly by the operator." >&2
    exit 1
  fi
  echo "PRODUCTION MODE - this backs up the real Loady/Platform Core production databases." >&2
  LOADY_PG_CONTAINER="${LOADY_PG_CONTAINER:?Set LOADY_PG_CONTAINER for production mode}"
  LOADY_PG_DB="${LOADY_PG_DB:?Set LOADY_PG_DB for production mode}"
  LOADY_PG_USER="${LOADY_PG_USER:?Set LOADY_PG_USER for production mode}"
  LOADY_BACKEND_CONTAINER="${LOADY_BACKEND_CONTAINER:?Set LOADY_BACKEND_CONTAINER for production mode}"
  PLATFORM_PG_CONTAINER="${PLATFORM_PG_CONTAINER:-}"
  PLATFORM_PG_DB="${PLATFORM_PG_DB:-}"
  PLATFORM_PG_USER="${PLATFORM_PG_USER:-}"
else
  LOADY_PG_CONTAINER="loady-staging-postgres-1"
  LOADY_PG_DB="loady_staging"
  LOADY_PG_USER="loady_staging"
  LOADY_BACKEND_CONTAINER="loady-staging-backend-1"
  PLATFORM_PG_CONTAINER="platform-core-staging-postgres-1"
  PLATFORM_PG_DB="platform_core_staging"
  PLATFORM_PG_USER="platform_core_staging"
fi

for c in "$LOADY_PG_CONTAINER" "$LOADY_BACKEND_CONTAINER"; do
  docker inspect -f '{{.State.Running}}' "$c" >/dev/null 2>&1 || { echo "NO-GO: container '$c' is not running." >&2; exit 1; }
done

mkdir -p "$OUT_DIR"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="$OUT_DIR/${ENV}-${TIMESTAMP}"
mkdir -p "$RUN_DIR"
echo "Writing backup to: $RUN_DIR"

echo "==> Dumping Loady Postgres ($LOADY_PG_DB)..."
docker exec "$LOADY_PG_CONTAINER" pg_dump -U "$LOADY_PG_USER" -d "$LOADY_PG_DB" -Fc -f /tmp/loady_backup.dump
docker cp "$LOADY_PG_CONTAINER:/tmp/loady_backup.dump" "$RUN_DIR/loady_postgres.dump"
docker exec "$LOADY_PG_CONTAINER" rm -f /tmp/loady_backup.dump

echo "==> Copying Loady history/settings SQLite file..."
docker cp "$LOADY_BACKEND_CONTAINER:/var/lib/loady/data/app.db" "$RUN_DIR/loady_app.db" 2>/dev/null \
  || echo "    (no app.db present yet - acceptable for a brand-new environment)"

if [[ -n "$PLATFORM_PG_CONTAINER" ]] && docker inspect -f '{{.State.Running}}' "$PLATFORM_PG_CONTAINER" >/dev/null 2>&1; then
  echo "==> Dumping Platform Core Postgres ($PLATFORM_PG_DB)..."
  docker exec "$PLATFORM_PG_CONTAINER" pg_dump -U "$PLATFORM_PG_USER" -d "$PLATFORM_PG_DB" -Fc -f /tmp/platform_backup.dump
  docker cp "$PLATFORM_PG_CONTAINER:/tmp/platform_backup.dump" "$RUN_DIR/platform_core_postgres.dump"
  docker exec "$PLATFORM_PG_CONTAINER" rm -f /tmp/platform_backup.dump
else
  echo "==> Platform Core Postgres not running/configured - skipping (not yet initialized)."
fi

echo "==> Recording migration-version inventory (no secrets)..."
{
  echo "# Migration version inventory - $TIMESTAMP ($ENV)"
  echo
  echo "## Loady (alembic)"
  docker exec "$LOADY_BACKEND_CONTAINER" python -m alembic current 2>&1 || echo "(unable to read Loady alembic version)"
  echo
  if [[ -n "$PLATFORM_PG_CONTAINER" ]] && docker inspect -f '{{.State.Running}}' "${PLATFORM_BACKEND_CONTAINER:-platform-core-staging-backend-1}" >/dev/null 2>&1; then
    echo "## Platform Core (alembic)"
    docker exec "${PLATFORM_BACKEND_CONTAINER:-platform-core-staging-backend-1}" python -m alembic current 2>&1 || echo "(unable to read Platform Core alembic version)"
  fi
} > "$RUN_DIR/migration_versions.txt"

echo "==> Recording configuration inventory (variable NAMES only - never values)..."
{
  echo "# Configuration inventory - $TIMESTAMP ($ENV)"
  echo "## Loady backend container env var names:"
  docker exec "$LOADY_BACKEND_CONTAINER" env | cut -d= -f1 | sort
  if [[ -n "${PLATFORM_BACKEND_CONTAINER:-}" ]] || docker inspect -f '{{.State.Running}}' platform-core-staging-backend-1 >/dev/null 2>&1; then
    echo "## Platform Core backend container env var names:"
    docker exec "${PLATFORM_BACKEND_CONTAINER:-platform-core-staging-backend-1}" env | cut -d= -f1 | sort
  fi
} > "$RUN_DIR/config_inventory.txt"

echo "==> Computing checksums..."
(cd "$RUN_DIR" && shasum -a 256 -- * > CHECKSUMS.sha256 2>/dev/null || sha256sum -- * > CHECKSUMS.sha256)

echo "==> Backup complete: $RUN_DIR"
cat "$RUN_DIR/CHECKSUMS.sha256"
