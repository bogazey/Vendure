#!/usr/bin/env bash
# Local Media Downloader - macOS / Linux startup script.
# Sets up the backend venv and frontend deps if needed, then launches both
# and opens the app in your default browser.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
FRONTEND_URL="http://127.0.0.1:5173"

echo "== Local Media Downloader =="

# 1. Verify Python
if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 is required but was not found. Install Python 3.12+ and try again." >&2
  exit 1
fi
echo "-> Python: $(python3 --version)"

# 2. Create virtual environment if missing
if [ ! -d "$BACKEND_DIR/.venv" ]; then
  echo "-> Creating Python virtual environment..."
  python3 -m venv "$BACKEND_DIR/.venv"
fi

# shellcheck disable=SC1091
source "$BACKEND_DIR/.venv/bin/activate"

# 3. Install backend requirements if needed
echo "-> Installing backend dependencies..."
pip install --disable-pip-version-check -q -r "$BACKEND_DIR/requirements.txt"

# 3b. Commercial layer: generate a local backend/.env with a real SECRET_KEY
# on first run (a missing one is fine - the app just generates a random
# per-process secret - but that invalidates every session on each restart,
# which is annoying for local development), then apply DB migrations.
if [ ! -f "$BACKEND_DIR/.env" ]; then
  echo "-> First run: creating backend/.env with a generated SECRET_KEY..."
  GENERATED_SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  {
    echo "SECRET_KEY=$GENERATED_SECRET"
    echo "PADDLE_ENV=sandbox"
  } > "$BACKEND_DIR/.env"
fi
echo "-> Applying commercial database migrations..."
(cd "$BACKEND_DIR" && python -m alembic upgrade head)

# 4. Verify FFmpeg
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "Warning: FFmpeg was not found on PATH. The app will start, but downloads"
  echo "requiring merging/conversion will fail until FFmpeg is installed."
  echo "See the README for installation instructions."
else
  echo "-> FFmpeg: $(ffmpeg -version | head -n1)"
fi

# 5. Install frontend dependencies if needed
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo "-> Installing frontend dependencies..."
  (cd "$FRONTEND_DIR" && npm install)
fi

# 6. Launch backend
echo "-> Starting backend on http://127.0.0.1:8000 ..."
(cd "$BACKEND_DIR" && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000) &
BACKEND_PID=$!

cleanup() {
  echo ""
  echo "Shutting down..."
  kill "$BACKEND_PID" 2>/dev/null || true
  kill "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# 7. Launch frontend
echo "-> Starting frontend on $FRONTEND_URL ..."
(cd "$FRONTEND_DIR" && npm run dev -- --host 127.0.0.1 --port 5173) &
FRONTEND_PID=$!

# 8. Open the browser once the frontend is reachable
(
  for _ in $(seq 1 30); do
    if curl -s -o /dev/null "$FRONTEND_URL"; then
      if command -v open >/dev/null 2>&1; then
        open "$FRONTEND_URL"
      elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$FRONTEND_URL"
      fi
      break
    fi
    sleep 1
  done
) &

wait "$BACKEND_PID" "$FRONTEND_PID"
