from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.database.commercial_models import User
from app.models.schemas import OpenPathRequest, ValidateFolderRequest, ValidateFolderResponse
from app.services import filesystem_service
from app.utils.paths import resolve_safe_directory, validate_directory_writable

router = APIRouter(prefix="/api/fs", tags=["filesystem"], dependencies=[Depends(get_current_user)])


@router.post("/open", status_code=204, response_model=None)
async def open_path(request: OpenPathRequest, user: User = Depends(get_current_user)) -> None:
    filesystem_service.open_path(request.path, user_id=user.id)


@router.post("/open-folder", status_code=204, response_model=None)
async def open_containing_folder(request: OpenPathRequest, user: User = Depends(get_current_user)) -> None:
    filesystem_service.open_containing_folder(request.path, user_id=user.id)


@router.post("/validate-folder", response_model=ValidateFolderResponse)
async def validate_folder(request: ValidateFolderRequest) -> ValidateFolderResponse:
    try:
        resolved = resolve_safe_directory(request.path)
    except ValueError as exc:
        return ValidateFolderResponse(valid=False, reason=str(exc))
    ok, reason = validate_directory_writable(resolved)
    return ValidateFolderResponse(valid=ok, reason=reason, resolved_path=str(resolved) if ok else None)
