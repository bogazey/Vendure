"""RS256 signing-key persistence and fail-closed behavior (mission 4,
phase 3): a key file that already exists is always loaded (any APP_ENV);
a missing key file is only auto-generated in development, and fails
closed everywhere else, so a staging/production process never silently
boots with a throwaway key that would invalidate every previously issued
token on the next restart.

Key loading is cached per-process (`functools.lru_cache`) and settings are
a lazy singleton, so each test resets both explicitly rather than relying
on module reload (reloading `jwt_keys` would desync it from `jwt_tokens`,
which already imported the pre-reload function objects by name).
"""
from __future__ import annotations

import pytest

from app.config import settings as settings_module
from app.security import jwt_keys, jwt_tokens


@pytest.fixture(autouse=True)
def _isolate_settings_singleton():
    """`get_settings()`/`_load_or_create_private_key()` are process-wide
    singletons/caches. `monkeypatch` reverts the env vars this file sets,
    but a settings object already constructed from a leaked env value
    would otherwise survive as the cached singleton and bleed into
    unrelated test files run afterward — reset both, unconditionally,
    once this test (and its own monkeypatch reverts) are done."""
    yield
    settings_module._settings = None
    jwt_keys._load_or_create_private_key.cache_clear()


def _reset(monkeypatch, key_path, app_env: str) -> None:
    monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", str(key_path))
    monkeypatch.setenv("APP_ENV", app_env)
    settings_module._settings = None
    jwt_keys._load_or_create_private_key.cache_clear()


def test_restart_preserves_the_signing_key_and_old_tokens_still_verify(monkeypatch, tmp_path):
    key_path = tmp_path / "signing.pem"
    _reset(monkeypatch, key_path, "development")

    token = jwt_tokens.create_session_access_token("usr_restart_test")
    assert key_path.exists()

    # Simulate a process restart: drop the settings singleton and the
    # lru_cache'd key, exactly like a fresh interpreter would start.
    _reset(monkeypatch, key_path, "development")

    payload = jwt_tokens.decode_session_access_token(token)
    assert payload is not None
    assert payload["sub"] == "usr_restart_test"


def test_development_generates_a_key_when_none_exists(monkeypatch, tmp_path):
    key_path = tmp_path / "auto.pem"
    _reset(monkeypatch, key_path, "development")

    assert not key_path.exists()
    jwt_keys.validate_signing_key_material()
    assert key_path.exists()
    assert oct(key_path.stat().st_mode)[-3:] == "600"


def test_staging_fails_closed_when_no_key_file_is_provisioned(monkeypatch, tmp_path):
    key_path = tmp_path / "missing-staging.pem"
    _reset(monkeypatch, key_path, "staging")

    assert not key_path.exists()
    raised = False
    try:
        jwt_keys.validate_signing_key_material()
    except jwt_keys.SigningKeyUnavailableError:
        raised = True
    assert raised, "expected SigningKeyUnavailableError"
    assert not key_path.exists(), "staging must never fall back to generating a key"


def test_production_fails_closed_when_no_key_file_is_provisioned(monkeypatch, tmp_path):
    key_path = tmp_path / "missing-prod.pem"
    _reset(monkeypatch, key_path, "production")

    raised = False
    try:
        jwt_keys.validate_signing_key_material()
    except jwt_keys.SigningKeyUnavailableError:
        raised = True
    assert raised, "expected SigningKeyUnavailableError"


def test_production_loads_a_pre_provisioned_key_file_without_error(monkeypatch, tmp_path):
    # First, generate a key as a stand-in for "provisioned out of band" by
    # an operator before the production process ever starts.
    key_path = tmp_path / "provisioned.pem"
    _reset(monkeypatch, key_path, "development")
    jwt_keys.validate_signing_key_material()
    assert key_path.exists()

    # Reload as production with that same (now-existing) key file.
    _reset(monkeypatch, key_path, "production")
    jwt_keys.validate_signing_key_material()  # must not raise
    assert jwt_keys.signing_key_is_available() is True


def test_signing_key_is_available_reports_false_in_staging_without_a_key(monkeypatch, tmp_path):
    key_path = tmp_path / "absent.pem"
    _reset(monkeypatch, key_path, "staging")

    assert jwt_keys.signing_key_is_available() is False
