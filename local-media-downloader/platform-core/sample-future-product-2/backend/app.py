"""Sample Future Product 2 - a brand-new ecosystem product onboarded
entirely through the Grand Admin UI (never the CLI, never by editing
Platform Core source). Proves two things end to end:

1. The Grand Admin product-onboarding flow (product + OAuth client +
   one-time secret) actually produces a working, usable client.
2. `@platform-core/react-client` (platform-core/sdk/react) works against a
   real backend built on `platform_client` (platform-core/sdk/python),
   without copying Loady/demo-product-a's integration code - only the
   documented contract (GET /api/platform/session, GET
   /api/platform/entitlements, POST /api/platform/logout) is shared.

This backend does the real Authorization Code + PKCE exchange against a
running Platform Core instance (same as demo-product-a/b), but exposes a
JSON API for a real React frontend instead of server-rendered HTML.
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
import time
from contextvars import ContextVar
from urllib.parse import urlencode

from fastapi import Cookie, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from platform_client import PlatformClient
from platform_client.fastapi_ext import LocalSession, build_platform_router

DEMO_BASE_URL = os.environ.get("DEMO_BASE_URL", "http://localhost:9303")
DEMO_CLIENT_ID = os.environ["DEMO_CLIENT_ID"]
DEMO_CLIENT_SECRET = os.environ["DEMO_CLIENT_SECRET"]
DEMO_PRODUCT_ID = os.environ["DEMO_PRODUCT_ID"]
PLATFORM_AUTH_BASE_URL = os.environ.get("PLATFORM_AUTH_BASE_URL", "http://127.0.0.1:8100")
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5305")
REDIRECT_URI = f"{DEMO_BASE_URL}/auth/callback"

app = FastAPI(title="Sample Future Product 2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

platform_client = PlatformClient(
    base_url=PLATFORM_AUTH_BASE_URL, client_id=DEMO_CLIENT_ID, client_secret=DEMO_CLIENT_SECRET, redirect_uri=REDIRECT_URI,
)

# This product's own local sessions - deliberately never the central
# session, matching every other product in this ecosystem.
# session_id -> {sub, email, email_verified, access_token}
_sessions: dict[str, dict] = {}

# `platform_client.fastapi_ext`'s dependency factories take a zero-argument
# `session_lookup` callable (product-supplied, deliberately storage-
# agnostic per that module's own docstring). This product's storage is an
# httpOnly cookie, so a small per-request contextvar - set by the
# middleware below, read by `_session_lookup` - is how `session_lookup`
# sees "this request's" cookie without FastAPI's own dependency plumbing
# (which `build_platform_router`'s routes, mounted once at import time via
# `include_router`, don't get a chance to receive per-call).
_current_session_cookie: ContextVar[str | None] = ContextVar("_current_session_cookie", default=None)


@app.middleware("http")
async def _stash_session_cookie(request: Request, call_next):
    _current_session_cookie.set(request.cookies.get("sf2_session"))
    return await call_next(request)


def _session_lookup() -> LocalSession | None:
    session = _sessions.get(_current_session_cookie.get() or "")
    if session is None:
        return None
    return LocalSession(sub=session["sub"], email=session["email"], email_verified=session["email_verified"])


def _logout() -> None:
    _sessions.pop(_current_session_cookie.get() or "", None)


app.include_router(
    build_platform_router(platform_client, _session_lookup, product_id=DEMO_PRODUCT_ID, logout=_logout),
    prefix="/api/platform",
)


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:64]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


@app.get("/auth/login")
async def auth_login():
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(24)
    params = {
        "response_type": "code",
        "client_id": DEMO_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": "openid profile",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    resp = RedirectResponse(url=f"{PLATFORM_AUTH_BASE_URL}/oauth/authorize?{urlencode(params)}", status_code=302)
    resp.set_cookie("pkce_verifier", verifier, httponly=True, max_age=300, samesite="lax")
    resp.set_cookie("pkce_state", state, httponly=True, max_age=300, samesite="lax")
    return resp


@app.get("/auth/callback")
async def auth_callback(
    code: str = Query(...),
    state: str = Query(...),
    pkce_verifier: str | None = Cookie(default=None),
    pkce_state: str | None = Cookie(default=None),
):
    if not pkce_verifier or not pkce_state or state != pkce_state:
        return RedirectResponse(url=f"{FRONTEND_ORIGIN}/?error=state_mismatch", status_code=302)

    tokens = platform_client.exchange_code(code=code, code_verifier=pkce_verifier)
    user = platform_client.verify_id_token(tokens.id_token)

    session_id = secrets.token_urlsafe(24)
    _sessions[session_id] = {
        "sub": user.sub, "email": user.email, "email_verified": user.email_verified,
        "access_token": tokens.access_token, "created_at": time.time(),
    }
    resp = RedirectResponse(url=f"{FRONTEND_ORIGIN}/", status_code=302)
    resp.set_cookie("sf2_session", session_id, httponly=True, samesite="lax")
    resp.delete_cookie("pkce_verifier")
    resp.delete_cookie("pkce_state")
    return resp


@app.get("/health")
async def health():
    return {"status": "ok", "product": DEMO_PRODUCT_ID}
