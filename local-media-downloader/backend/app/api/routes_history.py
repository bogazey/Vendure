from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.config.logging_config import get_logger
from app.database import history_repo
from app.models.schemas import ClearHistoryRequest, HistoryRecordOut
from app.utils.exceptions import InvalidPathError

router = APIRouter(prefix="/api/history", tags=["history"])
logger = get_logger("history_api")


@router.get("", response_model=list[HistoryRecordOut])
async def list_history(
    search: Optional[str] = Query(default=None),
    platform: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    order: str = Query(default="newest", pattern="^(newest|oldest)$"),
) -> list[HistoryRecordOut]:
    return history_repo.list_records(search=search, platform=platform, status=status, order=order)


@router.delete("/{record_id}", status_code=204, response_model=None)
async def delete_history_record(record_id: str, delete_file: bool = False) -> None:
    if delete_file:
        record = history_repo.get(record_id)
        if record and record.filepath:
            from pathlib import Path

            path = Path(record.filepath)
            try:
                if path.is_file():
                    path.unlink()
            except OSError as exc:
                raise InvalidPathError(f"Could not delete file: {exc}") from exc
    history_repo.delete(record_id)


@router.post("/clear", status_code=204, response_model=None)
async def clear_history(request: ClearHistoryRequest) -> None:
    from pathlib import Path

    records = history_repo.clear_all()
    if request.delete_files:
        for record in records:
            if record.filepath:
                try:
                    path = Path(record.filepath)
                    if path.is_file():
                        path.unlink()
                except OSError as exc:
                    logger.warning("Could not delete file for history %s: %s", record.id, exc)
