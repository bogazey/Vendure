"""SQLAlchemy engine/session for the commercial layer (users, billing, usage).

Deliberately separate from app/database/db.py, which is the existing raw
sqlite3 layer backing the downloader's history/settings tables. Keeping them
apart means the working downloader code (and its tests) is untouched, and
this layer can point at PostgreSQL in production just by changing
DATABASE_URL - no code changes.
"""
from __future__ import annotations

from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config.commercial_settings import get_commercial_settings


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal: sessionmaker | None = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_commercial_settings()
        connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
        _engine = create_engine(settings.database_url, connect_args=connect_args, future=True)
        if settings.database_url.startswith("sqlite"):
            from sqlalchemy import event

            @event.listens_for(_engine, "connect")
            def _set_sqlite_pragmas(dbapi_connection, _record) -> None:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys = ON")
                cursor.close()
    return _engine


def get_session_factory() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False, future=True)
    return _SessionLocal


def get_db() -> Iterator[Session]:
    """FastAPI dependency: yields a session, commits on success, rolls back on error."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def session_scope() -> Session:
    """For use outside FastAPI's DI (e.g. background jobs, tests, scripts).
    Caller is responsible for commit/rollback/close, ideally via `with`."""
    return get_session_factory()()
