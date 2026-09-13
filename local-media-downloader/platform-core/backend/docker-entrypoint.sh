#!/bin/sh
set -eu

# Mission 4, phase 2: compose's own `depends_on: condition: service_healthy`
# already blocks container start until postgres's healthcheck passes, but
# "healthy" only means the postgres process itself accepts connections -
# not that this specific database/user is ready. Wait explicitly rather
# than letting Alembic fail on a cold start / restart race.
python - <<'PYEOF'
import sys
import time

from app.database.db import get_engine
from sqlalchemy import text

deadline = time.monotonic() + 60
last_error = None
while time.monotonic() < deadline:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        break
    except Exception as exc:  # noqa: BLE001 - a plain readiness poll, not app logic
        last_error = exc
        time.sleep(2)
else:
    print(f"platform-core: database not reachable after 60s: {last_error}", file=sys.stderr)
    sys.exit(1)
PYEOF

python -m alembic upgrade head
exec "$@"
