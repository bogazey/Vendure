"""Download job endpoints.

Authenticated users work exactly as before: create_download is gated
through download_gate_service (entitlement checks + atomic credit
reservation) before a job is ever created. An anonymous caller gets the
same downloader with a separate, much smaller allowance instead of a 401 -
gated through guest_service (Free-equivalent feature checks + an atomic
"2 downloads, no credits" reservation, tied to an opaque server-issued
cookie, never a client-supplied id - see api/deps.get_guest_id and
GUEST_COOKIE_NAME below).

Jobs are scoped to their owner everywhere (list/get/cancel/retry): a
mismatched job_id is treated as 404, never a 403, so existence isn't
leaked cross-user - and a guest can never see another guest's (or any
authenticated user's) jobs, since ownership requires an exact id match on
whichever dimension (user_id xor guest_id) the request resolves to. retry
stays authenticated-only: guest jobs are never persisted to history (see
download_manager._save_history), so there is nothing for a guest to retry.
"""
from __future__ import annotations

import json
import mimetypes
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import GUEST_COOKIE_NAME, get_current_user, get_db, get_guest_id, get_optional_user
from app.config.commercial_settings import get_commercial_settings
from app.database import history_repo
from app.database.commercial_models import User
from app.models.commercial_enums import AnalyticsEventType
from app.models.commercial_schemas import GuestQuotaOut
from app.models.schemas import CreateDownloadRequest, DownloadJobOut
from app.services import analytics_service, guest_service, platform_entitlement_service
from app.services.account_service import account_service
from app.services.download_gate_service import download_gate_service
from app.services.download_manager import manager
from app.services.guest_storage_service import ensure_within_guest_dir
from app.services.rate_limit_service import guest_download_limiter
from app.services.user_storage_service import ensure_within_user_dir
from app.utils.exceptions import JobNotFoundError, RateLimitedError, UnsupportedUrlError
from app.utils.url_detect import detect_platform, is_supported_platform, is_valid_url

router = APIRouter(prefix="/api/downloads", tags=["downloads"])

_GUEST_IP_LIMIT = 20
_GUEST_IP_WINDOW_SECONDS = 3600.0


def _completed_file_for_owner(job_id: str, user: Optional[User], guest_id: Optional[str]) -> Path:
    """Resolve a completed download by opaque server record id, never client path."""
    if user is not None:
        record = history_repo.get(job_id, user_id=user.id)
        if record is None or record.status.value != "completed" or not record.filepath:
            raise JobNotFoundError("Completed download not found.")
        path = ensure_within_user_dir(Path(record.filepath), user.id)
    elif guest_id is not None:
        job = manager.get_job(job_id, guest_id=guest_id)
        if job.stage.value != "completed" or not job.filepath:
            raise JobNotFoundError("Completed download not found.")
        path = ensure_within_guest_dir(Path(job.filepath), guest_id)
    else:
        raise JobNotFoundError("Completed download not found.")
    if not path.is_file():
        raise JobNotFoundError("Downloaded file is no longer available.")
    return path


def _validate_url(request: CreateDownloadRequest) -> None:
    if not is_valid_url(request.url):
        raise UnsupportedUrlError("That doesn't look like a valid URL.")
    if not is_supported_platform(detect_platform(request.url)):
        raise UnsupportedUrlError(
            "This URL isn't supported. Only YouTube, TikTok, Instagram, and Facebook links are supported."
        )


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _set_guest_cookie(response: Response, guest_id: str) -> None:
    settings = get_commercial_settings()
    response.set_cookie(
        GUEST_COOKIE_NAME,
        guest_id,
        max_age=settings.guest_data_ttl_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        domain=settings.cookie_domain,
        path="/",
    )


def _record_download_started(
    db: Session, request: CreateDownloadRequest, job_id: str, visitor_id: str,
    user_id: Optional[str], analytics_context: dict,
) -> None:
    analytics_service.record_event(
        db, AnalyticsEventType.DOWNLOAD_STARTED,
        visitor_id=visitor_id, user_id=user_id, job_id=job_id,
        source_platform=detect_platform(request.url).value, media_type=request.media_type.value,
        format=analytics_service.derive_format_label(request), **analytics_context,
    )
    # Commit immediately (see routes_analyze.py for the same reasoning) -
    # get_db()'s end-of-request commit would roll this back too if anything
    # later in the request raises.
    db.commit()


def _gate_and_create(
    request: CreateDownloadRequest, user: User, db: Session, job_id: str,
    visitor_id: str, analytics_context: dict,
) -> DownloadJobOut:
    _validate_url(request)
    plan, subscription = account_service.get_current_plan(db, user.id)
    # Mission 5, phase 3: for a user linked to Platform Core, its
    # authoritative/cached entitlement (never the browser) decides which
    # plan gates this request - see
    # platform_entitlement_service.resolve_effective_plan. A no-op for
    # every account that has never migrated.
    plan, _entitlement_source = platform_entitlement_service.resolve_effective_plan(db, user, plan)

    reservation_id, max_resolution_height = download_gate_service.authorize_and_reserve(
        db, user, plan, subscription, request, job_id
    )
    # Commit the reservation now, before the job can possibly race to
    # commit/refund it in the background - get_db's end-of-request commit
    # happens too late for that race to be safe.
    db.commit()
    _record_download_started(db, request, job_id, visitor_id, user.id, analytics_context)

    job = manager.create_job(
        request, job_id=job_id, user_id=user.id, reservation_id=reservation_id,
        max_resolution_height=max_resolution_height, visitor_id=visitor_id, analytics_context=analytics_context,
    )
    return job.to_out()


