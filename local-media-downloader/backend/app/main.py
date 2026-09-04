"""FastAPI application entrypoint.

Binds to 127.0.0.1 only; CORS is restricted to the local Vite dev server /
built frontend origins. No endpoint here reads arbitrary files or executes
arbitrary commands.
"""
from __future__ import annotations

import traceback
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import (
    routes_analyze,
    routes_downloads,
    routes_filesystem,
    routes_health,
    routes_history,
    routes_progress,
    routes_settings,
)
from app.config.logging_config import get_logger, setup_logging
from app.database import history_repo
from app.database.db import get_connection
from app.services import ytdlp_service
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
    yield


app = FastAPI(title="Local Media Downloader API", version="1.0.0", lifespan=lifespan)

LOCAL_ORIGINS = [
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:4173",
    "http://localhost:4173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=LOCAL_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": exc.message, "technical": exc.technical},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled error on %s: %s\n%s", request.url.path, exc, traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={
            "message": "Something went wrong. See the technical details for more information.",
            "technical": str(exc),
        },
    )


app.include_router(routes_health.router)
app.include_router(routes_analyze.router)
app.include_router(routes_downloads.router)
app.include_router(routes_history.router)
app.include_router(routes_settings.router)
app.include_router(routes_filesystem.router)
app.include_router(routes_progress.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
