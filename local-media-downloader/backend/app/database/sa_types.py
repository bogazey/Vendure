"""Portable SQLAlchemy column types.

SQLite doesn't actually persist timezone info even for a column declared
`DateTime(timezone=True)` - datetimes round-trip as naive, which then blows
up any comparison against a timezone-aware `datetime.now(timezone.utc)`
(TypeError: can't compare offset-naive and offset-aware datetimes).
PostgreSQL, by contrast, returns genuinely tz-aware datetimes for the same
column type. UTCDateTime normalizes both directions so the rest of the app
can always assume "this is a timezone-aware UTC datetime", on either engine.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return value
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return value
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