def _gate_and_create_guest(
    request: CreateDownloadRequest, guest_id: str, db: Session, job_id: str,
    visitor_id: str, analytics_context: dict,
) -> DownloadJobOut:
    _validate_url(request)
    max_resolution_height = guest_service.authorize_and_reserve(db, guest_id, request)
    db.commit()
    _record_download_started(db, request, job_id, visitor_id, None, analytics_context)

    job = manager.create_job(
        request, job_id=job_id, guest_id=guest_id, max_resolution_height=max_resolution_height,
        visitor_id=visitor_id, analytics_context=analytics_context,
    )
    return job.to_out()


@router.post("", response_model=DownloadJobOut, status_code=201)
async def create_download(
    request: CreateDownloadRequest,
    http_request: Request,
    response: Response,
    user: Optional[User] = Depends(get_optional_user),
    guest_token: Optional[str] = Cookie(default=None, alias=GUEST_COOKIE_NAME),
    db: Session = Depends(get_db),
) -> DownloadJobOut:
    job_id = str(uuid.uuid4())
    visitor_id = analytics_service.ensure_visitor_id(http_request, response)
    analytics_context = {
        "country_code": analytics_service.request_country_code(http_request),
        **analytics_service.request_device_context(http_request),
    }

    if user is not None:
        return _gate_and_create(request, user, db, job_id, visitor_id, analytics_context)

    # Server-side quota (guest_service) is the real enforcement; this is a
    # coarse secondary guard against one IP cycling guest cookies to farm
    # more free downloads than intended - not identity, not fingerprinting.
    if not guest_download_limiter.allow(_client_key(http_request), _GUEST_IP_LIMIT, _GUEST_IP_WINDOW_SECONDS):
        raise RateLimitedError("Too many download attempts from this network. Please try again later.")

    guest_id, is_new = guest_service.resolve_or_create(db, guest_token)
    if is_new:
        db.commit()
        _set_guest_cookie(response, guest_id)
    return _gate_and_create_guest(request, guest_id, db, job_id, visitor_id, analytics_context)


@router.get("/guest-quota", response_model=GuestQuotaOut)
async def get_guest_quota(
    response: Response,
    guest_token: Optional[str] = Cookie(default=None, alias=GUEST_COOKIE_NAME),
    db: Session = Depends(get_db),
) -> GuestQuotaOut:
    """Mints a guest cookie on first call if none exists yet, so the "N free
    downloads" banner can render correctly before any download is
    attempted. Never called for signed-in users (see AuthContext usage)."""
    guest_id, is_new = guest_service.resolve_or_create(db, guest_token)
    if is_new:
        db.commit()
        _set_guest_cookie(response, guest_id)
    used, limit = guest_service.get_quota_status(db, guest_id)
    return GuestQuotaOut(remaining=max(0, limit - used), limit=limit)


@router.get("/{job_id}/file", response_class=FileResponse)
async def download_file(
    job_id: str,
    user: Optional[User] = Depends(get_optional_user),
    guest_id: Optional[str] = Depends(get_guest_id),
) -> FileResponse:
    path = _completed_file_for_owner(job_id, user, guest_id)
    media_type, _ = mimetypes.guess_type(path.name)
    return FileResponse(path=path, filename=path.name, media_type=media_type or "application/octet-stream")


@router.get("", response_model=list[DownloadJobOut])
async def list_downloads(
    user: Optional[User] = Depends(get_optional_user),
    guest_id: Optional[str] = Depends(get_guest_id),
) -> list[DownloadJobOut]:
    if user is not None:
        return manager.list_jobs(user_id=user.id)
    if guest_id is not None:
        return manager.list_jobs(guest_id=guest_id)
    return []


@router.get("/{job_id}", response_model=DownloadJobOut)
async def get_download(
    job_id: str,
    user: Optional[User] = Depends(get_optional_user),
    guest_id: Optional[str] = Depends(get_guest_id),
) -> DownloadJobOut:
    if user is None and guest_id is None:
        raise JobNotFoundError("Download job not found.")
    job = manager.get_job(job_id, user_id=user.id if user else None, guest_id=guest_id)
    return job.to_out()


@router.post("/{job_id}/cancel", response_model=DownloadJobOut)
async def cancel_download(
    job_id: str,
    user: Optional[User] = Depends(get_optional_user),
    guest_id: Optional[str] = Depends(get_guest_id),
) -> DownloadJobOut:
    if user is None and guest_id is None:
        raise JobNotFoundError("Download job not found.")
    manager.cancel_job(job_id, user_id=user.id if user else None, guest_id=guest_id)
    job = manager.get_job(job_id, user_id=user.id if user else None, guest_id=guest_id)
    return job.to_out()


@router.post("/{job_id}/retry", response_model=DownloadJobOut, status_code=201)
async def retry_download(
    job_id: str,
    http_request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DownloadJobOut:
    record = history_repo.get(job_id, user_id=user.id)
    if record is None:
        raise JobNotFoundError("History record not found.")
    raw = history_repo.get_request_json(job_id)
    request = CreateDownloadRequest(**json.loads(raw)) if raw else CreateDownloadRequest(url=record.url)
    new_job_id = str(uuid.uuid4())
    visitor_id = analytics_service.ensure_visitor_id(http_request, response)
    analytics_context = {
        "country_code": analytics_service.request_country_code(http_request),
        **analytics_service.request_device_context(http_request),
    }
    return _gate_and_create(request, user, db, new_job_id, visitor_id, analytics_context)
