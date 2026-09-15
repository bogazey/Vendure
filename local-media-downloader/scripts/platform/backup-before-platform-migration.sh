#!/usr/bin/env bash
# Mission 5, phase 5 / phase 25: full pre-migration backup of everything
# needed to return to the pre-Platform-Core state - Loady's Postgres, its
# separate history/settings SQLite file, and Platform Core's Postgres (if
# already initialized). Writes a config/migration-version inventory
# alongside the data (never secret values), and a SHA-256 checksum manifest
# so PRODUCTION_ROLLBACK_REHEARSAL.md / verify-migration.sh can prove every
# artifact is intact before anyone trusts it as a restore point.
#
# Mission 7: closes the encryption-at-rest / off-site / file-permission
# gaps PLATFORM_BACKUP_RESTORE.md documented as "not yet implemented
# anywhere" since Mission 4. Every backup artifact is now encrypted with
# `openssl enc` (AES-256-CBC, PBKDF2) before its plaintext is deleted -
# `age`/GPG were the doc's original suggestions but neither is installed
# on this machine; openssl is already present everywhere and gives the
# same encryption-at-rest property. BACKUP_ENCRYPTION_PASSPHRASE is
# REQUIRED (fails closed, no plaintext-fallback mode) in both staging and
# production - there is no principled reason a "staging" backup should be
# allowed to sit unencrypted when a "production" one isn't.
#
# Usage:
#   BACKUP_ENCRYPTION_PASSPHRASE=... scripts/platform/backup-before-platform-migration.sh \
#       --env staging --out /path/to/backup/dir [--retention-days N] [--offsite]
#   scripts/platform/backup-before-platform-migration.sh --env production --out ... \
#       (refuses unless PLATFORM_MIGRATION_CONFIRM=I_UNDERSTAND_THIS_IS_PRODUCTION is set -
#        this mission never sets that variable and never runs this script in production mode)
#
# Off-site (--offsite): if set, runs $BACKUP_OFFSITE_CMD (a shell command
# template; the backup run directory is passed as $1) after the backup
# completes. No specific provider is hard-coded - e.g.
#   BACKUP_OFFSITE_CMD='rclone copy "$1" remote:bucket/platform-backups/'
# UNTESTED beyond the invocation mechanism itself in this environment: no
# real off-site target (cloud storage account, rclone remote, etc.) is
# configured here to push to. See docs/platform/PLATFORM_BACKUP_RESTORE.md.
set -euo pipefail

BACKUP_ENCRYPTION_PASSPHRASE="${BACKUP_ENCRYPTION_PASSPHRASE:-}"
if [[ -z "$BACKUP_ENCRYPTION_PASSPHRASE" ]]; then
  echo "NO-GO: BACKUP_ENCRYPTION_PASSPHRASE must be set - backups are never written unencrypted." >&2
  exit 1
fi

RETENTION_DAYS=""
DO_OFFSITE=""
ENV=""
OUT_DIR=""

usage() {
  echo "Usage: $0 --env staging|production --out <backup-dir> [--retention-days N] [--offsite]" >&2
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENV="${2:-}"; shift 2 ;;
    --out) OUT_DIR="${2:-}"; shift 2 ;;
    --retention-days) RETENTION_DAYS="${2:-}"; shift 2 ;;
    --offsite) DO_OFFSITE="1"; shift 1 ;;
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

# Mission 15, Phase 20: backup-space preflight - MUST run before a single
# byte is written, so an undersized target volume is never discovered
# mid-backup (which would leave a truncated, unusable archive AND risk
# filling the disk Loady itself runs on, taking it down). The estimate
# sums each real source's current size (Postgres via pg_database_size,
# SQLite via a plain file stat) and applies a safety factor - the
# encrypted output is comparable in size to the plaintext it replaces
# in place (encrypt_in_place deletes the plaintext immediately after
# encrypting each artifact, so peak extra usage at any instant is at
# most one artifact's size, never the full sum), but inventory files,
# filesystem block overhead, and any estimation error all need margin.
REQUIRED_BYTES=0
LOADY_DB_BYTES="$(docker exec "$LOADY_PG_CONTAINER" psql -U "$LOADY_PG_USER" -d "$LOADY_PG_DB" -tAc "SELECT pg_database_size('$LOADY_PG_DB');" 2>/dev/null | tr -d '[:space:]')"
REQUIRED_BYTES=$((REQUIRED_BYTES + ${LOADY_DB_BYTES:-0}))

APP_DB_BYTES="$(docker exec "$LOADY_BACKEND_CONTAINER" stat -c%s /var/lib/loady/data/app.db 2>/dev/null || echo 0)"
REQUIRED_BYTES=$((REQUIRED_BYTES + ${APP_DB_BYTES:-0}))

if [[ -n "$PLATFORM_PG_CONTAINER" ]] && docker inspect -f '{{.State.Running}}' "$PLATFORM_PG_CONTAINER" >/dev/null 2>&1; then
  PLATFORM_DB_BYTES="$(docker exec "$PLATFORM_PG_CONTAINER" psql -U "$PLATFORM_PG_USER" -d "$PLATFORM_PG_DB" -tAc "SELECT pg_database_size('$PLATFORM_PG_DB');" 2>/dev/null | tr -d '[:space:]')"
  REQUIRED_BYTES=$((REQUIRED_BYTES + ${PLATFORM_DB_BYTES:-0}))
