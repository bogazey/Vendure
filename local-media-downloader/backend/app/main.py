"""FastAPI application entrypoint.

Binds to 127.0.0.1 only; CORS is restricted to the local Vite dev server /
built frontend origins. No endpoint here reads arbitrary files or executes
arbitrary commands.
"""
from __future__ import annotations

import asyncio
import traceback
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import (
    routes_account,
    routes_ads,
    routes_admin,
    routes_admin_analytics,
    routes_analytics,
    routes_analyze,
    routes_auth,
    routes_billing,
    routes_downloads,
    routes_filesystem,
    routes_health,
    routes_history,
    routes_platform_auth,
    routes_progress,
    routes_settings,
)
from app.config.logging_config import get_logger, setup_logging
from app.config.commercial_settings import get_commercial_settings
from app.database import history_repo
from app.database.db import get_connection
from app.services import ytdlp_service
from app.services.media_cleanup_service import periodic_cleanup
from app.utils.exceptions import AppError

setup_logging()
logger = get_logger("main")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    get_connection()  # creates schema if needed

    # Any history row still "in progress" means the app was killed mid-download
    # last time it ran (crash, force quit, `pkill`). Mark those failed now so
    # they don't sit "downloading" forever and so they're retryable.
    recovered = history_repo.mark_interrupted_as_failed(
        "Interrupted by application restart. You can retry this download."
    )
    if recovered:
        logger.warning("Recovered %d download(s) interrupted by a previous shutdown", recovered)

    ffmpeg_available, ffmpeg_path = ytdlp_service.check_ffmpeg()
    logger.info(
        "Startup: yt-dlp %s, ffmpeg_available=%s (%s)",
        ytdlp_service.get_ytdlp_version(),
        ffmpeg_available,
        ffmpeg_path,
    )

    # Mission 7 (Phase 17): make the Platform Core integration's actual
    # resolved state visible at boot, not just inferable from whether
    # PLATFORM_CLIENT_ID happens to be set - an operator reading startup
    # logs should be able to see at a glance whether auth/entitlements/
    # billing are live, without cross-referencing .env.
    settings = get_commercial_settings()
    logger.info(
        "Platform Core integration: configured=%s auth_enabled=%s entitlements_enabled=%s billing_enabled=%s",
        bool(settings.platform_client_id),
        settings.platform_auth_enabled,
        settings.platform_entitlements_enabled,
        settings.platform_billing_enabled,
    )

    cleanup_task = asyncio.create_task(periodic_cleanup())
    try:
        yield
    finally:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass


# Nginx's path allowlist (see frontend/nginx.conf, frontend/nginx.tls.conf)
# already keeps /docs, /redoc, and /openapi.json unreachable from the public
# internet in production, but that's the only layer doing so - the backend
# container itself has never disabled them. Disable them here too, so the
# interactive schema/API explorer isn't live at the application level if
# that network boundary is ever bypassed or misconfigured. Development/test
# environments (the settings default) keep them, since they're genuinely
# useful there.
_is_production = get_commercial_settings().app_env.strip().lower() == "production"

app = FastAPI(
    title="Local Media Downloader API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
)

LOCAL_ORIGINS = [
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:4173",
    "http://localhost:4173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=LOCAL_ORIGINS,
    # Auth cookies require credentialed CORS; the origin list above still
    # pins this to the local frontend only (allow_credentials=True does NOT
    # imply wildcard origins - FastAPI/Starlette refuses "*" with credentials).
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type"],
)

_MAINTENANCE_EXEMPT_METHODS = {"GET", "HEAD", "OPTIONS"}
_MAINTENANCE_EXEMPT_PATHS = {"/api/health"}


@app.middleware("http")
async def maintenance_mode_middleware(request: Request, call_next):
    """Mission 5, phase 6: a short, operator-toggled maintenance window for
    the production migration cutover (docs/platform/
    PRODUCTION_REHEARSAL_PLAN.md) - re-checked per request (not cached at
    startup) so an operator can flip MAINTENANCE_MODE and have it take
    effect without a restart, matching the "5-15 minute window" the
    rehearsal plan recommends rather than a full redeploy cycle. Read-only
    traffic and health checks are never blocked, so uptime monitoring and
    already-loaded pages keep working during the window."""
    if (
        get_commercial_settings().maintenance_mode
        and request.method not in _MAINTENANCE_EXEMPT_METHODS
        and request.url.path not in _MAINTENANCE_EXEMPT_PATHS
    ):
        return JSONResponse(
            status_code=503,
            content={
                "message": "Loady is temporarily unavailable for scheduled maintenance. Please try again shortly.",
                "technical": None,
                "code": "MAINTENANCE_MODE",
            },
            headers={"Retry-After": "300"},
        )
    return await call_next(request)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    technical = exc.technical if get_commercial_settings().app_env != "production" else None
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": exc.message, "technical": technical, "code": exc.code},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled error on %s: %s\n%s", request.url.path, exc, traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={
            "message": "Something went wrong. Please try again.",
            "technical": str(exc) if get_commercial_settings().app_env != "production" else None,
        },
    )


app.include_router(routes_health.router)
app.include_router(routes_auth.router)
app.include_router(routes_platform_auth.router)
app.include_router(routes_account.router)
app.include_router(routes_billing.router)
app.include_router(routes_admin.router)
app.include_router(routes_admin_analytics.router)
app.include_router(routes_analytics.router)
app.include_router(routes_ads.router)
app.include_router(routes_analyze.router)
app.include_router(routes_downloads.router)
app.include_router(routes_history.router)
app.include_router(routes_settings.router)
app.include_router(routes_filesystem.router)
app.include_router(routes_progress.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
