"""Application settings service: defaults + persistence + validation."""
from __future__ import annotations

from pathlib import Path
import os

from app.config.paths import DEFAULT_DOWNLOAD_DIR
from app.config.logging_config import get_logger
from app.database import settings_repo
from app.models.enums import CookieSource
from app.models.schemas import AppSettings, UpdateSettingsRequest
from app.utils.paths import resolve_safe_directory, validate_directory_writable

logger = get_logger("settings")

_SETTINGS_KEY = "app_settings"


def get_settings() -> AppSettings:
    configured_cap = os.environ.get("LMD_MAX_CONCURRENT_DOWNLOADS")
    stored = settings_repo.load_all().get(_SETTINGS_KEY)
    if stored:
        try:
            settings = AppSettings(**stored)
            if configured_cap is not None:
                cap = max(1, min(10, int(configured_cap)))
                if settings.max_concurrent_downloads > cap:
                    logger.warning(
                        "Capping persisted media concurrency %d at configured production limit %d",
                        settings.max_concurrent_downloads,
                        cap,
                    )
                    settings = settings.model_copy(update={"max_concurrent_downloads": cap})
            return settings
        except Exception:
            logger.warning("Stored settings failed validation; falling back to defaults")
    default_concurrency = int(configured_cap or "2")
    return AppSettings(download_dir=str(DEFAULT_DOWNLOAD_DIR), max_concurrent_downloads=default_concurrency)


def update_settings(patch: UpdateSettingsRequest) -> AppSettings:
    current = get_settings()
    data = current.model_dump()
    patch_data = patch.model_dump(exclude_unset=True, exclude_none=True)

    if "download_dir" in patch_data:
        resolved = resolve_safe_directory(patch_data["download_dir"])
        ok, reason = validate_directory_writable(resolved)
        if not ok:
            raise ValueError(reason or "Invalid download directory.")
        patch_data["download_dir"] = str(resolved)

    data.update(patch_data)

    if data.get("cookie_source") == CookieSource.FILE and data.get("cookie_file_path"):
        cookie_path = Path(data["cookie_file_path"]).expanduser()
        if not cookie_path.is_file():
            raise ValueError(
                "Cookie file not found at that path. Check Settings → Authentication."
            )

    new_settings = AppSettings(**data)
    settings_repo.save_all({_SETTINGS_KEY: new_settings.model_dump()})
    logger.info("Settings updated")
    return new_settings
