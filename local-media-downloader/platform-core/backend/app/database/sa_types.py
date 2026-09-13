"""Timezone-safe DateTime column, copied verbatim from Loady's
`sa_types.py` — SQLite silently drops timezone info even on a
`DateTime(timezone=True)` column, which caused a real production bug there
("can't compare offset-naive and offset-aware datetimes"). This normalizes
to timezone-aware UTC on both read and write, portable to PostgreSQL
unchanged.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
