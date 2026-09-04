"""System-wide settings shared by every account (download folder,
concurrency, theme, audio/video presets, timeouts). Auth-gated so this
isn't a completely open read/write on shared server config to anyone
unauthenticated - but note these fields genuinely ARE still one shared row
across every account (unlike container_mode/cookie_source, see
app/services/user_preferences_service.py), which is a real, documented,
not-yet-fixed limitation for a true multi-tenant deployment - see
COMMERCIAL_ARCHITECTURE.md §4.1."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models.schemas import AppSettings, UpdateSettingsRequest
from app.services.settings_service import get_settings, update_settings
from app.utils.exceptions import InvalidPathError

router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=AppSettings)
async def read_settings() -> AppSettings:
    return get_settings()


@router.put("", response_model=AppSettings)
async def write_settings(patch: UpdateSettingsRequest) -> AppSettings:
    try:
        return update_settings(patch)
    except ValueError as exc:
        raise InvalidPathError(str(exc)) from exc
