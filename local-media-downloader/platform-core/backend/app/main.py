"""Platform Core FastAPI application entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from sqlalchemy import text

from app.api import routes_admin, routes_auth, routes_billing, routes_oauth, routes_pages, routes_service, routes_v1
from app.config.logging_config import get_logger, setup_logging
from app.config.settings import get_settings
from app.database.db import get_engine, get_session_factory
from app.database.seed_roles import ensure_roles
from app.security.jwt_keys import signing_key_is_available, validate_signing_key_material
from app.utils.exceptions import AppError

setup_logging()
logger = get_logger("main")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Fail closed immediately if this environment cannot obtain a signing
    # key, rather than booting successfully and only failing on the first
    # login/token request (mission 4, phase 3).
    validate_signing_key_material()

    session = get_session_factory()()
    try:
        ensure_roles(session)
    finally:
        session.close()
    logger.info("Platform Core startup complete.", extra={"app_env": get_settings().app_env})
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
app.include_router(routes_billing.router)
app.include_router(routes_service.router)


@app.get("/health")
async def health() -> dict:
    """Liveness only: the process is up and able to answer HTTP requests.
    Never checks dependencies — a dependency outage must not make the
    container itself look unhealthy and get restart-looped."""
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> JSONResponse:
    """Readiness (mission 4, phase 8): are this process's critical
    dependencies actually usable right now? Checked fresh on every call —
    deliberately not cached — since this drives load-balancer/orchestrator
    routing decisions. Never returns secrets or internal exception text."""
    checks: dict[str, bool] = {}

    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception as exc:  # noqa: BLE001 - readiness must never crash on a dependency failure
        checks["database"] = False
        logger.warning("Readiness check: database unavailable: %s", type(exc).__name__)

    checks["signing_key"] = signing_key_is_available()

    healthy = all(checks.values())
    return JSONResponse(status_code=200 if healthy else 503, content={"status": "ok" if healthy else "not_ready", "checks": checks})
