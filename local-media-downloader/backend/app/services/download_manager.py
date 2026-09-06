"""In-process download queue: job lifecycle, concurrency, progress, cancellation.

Active jobs live in memory (they are inherently tied to this running process);
completed/failed/cancelled jobs are persisted to the SQLite history table.
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
import yt_dlp
from yt_dlp.utils import DownloadCancelled, sanitize_filename

from app.config.logging_config import get_logger
from app.database import history_repo
from app.database.commercial_db import session_scope
from app.models.enums import ContainerMode, CookieSource, DownloadStage, MediaType, Platform
from app.models.schemas import AppSettings, CreateDownloadRequest, DownloadJobOut
from app.services import guest_service, ytdlp_service
from app.services.guest_storage_service import ensure_within_guest_dir, guest_download_dir
from app.services.settings_service import get_settings
from app.services.usage_service import usage_service
from app.services.user_preferences_service import user_preferences_service
from app.services.user_storage_service import ensure_within_user_dir, user_download_dir
from app.utils.exceptions import (
    FfmpegMissingError,
    FfmpegProcessingError,
    InvalidPathError,
    JobNotFoundError,
    NoDownloadableMediaError,
    UnavailableMediaError,
)
from app.utils.paths import resolve_safe_directory, validate_directory_writable
from app.utils.url_detect import detect_platform

# Checked against the first bytes actually received over the wire before an
# "image" download is accepted - never trust a URL extension or a
# Content-Type header alone (e.g. an expired/blocked CDN link can return an
# HTML error page with a 200 status).
_IMAGE_MAGIC_SIGNATURES: tuple[bytes, ...] = (
    b"\xff\xd8\xff",  # JPEG
    b"\x89PNG\r\n\x1a\n",  # PNG
    b"GIF87a",
    b"GIF89a",
    b"BM",  # BMP
)


def _looks_like_image_bytes(data: bytes) -> bool:
    if any(data.startswith(sig) for sig in _IMAGE_MAGIC_SIGNATURES):
        return True
    return data[:4] == b"RIFF" and data[8:12] == b"WEBP"

# ffmpeg progress/version banners on stderr can be large; keeping ffmpeg quiet
# avoids filling the pipe buffer while _run_ffmpeg polls rather than streams
# it, and keeps the output that IS captured relevant if something fails.
_FFMPEG_QUIET_ARGS = ("-hide_banner", "-loglevel", "error")

logger = get_logger("download_manager")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DownloadJob:
    id: str
    request: CreateDownloadRequest
    platform: Platform
    user_id: Optional[str] = None
    guest_id: Optional[str] = None
    reservation_id: Optional[str] = None
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

    def list_jobs(self, user_id: Optional[str] = None, guest_id: Optional[str] = None) -> list[DownloadJobOut]:
        with self._lock:
            jobs = list(self._jobs.values())
        if user_id is not None:
            jobs = [j for j in jobs if j.user_id == user_id]
        if guest_id is not None:
            jobs = [j for j in jobs if j.guest_id == guest_id]
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return [j.to_out() for j in jobs]

    def get_job(self, job_id: str, user_id: Optional[str] = None, guest_id: Optional[str] = None) -> DownloadJob:
        with self._lock:
            job = self._jobs.get(job_id)
        # Scoped lookups treat "exists but belongs to someone else" the same
        # as "doesn't exist" - never leak another user's (or another
        # guest's) job via a 403 vs 404 distinction. Passing neither
        # user_id nor guest_id is an internal, trusted, unscoped lookup
        # (e.g. _run_job) - route handlers must never call it that way for
        # a fully-anonymous, cookie-less caller (see routes_downloads.py).
        if job is None or (user_id is not None and job.user_id != user_id) or (guest_id is not None and job.guest_id != guest_id):
            raise JobNotFoundError("Download job not found.")
        return job

    async def _get_semaphore(self) -> asyncio.Semaphore:
        settings = get_settings()
        if self._semaphore is None or self._semaphore_limit != settings.max_concurrent_downloads:
            self._semaphore = asyncio.Semaphore(settings.max_concurrent_downloads)
            self._semaphore_limit = settings.max_concurrent_downloads
        return self._semaphore

    def create_job(
        self,
        request: CreateDownloadRequest,
        job_id: Optional[str] = None,
        user_id: Optional[str] = None,
        guest_id: Optional[str] = None,
        reservation_id: Optional[str] = None,
    ) -> DownloadJob:
        platform = detect_platform(request.url)
        job = DownloadJob(
            id=job_id or str(uuid.uuid4()),
            request=request,
            platform=platform,
            user_id=user_id,
            guest_id=guest_id,
            reservation_id=reservation_id,
        )
        with self._lock:
            self._jobs[job.id] = job
            self._revision += 1
        asyncio.create_task(self._run_job(job.id))
        return job

    def cancel_job(self, job_id: str, user_id: Optional[str] = None, guest_id: Optional[str] = None) -> None:
        job = self.get_job(job_id, user_id=user_id, guest_id=guest_id)
        job.cancel_event.set()
        logger.info("Cancellation requested for job %s", job_id)

    def retry_job(self, history_id: str) -> DownloadJob:
        """Lower-level retry with no gating/ownership check - kept for
        programmatic/test use. routes_downloads.retry_download re-implements
        this with an ownership-scoped lookup and a fresh entitlement check
        instead of calling this directly."""
        record = history_repo.get(history_id)
        if record is None:
            raise JobNotFoundError("History record not found.")
        raw = history_repo.get_request_json(history_id)
        if raw:
            request = CreateDownloadRequest(**json.loads(raw))
        else:
            request = CreateDownloadRequest(url=record.url)
        return self.create_job(request)

    def _effective_settings(self, job: DownloadJob) -> AppSettings:
        """Global AppSettings (concurrency, audio/video presets, timeouts,
        ...) with:
        - container_mode/cookie_source/cookie_file_path overridden by this
          job's owning user's own preferences (see user_preferences_service.py
          for why those three fields can never come from the shared row), and
        - download_dir overridden to this user's own, non-configurable
          <DOWNLOAD_ROOT>/<user_id>/ directory (see user_storage_service.py) -
          never the shared global download_dir, which would both mix
          different accounts' files together and let any authenticated user
          redirect downloads to an arbitrary server path."""
        settings = get_settings()
        if job.guest_id:
            # Guests have no preferences row and no plan-derived feature
            # access beyond Free's ceiling (see guest_service) - always
            # Compatibility container mode, never cookies, and always their
            # own isolated <DOWNLOAD_ROOT>/_guests/<guest_id>/ directory.
            guest_dir = guest_download_dir(job.guest_id)
            return settings.model_copy(
                update={
                    "download_dir": str(guest_dir),
                    "container_mode": ContainerMode.COMPATIBILITY,
                    "cookie_source": CookieSource.NONE,
                }
            )
        if not job.user_id:
            return settings
        session = session_scope()
        try:
            effective = user_preferences_service.get_effective_settings(session, job.user_id, settings)
            session.commit()  # persist a lazily-created default row rather than rolling it back on close
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

        user_dir = user_download_dir(job.user_id)
        return effective.model_copy(update={"download_dir": str(user_dir)})

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
                # Persist a non-terminal row now (not just on completion) so a
                # crash mid-download leaves a trace: on next startup, any row
                # still "in progress" gets marked failed and stays retryable
                # instead of vanishing silently (see history_repo.mark_interrupted_as_failed).
                self._save_history(job)
                settings = self._effective_settings(job)
                await asyncio.to_thread(self._blocking_download, job, settings)
                if job.cancel_event.is_set():
                    # The download finished before we could interrupt it (e.g.
                    # cancel was clicked during the final merge/convert step,
                    # which we can't abort mid-flight). Honor the cancellation
                    # after the fact rather than silently reporting success.
                    self._cleanup_cancelled_file(job)
                    self._finish_as_cancelled(job)
                else:
                    self._finish_as_completed(job)
            except DownloadCancelled:
                self._cleanup_cancelled_file(job)
                self._finish_as_cancelled(job)
            except Exception as exc:  # noqa: BLE001 - centralizing error classification
                friendly = ytdlp_service.classify_error(exc, job.request.url)
                self._finish_as_failed(job, friendly)

    def _cleanup_cancelled_file(self, job: DownloadJob) -> None:
        if not job.filepath:
            return
        try:
            path = Path(job.filepath)
            if job.user_id:
                # Defense-in-depth: job.filepath was written by this exact
                # process into this user's own effective download_dir, so
                # this should never actually reject anything - but a
                # cleanup action is exactly the kind of place a future bug
                # (or a job replayed with a stale/tampered filepath) should
                # never be trusted to unlink outside the account it belongs to.
                path = ensure_within_user_dir(path, job.user_id)
            elif job.guest_id:
                path = ensure_within_guest_dir(path, job.guest_id)
            if path.is_file():
                path.unlink()
                logger.info("Removed file for cancelled job %s", job.id)
        except InvalidPathError as exc:
            logger.warning("Refused to remove out-of-bounds file for cancelled job %s: %s", job.id, exc)
        except OSError as exc:
            logger.warning("Could not remove file for cancelled job %s: %s", job.id, exc)

    def _blocking_download(self, job: DownloadJob, settings: AppSettings) -> None:
        if job.request.media_type == MediaType.IMAGE:
            self._blocking_download_image(job, settings)
            return

        ffmpeg_available, _ = ytdlp_service.check_ffmpeg()
        if not ffmpeg_available:
            raise FfmpegMissingError(
                "FFmpeg was not found on this system. Install it and try again."
            )

        download_dir = resolve_safe_directory(settings.download_dir)
        if job.user_id:
            # Belt-and-suspenders: _effective_settings() already computed
            # download_dir as this user's own <DOWNLOAD_ROOT>/<user_id>/,
            # but the actual write to disk is the single most consequential
            # step in this whole flow - never trust a value this many
            # layers removed from its source without re-checking it here too.
            download_dir = ensure_within_user_dir(download_dir, job.user_id)
        elif job.guest_id:
            download_dir = ensure_within_guest_dir(download_dir, job.guest_id)
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

            if job.request.media_type == MediaType.VIDEO and settings.container_mode == ContainerMode.COMPATIBILITY:
                self._ensure_compatible_mp4(job, info)

    def _blocking_download_image(self, job: DownloadJob, settings: AppSettings) -> None:
        """Images never go through yt-dlp's own downloader (it only knows
        how to fetch `formats`, and an image-only extraction has none - see
        ytdlp_service._pick_best_image) or FFmpeg - this fetches the actual
        image bytes directly and validates them before accepting the file."""
        download_dir = resolve_safe_directory(settings.download_dir)
        if job.user_id:
            download_dir = ensure_within_user_dir(download_dir, job.user_id)
        elif job.guest_id:
            download_dir = ensure_within_guest_dir(download_dir, job.guest_id)
        ok, reason = validate_directory_writable(download_dir)
        if not ok:
            raise PermissionError(reason or "Download folder is not writable.")

        info = ytdlp_service.extract_entry_for_download(
            job.request.url, settings, job.request.playlist_item_indices
        )
        image = ytdlp_service.pick_best_image(info)
        if image is None:
            raise NoDownloadableMediaError("This post does not contain downloadable media.")
        image_url, _width, _height, ext = image

        job.title = info.get("title") or job.title
        job.uploader = info.get("uploader") or info.get("channel") or job.uploader
        job.thumbnail = info.get("thumbnail") or image_url or job.thumbnail

        stem = sanitize_filename(f"{(job.title or 'image')[:150]} [{info.get('id') or job.id}]")
        target = self._dedupe_path(download_dir / f"{stem}.{ext}")

        job.stage = DownloadStage.DOWNLOADING
        self._bump_revision()

        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; Loady/1.0)",
            **(info.get("http_headers") or {}),
        }
        self._download_image_file(job, image_url, headers, target, settings)
        job.filepath = str(target)

    @staticmethod
    def _dedupe_path(path: Path) -> Path:
        if not path.exists():
            return path
        stem, suffix = path.stem, path.suffix
        for n in range(1, 1000):
            candidate = path.with_name(f"{stem} ({n}){suffix}")
            if not candidate.exists():
                return candidate
        return path

    def _download_image_file(
        self, job: DownloadJob, url: str, headers: dict[str, str], target: Path, settings: AppSettings
    ) -> None:
        tmp_target = target.with_name(f"{target.name}.part")
        try:
            with httpx.Client(follow_redirects=True, timeout=settings.network_timeout_seconds) as client:
                with client.stream("GET", url, headers=headers) as response:
                    response.raise_for_status()
                    total = int(response.headers.get("content-length") or 0) or None
                    job.total_bytes = total
                    downloaded = 0
                    first_chunk = True
                    with open(tmp_target, "wb") as f:
                        for chunk in response.iter_bytes(chunk_size=65536):
                            if job.cancel_event.is_set():
                                raise DownloadCancelled("Cancelled by user")
                            if first_chunk:
                                if not _looks_like_image_bytes(chunk):
                                    raise NoDownloadableMediaError(
                                        "This post does not contain downloadable media."
                                    )
                                first_chunk = False
                            f.write(chunk)
                            downloaded += len(chunk)
                            job.downloaded_bytes = downloaded
                            if total:
                                job.progress_percent = min(99.0, downloaded / total * 100)
                            self._bump_revision()
                    if first_chunk:
                        # Response body was empty - nothing to validate as an
                        # image, so treat it the same as an invalid response.
                        raise NoDownloadableMediaError("This post does not contain downloadable media.")
        except httpx.HTTPError as exc:
            tmp_target.unlink(missing_ok=True)
            raise UnavailableMediaError(
                "This post is unavailable or you may not have access to it.", technical=str(exc)
            ) from exc
        except Exception:
            tmp_target.unlink(missing_ok=True)
            raise

        tmp_target.replace(target)
        job.progress_percent = 100.0
        self._bump_revision()

    def _ensure_compatible_mp4(self, job: DownloadJob, info: dict) -> None:
        """Compatibility mode's guarantee: a video download always ends in a
        genuine, playable .mp4 - remuxing (fast, lossless) when the source
        codecs are already H.264/AAC, or transcoding via FFmpeg when they
        aren't (e.g. YouTube's VP9/AV1 + Opus streams). Never just renames a
        WebM/MKV file to .mp4."""
        if not job.filepath:
            return
        source = Path(job.filepath)
        if not source.is_file():
            return

        transcode = ytdlp_service.needs_mp4_transcode(info)
        if source.suffix.lower() == ".mp4" and not transcode:
            return  # already a genuine, compatible MP4 - nothing to do

        ffmpeg_available, ffmpeg_path = ytdlp_service.check_ffmpeg()
        if not ffmpeg_available or not ffmpeg_path:
            raise FfmpegMissingError("FFmpeg was not found on this system. Install it and try again.")

        job.stage = DownloadStage.CONVERTING
        self._bump_revision()
        new_path = self._produce_compatible_mp4(job, ffmpeg_path, source, transcode)
        job.filepath = str(new_path)

    def _produce_compatible_mp4(
        self, job: DownloadJob, ffmpeg_path: str, source: Path, transcode: bool
    ) -> Path:
        target = source.with_suffix(".mp4")
        # Guard against the rare case where the source is already named
        # ".mp4" but has incompatible codecs inside (needs_mp4_transcode
        # caught it): ffmpeg can't read and overwrite the same file at once,
        # so convert to a temp name first, then swap it into place.
        collides = target == source
        work_target = target.with_name(f"{target.stem}.compat_tmp.mp4") if collides else target

        if transcode:
            # Genuine re-encode to H.264 + AAC. crf 18 is close to visually
            # lossless (preserves quality) while still being broadly playable;
            # yuv420p maximizes device/player compatibility (some VP9 sources
            # use pixel formats older H.264 decoders choke on).
            args = [
                "-y", *_FFMPEG_QUIET_ARGS, "-i", str(source),
                "-map_metadata", "0",
                "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart",
                str(work_target),
            ]
        else:
            # Codecs are already MP4-compatible; just remux the container
            # losslessly (stream copy, no re-encode).
            args = [
                "-y", *_FFMPEG_QUIET_ARGS, "-i", str(source),
                "-map_metadata", "0",
                "-c", "copy",
                "-movflags", "+faststart",
                str(work_target),
            ]

        self._run_ffmpeg(job, ffmpeg_path, args, work_target)

        if collides:
            work_target.replace(target)
        else:
            try:
                source.unlink()
            except OSError as exc:
                logger.warning("Could not remove intermediate file %s: %s", source, exc)

        return target

    def _run_ffmpeg(self, job: DownloadJob, ffmpeg_path: str, args: list[str], output_path: Path) -> None:
        """Runs ffmpeg, polling job.cancel_event so a cancel click can
        interrupt an in-progress merge/conversion, not just the download."""
        proc = subprocess.Popen(
            [ffmpeg_path, *args], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True
        )
        while proc.poll() is None:
            if job.cancel_event.is_set():
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                output_path.unlink(missing_ok=True)
                raise DownloadCancelled("Cancelled during conversion")
            time.sleep(0.2)

        stderr_output = proc.stderr.read() if proc.stderr else ""
        if proc.returncode != 0:
            output_path.unlink(missing_ok=True)
            raise FfmpegProcessingError(
                "FFmpeg could not convert this video to a compatible MP4.",
                technical=(stderr_output or "").strip()[-4000:] or None,
            )

    def _finalize_usage(self, job: DownloadJob, committed: bool) -> None:
        """Settle this job's credit reservation (authenticated users) or
        guest download-quota reservation (guests): commit it on a genuine
        success, or give it back on failure/cancellation. Runs against the
        commercial DB directly (session_scope) since a background job has no
        FastAPI request-scoped session to reuse."""
        if job.reservation_id:
            session = session_scope()
            try:
                if committed:
                    usage_service.commit(session, job.reservation_id)
                else:
                    usage_service.refund(session, job.reservation_id)
                session.commit()
            except Exception:
                session.rollback()
                logger.exception(
                    "Failed to finalize usage for job %s (reservation %s)", job.id, job.reservation_id
                )
            finally:
                session.close()
        elif job.guest_id:
            session = session_scope()
            try:
                if committed:
                    guest_service.commit_download(session, job.guest_id)
                else:
                    guest_service.refund_download(session, job.guest_id)
                session.commit()
            except Exception:
                session.rollback()
                logger.exception("Failed to finalize guest quota for job %s (guest %s)", job.id, job.guest_id)
            finally:
                session.close()

    def _finish_as_completed(self, job: DownloadJob) -> None:
        job.stage = DownloadStage.COMPLETED
        job.progress_percent = 100.0
        job.completed_at = _now_iso()
        self._bump_revision()
        self._save_history(job)
        self._finalize_usage(job, committed=True)
        logger.info("Job %s completed", job.id)

    def _finish_as_cancelled(self, job: DownloadJob) -> None:
        job.stage = DownloadStage.CANCELLED
        job.completed_at = _now_iso()
        job.error_message = "Cancelled by user."
        self._bump_revision()
        self._save_history(job)
        self._finalize_usage(job, committed=False)
        logger.info("Job %s cancelled", job.id)

    def _finish_as_failed(self, job: DownloadJob, exc: Exception) -> None:
        job.stage = DownloadStage.FAILED
        job.completed_at = _now_iso()
        job.error_message = getattr(exc, "message", str(exc))
        job.error_technical = getattr(exc, "technical", None)
        self._bump_revision()
        self._save_history(job)
        self._finalize_usage(job, committed=False)
        logger.error("Job %s failed: %s", job.id, job.error_message)

    def _save_history(self, job: DownloadJob) -> None:
        if job.guest_id:
            # Guests have no My Downloads page to view it on (still behind
            # ProtectedRoute) and no account to eventually own the record -
            # persisting it would just be an anonymous-browsing data trail
            # with no product purpose. The in-memory DownloadJob is enough
            # for the SSE/progress UI during their session.
            return
        filesize = None
        if job.filepath:
            try:
                filesize = Path(job.filepath).stat().st_size
            except OSError:
                filesize = None
        resolution = None
        if job.request.quality_key and job.request.quality_key not in ("best", "mp3", "m4a"):
            resolution = f"{job.request.quality_key}p"

        if job.request.media_type == MediaType.AUDIO:
            format_label = (job.request.audio_format or "audio").upper()
        elif job.request.media_type == MediaType.IMAGE:
            format_label = "Image"
            if job.filepath:
                container = Path(job.filepath).suffix.lstrip(".").upper()
                if container:
                    format_label = f"Image · {container}"
        else:
            # Record the actual final container, not just the requested
            # quality - Compatibility mode may have transcoded/remuxed to a
            # different container than whatever yt-dlp initially produced.
            format_label = resolution or "Best Available"
            if job.filepath:
                container = Path(job.filepath).suffix.lstrip(".").upper()
                if container:
                    format_label = f"{format_label} · {container}"
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
                "user_id": job.user_id,
            }
        )


manager = DownloadManager()
