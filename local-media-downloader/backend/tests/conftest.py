"""Test-wide setup: redirect all app data to a temp directory before anything imports app.config.paths."""
import os
import tempfile

import pytest

_TEST_DATA_DIR = tempfile.mkdtemp(prefix="lmd_test_data_")
_TEST_DOWNLOAD_DIR = tempfile.mkdtemp(prefix="lmd_test_downloads_")

os.environ["LMD_DATA_DIR"] = _TEST_DATA_DIR
os.environ["LMD_LOG_DIR"] = os.path.join(_TEST_DATA_DIR, "logs")
os.environ["LMD_DB_PATH"] = os.path.join(_TEST_DATA_DIR, "app.db")
os.environ["LMD_DOWNLOAD_DIR"] = _TEST_DOWNLOAD_DIR
# CommercialSettings.database_url defaults to DATA_DIR/commercial.db, which
# resolves from LMD_DATA_DIR above - no separate env var needed. A fixed
# SECRET_KEY keeps JWTs valid across commercial_settings re-imports within a
# test run (the real app generates a random one per-process if unset).
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")


@pytest.fixture(scope="session", autouse=True)
def _commercial_schema():
    """Creates every commercial-layer table once for the whole test session
    (SQLAlchemy metadata against the temp sqlite file above) - the app itself
    uses Alembic migrations, but tests don't need migration history, just the
    current schema."""
    from app.database import commercial_models  # noqa: F401 - registers models on Base.metadata
    from app.database.commercial_db import Base, get_engine

    Base.metadata.create_all(get_engine())
    yield


@pytest.fixture()
def db_session():
    from app.database.commercial_db import get_session_factory

    session = get_session_factory()()
    try:
        yield session
        session.commit()
    finally:
        session.close()