fi

# 1.5x safety factor + a fixed 200 MiB floor for inventory/checksum files
# and filesystem overhead.
REQUIRED_BYTES=$(( (REQUIRED_BYTES * 3 / 2) + (200 * 1024 * 1024) ))

# df the nearest existing ancestor of OUT_DIR, since OUT_DIR itself may
# not exist yet.
DF_TARGET="$OUT_DIR"
while [[ ! -d "$DF_TARGET" && "$DF_TARGET" != "/" ]]; do
  DF_TARGET="$(dirname "$DF_TARGET")"
done
AVAILABLE_BYTES="$(df -Pk "$DF_TARGET" | awk 'NR==2 {print $4 * 1024}')"

echo "==> Backup space preflight: need ~$((REQUIRED_BYTES / 1024 / 1024)) MiB (with safety margin), have $((AVAILABLE_BYTES / 1024 / 1024)) MiB free on $DF_TARGET." >&2
if (( AVAILABLE_BYTES < REQUIRED_BYTES )); then
  echo "NO-GO: insufficient free disk space for a safe backup. Free up space or point --out at a volume with more headroom before retrying - never proceed with a backup that might fill the disk Loady itself runs on." >&2
  exit 1
fi

mkdir -p "$OUT_DIR"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="$OUT_DIR/${ENV}-${TIMESTAMP}"
mkdir -p "$RUN_DIR"
echo "Writing backup to: $RUN_DIR"

# Encrypts a data file in place (writes <file>.enc, then deletes the
# plaintext) - AES-256-CBC + PBKDF2 via openssl, since neither `age` nor
# `gpg` (the doc's original suggestions) is installed here. The
# plaintext is never left on disk once this returns.
encrypt_in_place() {
  local plaintext="$1"
  openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt \
    -in "$plaintext" -out "${plaintext}.enc" -pass env:BACKUP_ENCRYPTION_PASSPHRASE
  rm -f "$plaintext"
}

echo "==> Dumping Loady Postgres ($LOADY_PG_DB)..."
docker exec "$LOADY_PG_CONTAINER" pg_dump -U "$LOADY_PG_USER" -d "$LOADY_PG_DB" -Fc -f /tmp/loady_backup.dump
docker cp "$LOADY_PG_CONTAINER:/tmp/loady_backup.dump" "$RUN_DIR/loady_postgres.dump"
docker exec "$LOADY_PG_CONTAINER" rm -f /tmp/loady_backup.dump
echo "==> Encrypting loady_postgres.dump..."
encrypt_in_place "$RUN_DIR/loady_postgres.dump"

echo "==> Copying Loady history/settings SQLite file..."
if docker cp "$LOADY_BACKEND_CONTAINER:/var/lib/loady/data/app.db" "$RUN_DIR/loady_app.db" 2>/dev/null; then
  echo "==> Encrypting loady_app.db..."
  encrypt_in_place "$RUN_DIR/loady_app.db"
else
  echo "    (no app.db present yet - acceptable for a brand-new environment)"
fi

if [[ -n "$PLATFORM_PG_CONTAINER" ]] && docker inspect -f '{{.State.Running}}' "$PLATFORM_PG_CONTAINER" >/dev/null 2>&1; then
  echo "==> Dumping Platform Core Postgres ($PLATFORM_PG_DB)..."
  docker exec "$PLATFORM_PG_CONTAINER" pg_dump -U "$PLATFORM_PG_USER" -d "$PLATFORM_PG_DB" -Fc -f /tmp/platform_backup.dump
  docker cp "$PLATFORM_PG_CONTAINER:/tmp/platform_backup.dump" "$RUN_DIR/platform_core_postgres.dump"
  docker exec "$PLATFORM_PG_CONTAINER" rm -f /tmp/platform_backup.dump
  echo "==> Encrypting platform_core_postgres.dump..."
  encrypt_in_place "$RUN_DIR/platform_core_postgres.dump"
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

echo "==> Computing checksums (of the encrypted artifacts, not plaintext - none remains on disk)..."
(cd "$RUN_DIR" && shasum -a 256 -- * > CHECKSUMS.sha256 2>/dev/null || sha256sum -- * > CHECKSUMS.sha256)

echo "==> Restricting backup file permissions (owner-only)..."
chmod 700 "$RUN_DIR"
chmod 600 "$RUN_DIR"/*

if [[ -n "$RETENTION_DAYS" ]]; then
  echo "==> Pruning backups older than $RETENTION_DAYS day(s) under $OUT_DIR..."
  find "$OUT_DIR" -maxdepth 1 -mindepth 1 -type d -name '*-*' -mtime "+${RETENTION_DAYS}" -print -exec rm -rf {} \;
fi

if [[ -n "$DO_OFFSITE" ]]; then
  if [[ -z "${BACKUP_OFFSITE_CMD:-}" ]]; then
    echo "NO-GO: --offsite was given but BACKUP_OFFSITE_CMD is not set." >&2
    exit 1
  fi
  echo "==> Pushing off-site (BACKUP_OFFSITE_CMD)..."
  bash -c "$BACKUP_OFFSITE_CMD" -- "$RUN_DIR"
fi

echo "==> Backup complete: $RUN_DIR"
cat "$RUN_DIR/CHECKSUMS.sha256"
