from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from app.database.db import database_healthy
from app.config.commercial_settings import get_commercial_settings
from app.models.schemas import HealthResponse
from app.services import ytdlp_service
from app.services.settings_service import get_settings
from app.utils.paths import is_directory_writable

router = APIRouter(tags=["health"])


def compute_health() -> HealthResponse:
    """Single source of truth for backend/ffmpeg/yt-dlp/database health.

    Returns the full HealthResponse, including local filesystem paths
    (ffmpeg_path, download_dir) needed by same-machine consumers like
    Settings/FirstRunSetup. The admin System page must never display those
    paths - see routes_admin.get_admin_health, which calls this and strips
    them rather than reusing /api/health's payload as-is.
    """
    settings = get_settings()
    ffmpeg_available, ffmpeg_path = ytdlp_service.check_ffmpeg()
    writable = is_directory_writable(Path(settings.download_dir))

    try:
        version = ytdlp_service.get_ytdlp_version()
    except Exception:  # noqa: BLE001
        version = None

    db_ok = database_healthy()

    production = get_commercial_settings().app_env.lower() == "production"
    return HealthResponse(
        status="ok" if (ffmpeg_available and db_ok) else "degraded",
        ytdlp_version=version,
        ffmpeg_available=ffmpeg_available,
        ffmpeg_path=None if production else ffmpeg_path,
        download_dir="" if production else settings.download_dir,
        download_dir_writable=writable,
        database_ok=db_ok,
    )


@router.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return compute_health()
