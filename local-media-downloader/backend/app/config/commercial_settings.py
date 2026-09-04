"""Commercial-layer configuration (auth, billing, ads).

Everything here is read from the environment (optionally via a local .env
file). Nothing here is a real secret checked into git — see .env.example.
"""
from __future__ import annotations

import secrets

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config.logging_config import get_logger
from app.config.paths import DATA_DIR

logger = get_logger("commercial_settings")

# Generated once per process if SECRET_KEY isn't set, rather than falling
# back to a fixed "dev" string that could accidentally end up meaning
# something in a real deployment. Sessions won't survive a restart until a
# real SECRET_KEY is configured.
_GENERATED_SECRET = secrets.token_hex(32)


class CommercialSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Auth / sessions ---
    secret_key: str = Field(default=_GENERATED_SECRET, alias="SECRET_KEY")
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = Field(default=15, alias="ACCESS_TOKEN_TTL_MINUTES")
    refresh_token_ttl_days: int = Field(default=30, alias="REFRESH_TOKEN_TTL_DAYS")
    # False for local http:// dev, must be True behind HTTPS in production.
    cookie_secure: bool = Field(default=False, alias="COOKIE_SECURE")
    cookie_domain: str | None = Field(default=None, alias="COOKIE_DOMAIN")

    # --- Database (SQLAlchemy; swap to postgresql://... in production) ---
    database_url: str = Field(
        default=f"sqlite:///{DATA_DIR / 'commercial.db'}", alias="DATABASE_URL"
    )

    # --- Paddle ---
    paddle_env: str = Field(default="sandbox", alias="PADDLE_ENV")
    paddle_api_key: str = Field(default="", alias="PADDLE_API_KEY")
    paddle_client_token: str = Field(default="", alias="PADDLE_CLIENT_TOKEN")
    paddle_webhook_secret: str = Field(default="", alias="PADDLE_WEBHOOK_SECRET")
    paddle_pro_monthly_price_id: str = Field(default="", alias="PADDLE_PRO_MONTHLY_PRICE_ID")
    paddle_pro_annual_price_id: str = Field(default="", alias="PADDLE_PRO_ANNUAL_PRICE_ID")
    paddle_creator_monthly_price_id: str = Field(default="", alias="PADDLE_CREATOR_MONTHLY_PRICE_ID")
    paddle_creator_annual_price_id: str = Field(default="", alias="PADDLE_CREATOR_ANNUAL_PRICE_ID")

    # --- Ads ---
    ads_enabled: bool = Field(default=True, alias="ADS_ENABLED")

    # --- Frontend origin (for email links, CORS is handled in main.py) ---
    frontend_base_url: str = Field(default="http://127.0.0.1:5173", alias="FRONTEND_BASE_URL")


_settings: CommercialSettings | None = None


def get_commercial_settings() -> CommercialSettings:
    global _settings
    if _settings is None:
        _settings = CommercialSettings()
        if _settings.secret_key == _GENERATED_SECRET:
            logger.warning(
                "SECRET_KEY not set - using a random per-process secret. "
                "All sessions will be invalidated on restart. Set SECRET_KEY "
                "in your environment for anything beyond local development."
            )
        if _settings.paddle_env != "sandbox":
            logger.warning(
                "PADDLE_ENV=%s - this build is only intended to run against "
                "Paddle Sandbox. Refusing to treat this as a live billing "
                "environment.",
                _settings.paddle_env,
            )
    return _settings
