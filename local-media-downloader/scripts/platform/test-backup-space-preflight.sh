#!/usr/bin/env bash
# Mission 15, Phase 20 regression test for the disk-space preflight added to
# backup-before-platform-migration.sh. No real Docker daemon or Postgres is
# needed - a fake `docker` and a fake `df` are placed first on PATH so the
# script's own logic (size query -> safety-factor math -> comparison against
# free space -> NO-GO) is exercised deterministically, in isolation from
# whether a real database of a given size actually exists anywhere.
#
# Usage: scripts/platform/test-backup-space-preflight.sh
# Exits 0 and prints "ALL PASSED" if both cases behave correctly; exits 1
# and prints which case failed otherwise.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="$SCRIPT_DIR/backup-before-platform-migration.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

FAKE_BIN="$WORK/bin"
mkdir -p "$FAKE_BIN"

make_fake_docker() {
  local db_bytes="$1"
  cat > "$FAKE_BIN/docker" <<EOF
#!/usr/bin/env bash
if [[ "\$1" == "inspect" ]]; then
  echo "true"
  exit 0
fi
if [[ "\$1" == "exec" ]]; then
  shift
  container="\$1"; shift
  # psql size query
  if [[ "\$*" == *"pg_database_size"* ]]; then
    echo "$db_bytes"
    exit 0
  fi
  # app.db stat
  if [[ "\$*" == *"stat -c%s"* ]]; then
    echo "0"
    exit 0
  fi
  exit 1
fi
echo "unhandled docker invocation: \$*" >&2
exit 1
EOF
  chmod +x "$FAKE_BIN/docker"
}

make_fake_df() {
  local avail_kib="$1"
  cat > "$FAKE_BIN/df" <<EOF
#!/usr/bin/env bash
echo "Filesystem 1K-blocks Used Available Use% Mounted"
echo "fake 1000000 1 $avail_kib 1% /"
EOF
  chmod +x "$FAKE_BIN/df"
}

run_case() {
  local db_bytes="$1" avail_kib="$2"
  make_fake_docker "$db_bytes"
  make_fake_df "$avail_kib"
  OUT_DIR_TEST="$WORK/out-$RANDOM"
  set +e
  PATH="$FAKE_BIN:$PATH" \
    LOADY_PG_CONTAINER=fake-loady-pg LOADY_PG_DB=fake_db LOADY_PG_USER=fake_user \
    LOADY_BACKEND_CONTAINER=fake-loady-backend \
    BACKUP_ENCRYPTION_PASSPHRASE=not-a-real-secret-test-only \
    bash "$TARGET" --env staging --out "$OUT_DIR_TEST" > "$WORK/output.log" 2>&1
  echo "$?"
}

echo "Case 1: database far larger than free disk space -> expect NO-GO, exit 1"
EXIT_CODE="$(run_case $((5 * 1024 * 1024 * 1024)) $((1 * 1024 * 1024)))"  # 5 GiB DB, 1 GiB free
if [[ "$EXIT_CODE" != "1" ]] || ! grep -q "NO-GO: insufficient free disk space" "$WORK/output.log"; then
  echo "FAILED: expected exit 1 with an insufficient-space NO-GO message. Got exit $EXIT_CODE:" >&2
  cat "$WORK/output.log" >&2
  exit 1
fi
echo "  OK: correctly refused with NO-GO."

echo "Case 2: database far smaller than free disk space -> expect the preflight to PASS (script proceeds past it)"
EXIT_CODE="$(run_case $((10 * 1024 * 1024)) $((50 * 1024 * 1024)))"  # 10 MiB DB, 50 GiB free
if grep -q "NO-GO: insufficient free disk space" "$WORK/output.log"; then
  echo "FAILED: preflight incorrectly refused a backup with ample free space:" >&2
  cat "$WORK/output.log" >&2
  exit 1
fi
if ! grep -q "Backup space preflight: need" "$WORK/output.log"; then
  echo "FAILED: expected preflight message not found at all - the check may not be running." >&2
  cat "$WORK/output.log" >&2
  exit 1
fi
echo "  OK: preflight passed and the script proceeded (later failure, if any, is expected - the fake docker doesn't implement pg_dump)."

echo "ALL PASSED"
