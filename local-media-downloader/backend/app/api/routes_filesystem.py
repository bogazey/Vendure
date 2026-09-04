from __future__ import annotations

from fastapi import APIRouter

from app.models.schemas import OpenPathRequest, ValidateFolderRequest, ValidateFolderResponse
from app.services import filesystem_service
from app.utils.paths import resolve_safe_directory, validate_directory_writable

router = APIRouter(prefix="/api/fs", tags=["filesystem"])


@router.post("/open", status_code=204, response_model=None)
async def open_path(request: OpenPathRequest) -> None:
    filesystem_service.open_path(request.path)


@router.post("/open-folder", status_code=204, response_model=None)
async def open_containing_folder(request: OpenPathRequest) -> None:
    filesystem_service.open_containing_folder(request.path)


@router.post("/validate-folder", response_model=ValidateFolderResponse)
async def validate_folder(request: ValidateFolderRequest) -> ValidateFolderResponse:
    try:
        resolved = resolve_safe_directory(request.path)
    except ValueError as exc:
        return ValidateFolderResponse(valid=False, reason=str(exc))
    ok, reason = validate_directory_writable(resolved)
    return ValidateFolderResponse(valid=ok, reason=reason, resolved_path=str(resolved) if ok else None)
