"""Platform Core configuration.

Everything here is read from the environment (optionally via a local .env
file), following the same pattern as Loady's `commercial_settings.py`.
Nothing here is a real secret checked into git.

`PLATFORM_AUTH_BASE_URL` / `PLATFORM_API_BASE_URL` are deliberately
configurable rather than hard-coded to any final public domain (see
mission-brief section 6) — a future production deployment might use
`https://auth.<ecosystem-domain>`, but local development must work without
owning that domain at all.
"""
from __future__ import annotations

import secrets
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Generated once per process if COOKIE_SIGNING_KEY isn't set, mirroring
# Loady's SECRET_KEY pattern: no fixed "dev" fallback that could accidentally
# mean something in a real deployment.
_GENERATED_COOKIE_KEY = secrets.token_hex(32)


class PlatformSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    app_env: str = Field(default="development", alias="APP_ENV")

    # --- Central identity domains (configurable, never hard-coded) ---
    platform_auth_base_url: str = Field(default="http://localhost:8100", alias="PLATFORM_AUTH_BASE_URL")
    platform_api_base_url: str = Field(default="http://localhost:8100", alias="PLATFORM_API_BASE_URL")

    # --- Database (SQLAlchemy; portable to PostgreSQL in production) ---
    database_url: str = Field(
        default=f"sqlite:///{DATA_DIR / 'platform.db'}", alias="DATABASE_URL"
    )

    # --- Central session cookies (separate namespace from any product's
    # own cookies — this service's cookies are never read by a product) ---
    cookie_signing_key: str = Field(default=_GENERATED_COOKIE_KEY, alias="COOKIE_SIGNING_KEY")
    cookie_secure: bool = Field(default=False, alias="COOKIE_SECURE")
    cookie_domain: str | None = Field(default=None, alias="COOKIE_DOMAIN")
    access_token_ttl_minutes: int = Field(default=15, alias="ACCESS_TOKEN_TTL_MINUTES")
    refresh_token_ttl_days: int = Field(default=30, alias="REFRESH_TOKEN_TTL_DAYS")

    # --- OIDC-style token signing (RS256; JWKS published for resource
    # servers/products to verify without ever holding the private key) ---
    jwt_private_key_path: str = Field(
        default=str(DATA_DIR / "jwt_signing_key.pem"), alias="JWT_PRIVATE_KEY_PATH"
    )
    jwt_key_id: str = Field(default="platform-core-2026-1", alias="JWT_KEY_ID")
    oidc_access_token_ttl_minutes: int = Field(default=15, alias="OIDC_ACCESS_TOKEN_TTL_MINUTES")
    oidc_id_token_ttl_minutes: int = Field(default=15, alias="OIDC_ID_TOKEN_TTL_MINUTES")
    oidc_refresh_token_ttl_days: int = Field(default=30, alias="OIDC_REFRESH_TOKEN_TTL_DAYS")
    authorization_code_ttl_seconds: int = Field(default=60, alias="AUTHORIZATION_CODE_TTL_SECONDS")

    # --- Email (dev/test backend only in this mission — see mission-brief
    # section 21: do not configure production Resend here) ---
    email_backend: str = Field(default="log", alias="EMAIL_BACKEND")

    # --- Mission 6: billing (Phases 9-11). No live processor is ever
    # called from this service (mission-brief Phase 9/56) - these exist
    # so webhook signature verification and (future, out-of-mission) live
    # checkout can be configured without code changes. Never a real
    # production secret checked into git. ---
    billing_default_provider: str = Field(default="paddle", alias="BILLING_DEFAULT_PROVIDER")
    paddle_webhook_secret: str | None = Field(default=None, alias="PADDLE_WEBHOOK_SECRET")

    # --- Mission 6: service-to-service auth (Phases 36-37) ---
    service_access_token_ttl_minutes: int = Field(default=15, alias="SERVICE_ACCESS_TOKEN_TTL_MINUTES")

    # --- Mission 6: outbound product webhooks (Phases 41-43) ---
    outbox_delivery_timeout_seconds: float = Field(default=5.0, alias="OUTBOX_DELIVERY_TIMEOUT_SECONDS")
    outbox_max_attempts: int = Field(default=5, alias="OUTBOX_MAX_ATTEMPTS")

    # --- Mission 6 continuation: webhook secret encryption at rest ---
    # 32 raw bytes, base64-encoded. Empty in dev (an ephemeral per-process
    # key is generated instead - see app/security/secret_encryption.py);
    # staging/production MUST set a real value or every encrypt/decrypt
    # call fails closed rather than storing plaintext.
    webhook_secret_encryption_key: str = Field(default="", alias="WEBHOOK_SECRET_ENCRYPTION_KEY")


_settings: PlatformSettings | None = None


def get_settings() -> PlatformSettings:
    global _settings
    if _settings is None:
        _settings = PlatformSettings()
    return _settings
