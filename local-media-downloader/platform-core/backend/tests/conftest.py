"""Test-wide setup: redirect all app data to a temp directory before
anything imports app.config.settings (mirrors Loady's own
`backend/tests/conftest.py` pattern)."""
from __future__ import annotations

import os
import tempfile

import pytest

_TEST_DIR = tempfile.mkdtemp(prefix="platform_core_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DIR}/platform.db"
os.environ["JWT_PRIVATE_KEY_PATH"] = f"{_TEST_DIR}/jwt_signing_key.pem"
os.environ.setdefault("COOKIE_SIGNING_KEY", "test-cookie-signing-key-not-for-production")


@pytest.fixture(scope="session", autouse=True)
def _schema():
    from app.database import models  # noqa: F401 - registers models on Base.metadata
    from app.database.db import Base, get_engine, get_session_factory
    from app.database.seed_roles import ensure_roles

    Base.metadata.create_all(get_engine())
    session = get_session_factory()()
    try:
        ensure_roles(session)
    finally:
        session.close()
    yield


@pytest.fixture()
def db_session():
    from app.database.db import get_session_factory

    session = get_session_factory()()
    try:
        yield session
        session.commit()
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    from app.services import rate_limit_service

    for limiter in (
        rate_limit_service.login_limiter,
        rate_limit_service.signup_limiter,
        rate_limit_service.password_reset_limiter,
        rate_limit_service.oauth_token_limiter,
    ):
        limiter.clear()
    yield


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as c:
        yield c
