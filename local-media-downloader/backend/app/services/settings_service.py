"""Application settings service: defaults + persistence + validation."""
from __future__ import annotations

from app.config.paths import DEFAULT_DOWNLOAD_DIR
from app.config.logging_config import get_logger
from app.database import settings_repo
from app.models.schemas import AppSettings, UpdateSettingsRequest
from app.utils.paths import resolve_safe_directory, validate_directory_writable

logger = get_logger("settings")

_SETTINGS_KEY = "app_settings"


def get_settings() -> AppSettings:
    stored = settings_repo.load_all().get(_SETTINGS_KEY)
    if stored:
        try:
            return AppSettings(**stored)
        except Exception:
            logger.warning("Stored settings failed validation; falling back to defaults")
    return AppSettings(download_dir=str(DEFAULT_DOWNLOAD_DIR))


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
    new_settings = AppSettings(**data)
    settings_repo.save_all({_SETTINGS_KEY: new_settings.model_dump()})
    logger.info("Settings updated")
    return new_settings
