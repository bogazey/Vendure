"""Commercial-layer configuration (auth, billing, ads).

Everything here is read from the environment (optionally via a local .env
file). Nothing here is a real secret checked into git — see .env.example.
"""
from __future__ import annotations

import secrets

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config.logging_config import get_logger
from app.config.paths import DATA_DIR, DEFAULT_DOWNLOAD_DIR

logger = get_logger("commercial_settings")

# Generated once per process if SECRET_KEY isn't set, rather than falling
# back to a fixed "dev" string that could accidentally end up meaning
# something in a real deployment. Sessions won't survive a restart until a
# real SECRET_KEY is configured.
_GENERATED_SECRET = secrets.token_hex(32)


class CommercialSettings(BaseSettings):
    # env_ignore_empty: a blank `KEY=` line in .env (as .env.example ships
    # for SECRET_KEY/DATABASE_URL/DOWNLOAD_ROOT/COOKIE_DOMAIN, intending the
    # Python-side default below to apply) would otherwise be read as an
    # explicit empty string and override the default instead of falling
    # through to it - notably making SECRET_KEY="" silently instead of a
    # generated secret, with no warning.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    # --- Auth / sessions ---
    secret_key: str = Field(default=_GENERATED_SECRET, alias="SECRET_KEY")
    app_env: str = Field(default="development", alias="APP_ENV")
    email_backend: str = Field(default="log", alias="EMAIL_BACKEND")
    resend_api_key: SecretStr = Field(default=SecretStr(""), alias="RESEND_API_KEY")
    email_from: str = Field(default="", alias="EMAIL_FROM")
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

    # --- Storage ---
    # Admin/server config, not user-editable: every authenticated user's
    # downloads are confined to <DOWNLOAD_ROOT>/<user_id>/ - see
    # app/services/user_storage_service.py. Defaults to the personal app's
    # own default download folder so this works out of the box.
    download_root: str = Field(default=str(DEFAULT_DOWNLOAD_DIR), alias="DOWNLOAD_ROOT")

    # --- Guest downloads ---
    # Anonymous "try before you sign up" allowance - see guest_service.py /
    # guest_storage_service.py. Guest files/quota rows older than this are
    # swept on startup (same one-shot pattern as
    # history_repo.mark_interrupted_as_failed, not a recurring scheduler).
    guest_download_limit: int = Field(default=5, alias="GUEST_DOWNLOAD_LIMIT")
    guest_data_ttl_hours: int = Field(default=48, alias="GUEST_DATA_TTL_HOURS")
    authenticated_media_ttl_hours: int = Field(default=24, alias="AUTHENTICATED_MEDIA_TTL_HOURS")
    partial_media_ttl_hours: int = Field(default=6, alias="PARTIAL_MEDIA_TTL_HOURS")
    media_cleanup_interval_minutes: int = Field(default=60, alias="MEDIA_CLEANUP_INTERVAL_MINUTES")
    media_max_bytes: int = Field(default=40 * 1024**3, alias="MEDIA_MAX_BYTES")
    # Per-file ceiling for direct image/CDN streaming. This is separate from
    # MEDIA_MAX_BYTES, which is the aggregate disposable-media volume ceiling.
    direct_image_max_bytes: int = Field(
        default=50 * 1024**2,
        ge=1024**2,
        le=100 * 1024**2,
        alias="DIRECT_IMAGE_MAX_BYTES",
    )

    # --- Ads ---
    ads_enabled: bool = Field(default=True, alias="ADS_ENABLED")

    # --- Analytics ---
    # First-party, privacy-conscious web analytics - see app/services/
    # analytics_service.py and docs/ANALYTICS.md. Raw events are purged after
    # this many days by the existing periodic media-cleanup task; there is no
    # separate aggregated/long-term table in V1 (see docs/ANALYTICS.md
    # "Scaling considerations" for the documented upgrade path).
    analytics_retention_days: int = Field(default=90, ge=1, le=365, alias="ANALYTICS_RETENTION_DAYS")

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
            # This does NOT block or fall back to Sandbox - paddle_client.py's
            # _base_url() genuinely switches to https://api.paddle.com (Paddle
            # Live) for any value other than "sandbox". The log message used
            # to claim this was "refused," which was never true; it's a
            # go-live notice, not a safety interlock.
            logger.warning(
                "PADDLE_ENV=%s - Paddle API calls now target the LIVE endpoint "
                "(https://api.paddle.com), not Sandbox. Confirm this is "
                "intentional and that PADDLE_API_KEY, PADDLE_CLIENT_TOKEN, "
                "PADDLE_WEBHOOK_SECRET, and all four price IDs are genuine "
                "Paddle Live values before accepting real payments.",
                _settings.paddle_env,
            )
    return _settings
