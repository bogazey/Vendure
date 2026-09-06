"""Strictly bounded retention cleanup for disposable downloaded media."""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

from app.config.commercial_settings import get_commercial_settings
from app.config.logging_config import get_logger
from app.database.commercial_db import session_scope
from app.services import guest_service
from app.services.download_manager import manager
from app.services.guest_storage_service import remove_guest_dir
from app.utils.paths import is_within

logger = get_logger("media_cleanup")
_TEMP_SUFFIXES = {".part", ".ytdl", ".tmp", ".temp"}
_TEMP_MARKERS = (".part-", ".ffmpeg-", ".temp-")


def _is_temp_artifact(path: Path) -> bool:
    name = path.name.lower()
    return path.suffix.lower() in _TEMP_SUFFIXES or any(marker in name for marker in _TEMP_MARKERS)


def cleanup_media_files(*, now: float | None = None, active_paths: set[Path] | None = None) -> int:
    settings = get_commercial_settings()
    root = Path(settings.download_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    current = now if now is not None else time.time()
    active = {path.resolve() for path in (active_paths or set())}
    removed = 0

    for path in root.rglob("*"):
        try:
            if path.is_symlink() or not path.is_file():
                continue
            resolved = path.resolve()
            if not is_within(resolved, root) or resolved in active:
                continue
            age = current - path.stat().st_mtime
            is_temp = _is_temp_artifact(path)
            if is_temp and age >= settings.partial_media_ttl_hours * 3600:
                path.unlink()
                removed += 1
            elif "_guests" not in resolved.relative_to(root).parts and age >= settings.authenticated_media_ttl_hours * 3600:
                path.unlink()
                removed += 1
        except OSError:
            logger.exception("Could not clean media artifact under DOWNLOAD_ROOT")

    for directory in sorted((p for p in root.rglob("*") if p.is_dir() and not p.is_symlink()), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            pass
    return removed


def cleanup_once() -> None:
    session = session_scope()
    try:
        expired_guest_ids = guest_service.cleanup_expired(session)
        session.commit()
    except Exception:
        session.rollback()
        expired_guest_ids = []
        logger.exception("Guest retention cleanup failed")
    finally:
        session.close()
    for guest_id in expired_guest_ids:
        remove_guest_dir(guest_id)
    removed = cleanup_media_files(active_paths=manager.active_filepaths())
    if expired_guest_ids or removed:
        logger.info("Media cleanup removed %d expired guest directories and %d stale files", len(expired_guest_ids), removed)


async def periodic_cleanup() -> None:
    interval = max(1, get_commercial_settings().media_cleanup_interval_minutes) * 60
    while True:
        try:
            await asyncio.to_thread(cleanup_once)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Periodic media cleanup failed")
        await asyncio.sleep(interval)
