#!/usr/bin/env bash
# Mission 15, Phase 18 regression test for production-preflight-inspection.sh.
# Stubs `docker`/`df`/`free` so both the GO and NO-GO paths are exercised
# deterministically without a real Docker daemon, real Postgres, or a real
# host under memory/disk pressure.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="$SCRIPT_DIR/production-preflight-inspection.sh"
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
    shift; shift  # drop "exec" and container name
    if [[ "$*" == *"pg_isready"* ]]; then exit 0; fi
    if [[ "$*" == *"count(*) FROM users"* ]]; then echo "42"; exit 0; fi
    if [[ "$*" == *"alembic current"* ]]; then echo "abc123 (head)"; exit 0; fi
    exit 1 ;;
  *) echo "unhandled: $*" >&2; exit 1 ;;
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

TLS_DIR="$WORK/tls"
mkdir -p "$TLS_DIR"
touch "$TLS_DIR/fullchain.pem" "$TLS_DIR/privkey.pem"
SIGNING_KEY="$WORK/signing-key.pem"
touch "$SIGNING_KEY"
chmod 600 "$SIGNING_KEY"

run() {
  PATH="$FAKE_BIN:$PATH" \
    LOADY_PG_CONTAINER=fake-loady-pg LOADY_BACKEND_CONTAINER=fake-loady-be \
    PLATFORM_PG_CONTAINER=fake-platform-pg PLATFORM_BACKEND_CONTAINER=fake-platform-be \
    REVERSE_PROXY_CONTAINER=fake-edge \
    SIGNING_KEY_PATH="$SIGNING_KEY" TLS_DIR="$TLS_DIR" \
    bash "$TARGET" --env production
}

echo "Case 1: everything healthy -> expect GO, exit 0"
set +e
OUT="$(run 2>&1)"; CODE=$?
set -e
if [[ "$CODE" != "0" ]] || ! grep -q "^GO$" <<<"$OUT"; then
  echo "FAILED: expected GO/exit 0. Got exit $CODE:" >&2
  echo "$OUT" >&2
  exit 1
fi
echo "  OK: GO."

echo "Case 2: signing key has wrong permissions -> expect NO-GO, exit 1"
chmod 644 "$SIGNING_KEY"
set +e
OUT="$(run 2>&1)"; CODE=$?
set -e
chmod 600 "$SIGNING_KEY"
if [[ "$CODE" != "1" ]] || ! grep -q "NO-GO:" <<<"$OUT" || ! grep -q "not mode 600" <<<"$OUT"; then
  echo "FAILED: expected NO-GO citing the permission problem. Got exit $CODE:" >&2
  echo "$OUT" >&2
  exit 1
fi
echo "  OK: NO-GO correctly cited the permission problem."

echo "ALL PASSED"
