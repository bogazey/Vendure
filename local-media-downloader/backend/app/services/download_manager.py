"""In-process download queue: job lifecycle, concurrency, progress, cancellation.

Active jobs live in memory (they are inherently tied to this running process);
completed/failed/cancelled jobs are persisted to the SQLite history table.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yt_dlp
from yt_dlp.utils import DownloadCancelled

from app.config.logging_config import get_logger
from app.database import history_repo
from app.models.enums import DownloadStage, MediaType, Platform
from app.models.schemas import AppSettings, CreateDownloadRequest, DownloadJobOut
from app.services import ytdlp_service
from app.services.settings_service import get_settings
from app.utils.exceptions import FfmpegMissingError, JobNotFoundError, UnavailableMediaError
from app.utils.paths import resolve_safe_directory, validate_directory_writable
from app.utils.url_detect import detect_platform

logger = get_logger("download_manager")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DownloadJob:
    id: str
    request: CreateDownloadRequest
    platform: Platform
    title: Optional[str] = None
    uploader: Optional[str] = None
    thumbnail: Optional[str] = None
    stage: DownloadStage = DownloadStage.QUEUED
    progress_percent: float = 0.0
    speed_bps: Optional[float] = None
    downloaded_bytes: Optional[int] = None
    total_bytes: Optional[int] = None
    eta_seconds: Optional[int] = None
    filepath: Optional[str] = None
    error_message: Optional[str] = None
    error_technical: Optional[str] = None
    created_at: str = field(default_factory=_now_iso)
    completed_at: Optional[str] = None
    cancel_event: threading.Event = field(default_factory=threading.Event)

    def to_out(self) -> DownloadJobOut:
        return DownloadJobOut(
            id=self.id,
            url=self.request.url,
            platform=self.platform,
            title=self.title,
            uploader=self.uploader,
            thumbnail=self.thumbnail,
            media_type=self.request.media_type,
            stage=self.stage,
            progress_percent=round(self.progress_percent, 1),
            speed_bps=self.speed_bps,
            downloaded_bytes=self.downloaded_bytes,
            total_bytes=self.total_bytes,
            eta_seconds=self.eta_seconds,
            filepath=self.filepath,
            error_message=self.error_message,
            created_at=self.created_at,
            completed_at=self.completed_at,
        )


class DownloadManager:
    def __init__(self) -> None:
        self._jobs: dict[str, DownloadJob] = {}
        self._lock = threading.Lock()
        self._revision = 0
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._semaphore_limit: int = 0

    def _bump_revision(self) -> None:
        with self._lock:
            self._revision += 1

    @property
    def revision(self) -> int:
        with self._lock:
            return self._revision

    def list_jobs(self) -> list[DownloadJobOut]:
        with self._lock:
            jobs = list(self._jobs.values())
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return [j.to_out() for j in jobs]

    def get_job(self, job_id: str) -> DownloadJob:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise JobNotFoundError("Download job not found.")
        return job

    async def _get_semaphore(self) -> asyncio.Semaphore:
        settings = get_settings()
        if self._semaphore is None or self._semaphore_limit != settings.max_concurrent_downloads:
            self._semaphore = asyncio.Semaphore(settings.max_concurrent_downloads)
            self._semaphore_limit = settings.max_concurrent_downloads
        return self._semaphore

    def create_job(self, request: CreateDownloadRequest) -> DownloadJob:
        platform = detect_platform(request.url)
        job = DownloadJob(id=str(uuid.uuid4()), request=request, platform=platform)
        with self._lock:
            self._jobs[job.id] = job
            self._revision += 1
        asyncio.create_task(self._run_job(job.id))
        return job

    def cancel_job(self, job_id: str) -> None:
        job = self.get_job(job_id)
        job.cancel_event.set()
        logger.info("Cancellation requested for job %s", job_id)

    def retry_job(self, history_id: str) -> DownloadJob:
        record = history_repo.get(history_id)
        if record is None:
            raise JobNotFoundError("History record not found.")
        raw = history_repo.get_request_json(history_id)
        if raw:
            request = CreateDownloadRequest(**json.loads(raw))
        else:
            request = CreateDownloadRequest(url=record.url)
        return self.create_job(request)

    async def _run_job(self, job_id: str) -> None:
        job = self.get_job(job_id)
        semaphore = await self._get_semaphore()
        async with semaphore:
            if job.cancel_event.is_set():
                self._finish_as_cancelled(job)
                return
            try:
                job.stage = DownloadStage.ANALYZING
                self._bump_revision()
                settings = get_settings()
                await asyncio.to_thread(self._blocking_download, job, settings)
                self._finish_as_completed(job)
            except DownloadCancelled:
                self._finish_as_cancelled(job)
            except Exception as exc:  # noqa: BLE001 - centralizing error classification
                friendly = ytdlp_service.classify_error(exc, job.request.url)
                self._finish_as_failed(job, friendly)

    def _blocking_download(self, job: DownloadJob, settings: AppSettings) -> None:
        ffmpeg_available, _ = ytdlp_service.check_ffmpeg()
        if not ffmpeg_available:
            raise FfmpegMissingError(
                "FFmpeg was not found on this system. Install it and try again."
            )

        download_dir = resolve_safe_directory(settings.download_dir)
        ok, reason = validate_directory_writable(download_dir)
        if not ok:
            raise PermissionError(reason or "Download folder is not writable.")

        def progress_hook(d: dict) -> None:
            if job.cancel_event.is_set():
                raise DownloadCancelled("Cancelled by user")
            status = d.get("status")
            if status == "downloading":
                job.stage = DownloadStage.DOWNLOADING
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                downloaded = d.get("downloaded_bytes")
                job.downloaded_bytes = downloaded
                job.total_bytes = total
                job.speed_bps = d.get("speed")
                eta = d.get("eta")
                job.eta_seconds = int(eta) if eta is not None else None
                if total:
                    job.progress_percent = min(99.0, (downloaded or 0) / total * 100)
            elif status == "finished":
                job.progress_percent = 100.0
                filename = d.get("filename")
                if filename:
                    job.filepath = filename
            self._bump_revision()

        def postprocessor_hook(d: dict) -> None:
            pp = (d.get("postprocessor") or "").lower()
            status = d.get("status")
            if status == "started":
                if "merger" in pp:
                    job.stage = DownloadStage.MERGING
                elif "extractaudio" in pp or "ffmpeg" in pp:
                    job.stage = DownloadStage.CONVERTING
            if status == "finished":
                info = d.get("info_dict") or {}
                filepath = info.get("filepath")
                if filepath:
                    job.filepath = filepath
            self._bump_revision()

        output_template = str(download_dir / "%(title).150B [%(id)s].%(ext)s")

        opts = ytdlp_service.build_download_opts(
            job.request, settings, output_template, progress_hook, postprocessor_hook
        )

        job.stage = DownloadStage.DOWNLOADING
        self._bump_revision()

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(job.request.url, download=True)
            if info is None:
                raise UnavailableMediaError(
                    "No media information could be extracted from this URL."
                )
            job.title = info.get("title") or job.title
            job.uploader = info.get("uploader") or info.get("channel") or job.uploader
            job.thumbnail = info.get("thumbnail") or job.thumbnail
            if not job.filepath:
                try:
                    job.filepath = ydl.prepare_filename(info)
                except Exception:  # noqa: BLE001
                    pass

    def _finish_as_completed(self, job: DownloadJob) -> None:
        job.stage = DownloadStage.COMPLETED
        job.progress_percent = 100.0
        job.completed_at = _now_iso()
        self._bump_revision()
        self._save_history(job)
        logger.info("Job %s completed", job.id)

    def _finish_as_cancelled(self, job: DownloadJob) -> None:
        job.stage = DownloadStage.CANCELLED
        job.completed_at = _now_iso()
        job.error_message = "Cancelled by user."
        self._bump_revision()
        self._save_history(job)
        logger.info("Job %s cancelled", job.id)

    def _finish_as_failed(self, job: DownloadJob, exc: Exception) -> None:
        job.stage = DownloadStage.FAILED
        job.completed_at = _now_iso()
        job.error_message = getattr(exc, "message", str(exc))
        job.error_technical = getattr(exc, "technical", None)
        self._bump_revision()
        self._save_history(job)
        logger.error("Job %s failed: %s", job.id, job.error_message)

    def _save_history(self, job: DownloadJob) -> None:
        filesize = None
        if job.filepath:
            try:
                filesize = Path(job.filepath).stat().st_size
            except OSError:
                filesize = None
        resolution = None
        if job.request.quality_key and job.request.quality_key not in ("best", "mp3", "m4a"):
            resolution = f"{job.request.quality_key}p"
        format_label = (
            (job.request.audio_format or "audio").upper()
            if job.request.media_type == MediaType.AUDIO
            else (resolution or "Best Available")
        )
        history_repo.upsert(
            {
                "id": job.id,
                "url": job.request.url,
                "platform": job.platform.value,
                "title": job.title,
                "uploader": job.uploader,
                "thumbnail": job.thumbnail,
                "format_label": format_label,
                "resolution": resolution,
                "filepath": job.filepath,
                "filesize": filesize,
                "created_at": job.created_at,
                "completed_at": job.completed_at,
                "status": job.stage.value,
                "error_message": job.error_message,
                "request_json": job.request.model_dump_json(),
            }
        )


manager = DownloadManager()
