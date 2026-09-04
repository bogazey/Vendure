"""Key-value settings persistence backed by SQLite."""
from __future__ import annotations

import json
from typing import Any

from app.database.db import get_cursor


def load_all() -> dict[str, Any]:
    with get_cursor() as cur:
        cur.execute("SELECT key, value FROM settings")
        rows = cur.fetchall()
    result: dict[str, Any] = {}
    for row in rows:
        try:
            result[row["key"]] = json.loads(row["value"])
        except (json.JSONDecodeError, TypeError):
            result[row["key"]] = row["value"]
    return result


def save_all(values: dict[str, Any]) -> None:
    with get_cursor() as cur:
        for key, value in values.items():
            cur.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(value)),
            )
