from __future__ import annotations

from fastapi import APIRouter

from app.models.schemas import CreateDownloadRequest, DownloadJobOut
from app.services.download_manager import manager
from app.utils.exceptions import UnsupportedUrlError
from app.utils.url_detect import detect_platform, is_supported_platform, is_valid_url

router = APIRouter(prefix="/api/downloads", tags=["downloads"])


@router.post("", response_model=DownloadJobOut, status_code=201)
async def create_download(request: CreateDownloadRequest) -> DownloadJobOut:
    if not is_valid_url(request.url):
        raise UnsupportedUrlError("That doesn't look like a valid URL.")
    if not is_supported_platform(detect_platform(request.url)):
        raise UnsupportedUrlError(
            "This URL isn't supported. Only YouTube, TikTok, Instagram, and Facebook links are supported."
        )
    job = manager.create_job(request)
    return job.to_out()


@router.get("", response_model=list[DownloadJobOut])
async def list_downloads() -> list[DownloadJobOut]:
    return manager.list_jobs()


@router.get("/{job_id}", response_model=DownloadJobOut)
async def get_download(job_id: str) -> DownloadJobOut:
    job = manager.get_job(job_id)
    return job.to_out()


@router.post("/{job_id}/cancel", response_model=DownloadJobOut)
async def cancel_download(job_id: str) -> DownloadJobOut:
    manager.cancel_job(job_id)
    job = manager.get_job(job_id)
    return job.to_out()


@router.post("/{job_id}/retry", response_model=DownloadJobOut, status_code=201)
async def retry_download(job_id: str) -> DownloadJobOut:
    job = manager.retry_job(job_id)
    return job.to_out()
