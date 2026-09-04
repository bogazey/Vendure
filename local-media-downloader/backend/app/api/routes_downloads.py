"""Download job endpoints.

Every route here requires a signed-in user. create_download is gated through
download_gate_service (entitlement checks + atomic credit reservation) before
a job is ever created - no plan/credit logic lives in this file. Jobs are
scoped to their owning user everywhere (list/get/cancel/retry): a mismatched
job_id is treated as 404, never a 403, so existence isn't leaked cross-user.
"""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.database import history_repo
from app.database.commercial_models import User
from app.models.schemas import CreateDownloadRequest, DownloadJobOut
from app.services.account_service import account_service
from app.services.download_gate_service import download_gate_service
from app.services.download_manager import manager
from app.utils.exceptions import JobNotFoundError, UnsupportedUrlError
from app.utils.url_detect import detect_platform, is_supported_platform, is_valid_url

router = APIRouter(prefix="/api/downloads", tags=["downloads"])


def _validate_url(request: CreateDownloadRequest) -> None:
    if not is_valid_url(request.url):
        raise UnsupportedUrlError("That doesn't look like a valid URL.")
    if not is_supported_platform(detect_platform(request.url)):
        raise UnsupportedUrlError(
            "This URL isn't supported. Only YouTube, TikTok, Instagram, and Facebook links are supported."
        )


def _gate_and_create(
    request: CreateDownloadRequest, user: User, db: Session
) -> DownloadJobOut:
    _validate_url(request)
    plan, subscription = account_service.get_current_plan(db, user.id)
    job_id = str(uuid.uuid4())

    reservation_id = download_gate_service.authorize_and_reserve(
        db, user, plan, subscription, request, job_id
    )
    # Commit the reservation now, before the job can possibly race to
    # commit/refund it in the background - get_db's end-of-request commit
    # happens too late for that race to be safe.
    db.commit()

    job = manager.create_job(request, job_id=job_id, user_id=user.id, reservation_id=reservation_id)
    return job.to_out()


@router.post("", response_model=DownloadJobOut, status_code=201)
async def create_download(
    request: CreateDownloadRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DownloadJobOut:
    return _gate_and_create(request, user, db)


@router.get("", response_model=list[DownloadJobOut])
async def list_downloads(user: User = Depends(get_current_user)) -> list[DownloadJobOut]:
    return manager.list_jobs(user_id=user.id)


@router.get("/{job_id}", response_model=DownloadJobOut)
async def get_download(job_id: str, user: User = Depends(get_current_user)) -> DownloadJobOut:
    job = manager.get_job(job_id, user_id=user.id)
    return job.to_out()


@router.post("/{job_id}/cancel", response_model=DownloadJobOut)
async def cancel_download(job_id: str, user: User = Depends(get_current_user)) -> DownloadJobOut:
    manager.cancel_job(job_id, user_id=user.id)
    job = manager.get_job(job_id, user_id=user.id)
    return job.to_out()


@router.post("/{job_id}/retry", response_model=DownloadJobOut, status_code=201)
async def retry_download(
    job_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DownloadJobOut:
    record = history_repo.get(job_id, user_id=user.id)
    if record is None:
        raise JobNotFoundError("History record not found.")
    raw = history_repo.get_request_json(job_id)
    request = CreateDownloadRequest(**json.loads(raw)) if raw else CreateDownloadRequest(url=record.url)
    return _gate_and_create(request, user, db)
