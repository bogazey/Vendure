from __future__ import annotations

from fastapi import APIRouter

from app.models.schemas import AppSettings, UpdateSettingsRequest
from app.services.settings_service import get_settings, update_settings
from app.utils.exceptions import InvalidPathError

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=AppSettings)
async def read_settings() -> AppSettings:
    return get_settings()


@router.put("", response_model=AppSettings)
async def write_settings(patch: UpdateSettingsRequest) -> AppSettings:
    try:
        return update_settings(patch)
    except ValueError as exc:
        raise InvalidPathError(str(exc)) from exc
