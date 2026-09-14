#!/bin/bash
# Mission 6 continuation - starts an isolated local stack (fresh SQLite DB,
# real signing key, backend + both frontends) for the browser E2E run.
# Not part of the application; a throwaway local dev harness only.
set -euo pipefail

E2E_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$E2E_DIR/../backend"
ADMIN_DIR="$E2E_DIR/../admin-frontend"
ACCOUNT_DIR="$E2E_DIR/../account-frontend"
DATA_DIR=$(mktemp -d)

export DATABASE_URL="sqlite:///$DATA_DIR/platform.db"
export JWT_PRIVATE_KEY_PATH="$DATA_DIR/jwt_signing_key.pem"
export COOKIE_SIGNING_KEY="e2e-cookie-signing-key"
export APP_ENV=development
export PLATFORM_AUTH_BASE_URL="http://127.0.0.1:8100"
export PLATFORM_API_BASE_URL="http://127.0.0.1:8100"

echo "Data dir: $DATA_DIR"
cd "$BACKEND_DIR"
./.venv/bin/alembic upgrade head
./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8100 > "$DATA_DIR/backend.log" 2>&1 &
echo $! > "$DATA_DIR/backend.pid"

for i in $(seq 1 30); do
  if curl -s http://127.0.0.1:8100/health > /dev/null 2>&1; then break; fi
  sleep 1
done

"$BACKEND_DIR/.venv/bin/python" "$E2E_DIR/bootstrap_super_admin.py" e2e-super-admin@example.com correct-horse-battery

cd "$ADMIN_DIR"
VITE_PLATFORM_API_BASE_URL="http://127.0.0.1:8100" npm run dev > "$DATA_DIR/admin-frontend.log" 2>&1 &
echo $! > "$DATA_DIR/admin-frontend.pid"

cd "$ACCOUNT_DIR"
VITE_PLATFORM_API_BASE_URL="http://127.0.0.1:8100" npm run dev > "$DATA_DIR/account-frontend.log" 2>&1 &
echo $! > "$DATA_DIR/account-frontend.pid"

for i in $(seq 1 30); do
  if curl -s http://127.0.0.1:5273 > /dev/null 2>&1 && curl -s http://127.0.0.1:5274 > /dev/null 2>&1; then break; fi
  sleep 1
done

echo "$DATA_DIR" > "$E2E_DIR/.last_data_dir"
echo "All servers up. Data dir: $DATA_DIR"
