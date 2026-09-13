"""SQLAlchemy engine/session setup — portable between SQLite (local dev)
and PostgreSQL (a future production deployment), same pattern as Loady's
`commercial_db.py`.
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config.settings import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_SessionFactory = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        is_sqlite = settings.database_url.startswith("sqlite")
        if is_sqlite:
            _engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
        else:
            # PostgreSQL (mission 4, phase 2): a small bounded pool plus
            # pre-ping so a connection dropped by the DB (idle timeout,
            # restart) is detected and replaced rather than surfacing as a
            # user-facing error on the next request — reasonable defaults
            # for this service's single-worker V1 staging deployment, not
            # tuned for horizontal scale-out.
            _engine = create_engine(
                settings.database_url,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=10,
                pool_recycle=1800,
            )
    return _engine


def get_session_factory() -> sessionmaker:
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)
    return _SessionFactory
