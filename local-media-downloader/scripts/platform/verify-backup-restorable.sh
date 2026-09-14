#!/usr/bin/env bash
# Mission 5, phase 5 / phase 24: proves a backup produced by
# backup-before-platform-migration.sh can actually be restored - not just
# that the files exist. Everything happens in throwaway, network-isolated
# Docker resources; nothing here ever touches the real staging or
# production databases. Also re-verifies every file against
# CHECKSUMS.sha256 first, so a corrupted backup is caught before any
# restore is even attempted (see PRODUCTION_ROLLBACK_REHEARSAL.md's backup
# corruption test).
#
# Mission 7: backup-before-platform-migration.sh now encrypts every data
# artifact (`.dump.enc`/`.db.enc`, AES-256-CBC via openssl) - this script
# decrypts into a throwaway temp dir (never overwriting the checksummed
# `.enc` file on disk) using the same BACKUP_ENCRYPTION_PASSPHRASE before
# attempting a restore.
#
# Usage: BACKUP_ENCRYPTION_PASSPHRASE=... scripts/platform/verify-backup-restorable.sh <backup-run-dir>
#   e.g. scripts/platform/verify-backup-restorable.sh docs/platform/rehearsal-artifacts/backups/staging-20260913T210149Z
set -euo pipefail

[[ -n "${BACKUP_ENCRYPTION_PASSPHRASE:-}" ]] || { echo "NO-GO: BACKUP_ENCRYPTION_PASSPHRASE must be set to decrypt this backup." >&2; exit 1; }

[[ $# -eq 1 ]] || { echo "Usage: $0 <backup-run-dir>" >&2; exit 2; }
RUN_DIR="$(cd "$1" && pwd)"
[[ -f "$RUN_DIR/CHECKSUMS.sha256" ]] || { echo "NO-GO: $RUN_DIR/CHECKSUMS.sha256 not found." >&2; exit 1; }

echo "==> Verifying checksums (of the encrypted artifacts as stored)..."
(cd "$RUN_DIR" && (shasum -a 256 -c CHECKSUMS.sha256 || sha256sum -c CHECKSUMS.sha256)) \
  || { echo "NO-GO: checksum verification failed - this backup is not trustworthy. Do not restore from it." >&2; exit 1; }
echo "    All checksums match."

run_id="platform-backup-verify-$$"
temp_dir="$(mktemp -d)"
cleanup() {
  docker rm -f "${run_id}-loady-pg" "${run_id}-platform-pg" >/dev/null 2>&1 || true
  docker volume rm "${run_id}-loady-vol" "${run_id}-platform-vol" >/dev/null 2>&1 || true
  rm -rf "$temp_dir"
}
trap cleanup EXIT

decrypt_to_temp() {
  local encrypted="$1"
  local plaintext_name="$2"
  local out="$temp_dir/$plaintext_name"
  openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
    -in "$encrypted" -out "$out" -pass env:BACKUP_ENCRYPTION_PASSPHRASE
  echo "$out"
}

restore_dump_isolated() {
  local label="$1"
  local dump_file="$2"
  local container="${run_id}-${label}-pg"
  local volume="${run_id}-${label}-vol"
  echo "==> Restoring $label Postgres dump into an isolated, network-disconnected container..."
  docker volume create "$volume" >/dev/null
  docker run -d --name "$container" --network none \
    -e POSTGRES_USER=restorecheck -e POSTGRES_PASSWORD=restorecheck -e POSTGRES_DB=restorecheck \
    -v "$volume:/var/lib/postgresql/data" -v "$dump_file:/backup.dump:ro" postgres:16 >/dev/null
  for _ in $(seq 1 30); do
    docker exec "$container" pg_isready -U restorecheck -d restorecheck >/dev/null 2>&1 && break
    sleep 1
  done
  docker exec "$container" pg_isready -U restorecheck -d restorecheck >/dev/null
  docker exec "$container" pg_restore -U restorecheck -d restorecheck --no-owner --no-privileges /backup.dump
  local table_count
  table_count="$(docker exec "$container" psql -U restorecheck -d restorecheck -tAc \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")"
  [[ "$table_count" -gt 0 ]] || { echo "NO-GO: $label restore produced zero tables." >&2; exit 1; }
  echo "    $label restore OK - $table_count table(s) present."
}

if [[ -f "$RUN_DIR/loady_postgres.dump.enc" ]]; then
  decrypted="$(decrypt_to_temp "$RUN_DIR/loady_postgres.dump.enc" "loady_postgres.dump")"
  restore_dump_isolated "loady" "$decrypted"
fi
if [[ -f "$RUN_DIR/platform_core_postgres.dump.enc" ]]; then
  decrypted="$(decrypt_to_temp "$RUN_DIR/platform_core_postgres.dump.enc" "platform_core_postgres.dump")"
  restore_dump_isolated "platform" "$decrypted"
fi

if [[ -f "$RUN_DIR/loady_app.db.enc" ]]; then
  echo "==> Verifying Loady history/settings SQLite file integrity..."
  decrypt_to_temp "$RUN_DIR/loady_app.db.enc" "app.db" >/dev/null
  python3 - "$temp_dir/app.db" <<'PY'
import sqlite3, sys
connection = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
result = connection.execute("PRAGMA integrity_check").fetchone()[0]
connection.close()
if result != "ok":
    raise SystemExit(f"SQLite integrity check failed: {result}")
print("    SQLite integrity check: ok")
PY
fi

echo "==> Backup at $RUN_DIR is verified restorable. No staging/production data was modified."
