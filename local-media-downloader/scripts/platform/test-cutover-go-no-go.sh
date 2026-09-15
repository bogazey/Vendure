#!/usr/bin/env bash
# Mission 15, Phase 25 regression test for cutover-go-no-go.sh.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="$SCRIPT_DIR/cutover-go-no-go.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

FAKE_BIN="$WORK/bin"
mkdir -p "$FAKE_BIN"
cat > "$FAKE_BIN/docker" <<'EOF'
#!/usr/bin/env bash
case "$1" in
  version) echo "24.0.0"; exit 0 ;;
  compose) echo "2.24.0"; exit 0 ;;
  volume)
    echo "loady-rc_app-data"
    echo "loady-rc_media-data"
    echo "loady-rc_postgres-data"
    echo "loady-rc_platform-postgres-data"
    exit 0 ;;
  inspect) echo "healthy"; exit 0 ;;
  exec)
    shift; shift
    if [[ "$*" == *"pg_isready"* ]]; then exit 0; fi
    if [[ "$*" == *"count(*) FROM users"* ]]; then echo "42"; exit 0; fi
    if [[ "$*" == *"alembic current"* ]]; then echo "abc123 (head)"; exit 0; fi
    exit 1 ;;
  *) exit 1 ;;
esac
EOF
chmod +x "$FAKE_BIN/docker"
cat > "$FAKE_BIN/df" <<'EOF'
#!/usr/bin/env bash
echo "Filesystem 1M-blocks Used Available Use% Mounted"
echo "fake 100000 1 50000 1% /"
EOF
chmod +x "$FAKE_BIN/df"
cat > "$FAKE_BIN/free" <<'EOF'
#!/usr/bin/env bash
echo "              total        used        free      shared  buff/cache   available"
echo "Mem:           8000        2000        1000           0        5000        6000"
echo "Swap:          2000           0        2000"
EOF
chmod +x "$FAKE_BIN/free"

TLS_DIR="$WORK/tls"; mkdir -p "$TLS_DIR"; touch "$TLS_DIR/fullchain.pem" "$TLS_DIR/privkey.pem"
SIGNING_KEY="$WORK/signing-key.pem"; touch "$SIGNING_KEY"; chmod 600 "$SIGNING_KEY"

export PATH="$FAKE_BIN:$PATH"
export LOADY_PG_CONTAINER=fake-loady-pg LOADY_BACKEND_CONTAINER=fake-loady-be
export PLATFORM_PG_CONTAINER=fake-platform-pg PLATFORM_BACKEND_CONTAINER=fake-platform-be
export REVERSE_PROXY_CONTAINER=fake-edge
export SIGNING_KEY_PATH="$SIGNING_KEY" TLS_DIR="$TLS_DIR"

BACKUP_DIR="$WORK/backups"
BACKUP_RUN_DIR="$BACKUP_DIR/production-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP_RUN_DIR"
touch "$BACKUP_RUN_DIR/CHECKSUMS.sha256"

DRY_RUN_REPORT="$WORK/dry-run-report.txt"
echo "created=10 linked=5 skipped=0 conflicted=0 failed=0" > "$DRY_RUN_REPORT"

echo "Case 1: everything satisfied -> expect GO, exit 0"
set +e
OUT="$(MIGRATION_DRY_RUN_REPORT_PATH="$DRY_RUN_REPORT" OAUTH_REDIRECT_URI_VERIFIED=yes \
  bash "$TARGET" --env production --backup-dir "$BACKUP_DIR" 2>&1)"
CODE=$?
set -e
if [[ "$CODE" != "0" ]] || ! grep -q "^OVERALL: GO$" <<<"$OUT"; then
  echo "FAILED: expected overall GO. Got exit $CODE:" >&2
  echo "$OUT" >&2
  exit 1
fi
echo "  OK: GO."

echo "Case 2: no backup present -> expect NO-GO, exit 1"
EMPTY_BACKUP_DIR="$WORK/empty-backups"
mkdir -p "$EMPTY_BACKUP_DIR"
set +e
OUT="$(MIGRATION_DRY_RUN_REPORT_PATH="$DRY_RUN_REPORT" OAUTH_REDIRECT_URI_VERIFIED=yes \
  bash "$TARGET" --env production --backup-dir "$EMPTY_BACKUP_DIR" 2>&1)"
CODE=$?
set -e
if [[ "$CODE" != "1" ]] || ! grep -q "^OVERALL: NO-GO$" <<<"$OUT" || ! grep -q "BACKUPS:.*NO-GO" <<<"$OUT"; then
  echo "FAILED: expected overall NO-GO citing BACKUPS. Got exit $CODE:" >&2
  echo "$OUT" >&2
  exit 1
fi
echo "  OK: NO-GO correctly cited missing backup."

echo "Case 3: OAUTH attestation missing -> expect NO-GO"
set +e
OUT="$(MIGRATION_DRY_RUN_REPORT_PATH="$DRY_RUN_REPORT" \
  bash "$TARGET" --env production --backup-dir "$BACKUP_DIR" 2>&1)"
CODE=$?
set -e
if [[ "$CODE" != "1" ]] || ! grep -q "OAUTH:.*NO-GO" <<<"$OUT"; then
  echo "FAILED: expected NO-GO citing missing OAUTH attestation. Got exit $CODE:" >&2
  echo "$OUT" >&2
  exit 1
fi
echo "  OK: NO-GO correctly cited unattested OAUTH."

echo "Case 4: --json produces valid JSON with overall key"
set +e
OUT="$(MIGRATION_DRY_RUN_REPORT_PATH="$DRY_RUN_REPORT" OAUTH_REDIRECT_URI_VERIFIED=yes \
  bash "$TARGET" --env production --backup-dir "$BACKUP_DIR" --json 2>&1)"
CODE=$?
set -e
if [[ "$CODE" != "0" ]] || ! python3 -c "import json,sys; d=json.load(sys.stdin); assert d['overall']=='GO'" <<<"$OUT"; then
  echo "FAILED: expected valid JSON with overall=GO. Got exit $CODE:" >&2
  echo "$OUT" >&2
  exit 1
fi
echo "  OK: JSON output valid."

echo "ALL PASSED"
