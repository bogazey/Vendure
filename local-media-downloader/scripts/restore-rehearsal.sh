#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 /path/to/postgres.dump /path/to/app.db" >&2
  exit 2
fi

pg_dump_path="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
sqlite_path="$(cd "$(dirname "$2")" && pwd)/$(basename "$2")"
[[ -f "$pg_dump_path" && -f "$sqlite_path" ]] || { echo "Both backup files must exist." >&2; exit 2; }

run_id="loady-restore-check-$$"
container_name="${run_id}-postgres"
volume_name="${run_id}-data"
temp_dir="$(mktemp -d)"
cleanup() {
  docker rm -f "$container_name" >/dev/null 2>&1 || true
  docker volume rm "$volume_name" >/dev/null 2>&1 || true
  rm -rf "$temp_dir"
}
trap cleanup EXIT

docker volume create "$volume_name" >/dev/null
docker run -d --name "$container_name" --network none \
  -e POSTGRES_USER=restorecheck -e POSTGRES_PASSWORD=restorecheck -e POSTGRES_DB=restorecheck \
  -v "$volume_name:/var/lib/postgresql/data" -v "$pg_dump_path:/backup.dump:ro" postgres:16-alpine >/dev/null

for _ in {1..30}; do
  docker exec "$container_name" pg_isready -U restorecheck -d restorecheck >/dev/null 2>&1 && break
  sleep 1
done
docker exec "$container_name" pg_isready -U restorecheck -d restorecheck >/dev/null
docker exec "$container_name" pg_restore -U restorecheck -d restorecheck --no-owner --no-privileges /backup.dump
docker exec "$container_name" psql -U restorecheck -d restorecheck -v ON_ERROR_STOP=1 -c 'SELECT 1' >/dev/null

cp "$sqlite_path" "$temp_dir/app.db"
python3 - "$temp_dir/app.db" <<'PY'
import sqlite3, sys
connection = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
result = connection.execute("PRAGMA integrity_check").fetchone()[0]
connection.close()
if result != "ok":
    raise SystemExit(f"SQLite integrity check failed: {result}")
PY

echo "Restore rehearsal passed in isolated temporary storage. Production data was not modified."
