"""Platform Core FastAPI application entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import routes_admin, routes_auth, routes_oauth, routes_pages, routes_v1
from app.config.logging_config import get_logger, setup_logging
from app.database.db import get_session_factory
from app.database.seed_roles import ensure_roles
from app.utils.exceptions import AppError

setup_logging()
logger = get_logger("main")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    session = get_session_factory()()
    try:
        ensure_roles(session)
    finally:
        session.close()
    logger.info("Platform Core startup complete.")
    yield


app = FastAPI(title="Platform Core API", version="0.1.0", lifespan=lifespan)

# CORS: an explicit local-dev allowlist, never a wildcard with credentials
# (mirrors Loady's own CORS posture) — the demo product frontends and any
# future account-portal SPA are the only expected browser-side callers of
# the JSON API; the /login, /signup, /oauth/* endpoints are same-origin
# top-level navigations and don't need CORS at all.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8100", "http://127.0.0.1:8100",
        "http://localhost:8101", "http://127.0.0.1:8101",
        "http://localhost:8102", "http://127.0.0.1:8102",
        "http://localhost:5273", "http://127.0.0.1:5273",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message})


app.include_router(routes_pages.router)
app.include_router(routes_auth.router)
app.include_router(routes_oauth.router)
app.include_router(routes_v1.router)
app.include_router(routes_admin.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
