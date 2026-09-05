"""System-wide settings shared by every account (concurrency, theme, audio/
video presets, timeouts). Auth-gated so this isn't a completely open
read/write on shared server config to anyone unauthenticated.

`download_dir` is the one field on AppSettings that is NOT actually
per-account-editable in commercial mode any more: GET always returns the
caller's own, non-configurable <DOWNLOAD_ROOT>/<user_id>/ directory (see
user_storage_service.py), and PUT rejects any attempt to change it. The
rest of AppSettings genuinely IS still one shared row across every
account, which is a real, documented, not-yet-fixed limitation for a true
multi-tenant deployment - see COMMERCIAL_ARCHITECTURE.md §4.1.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.database.commercial_models import User
from app.models.schemas import AppSettings, UpdateSettingsRequest
from app.services.settings_service import get_settings, update_settings
from app.services.user_storage_service import user_download_dir
from app.utils.exceptions import InvalidPathError

router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=AppSettings)
async def read_settings(user: User = Depends(get_current_user)) -> AppSettings:
    settings = get_settings()
    return settings.model_copy(update={"download_dir": str(user_download_dir(user.id))})


@router.put("", response_model=AppSettings)
async def write_settings(
    patch: UpdateSettingsRequest, user: User = Depends(get_current_user)
) -> AppSettings:
    if "download_dir" in patch.model_dump(exclude_unset=True):
        raise InvalidPathError(
            "Your download location is managed automatically and can't be changed here."
        )
    try:
        settings = update_settings(patch)
    except ValueError as exc:
        raise InvalidPathError(str(exc)) from exc
    return settings.model_copy(update={"download_dir": str(user_download_dir(user.id))})
