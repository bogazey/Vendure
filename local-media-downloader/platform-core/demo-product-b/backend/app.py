"""A minimal, real OIDC *client* — not a mock — used only to prove that
Platform Core's SSO actually works end-to-end for a separate product
(mission-brief sections 30/31). Both demo-product-a and demo-product-b run
this exact file; only their environment variables differ (client_id,
port, display name). Nothing about the Platform Core side is faked or
stubbed here: this app performs a real Authorization Code + PKCE exchange
against a running Platform Core instance, verifies the returned tokens'
RS256 signature against Platform Core's real JWKS endpoint, and calls
Platform Core's real `/api/v1/entitlements/me` for the "does this user
have access" question - it never asks Platform Core "give me the user"
directly and just believes it.
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
import time
from html import escape
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import Cookie, FastAPI, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from jwt import PyJWKClient

DEMO_NAME = os.environ.get("DEMO_NAME", "Demo Product")
DEMO_ACCENT = os.environ.get("DEMO_ACCENT", "#3B82F6")
DEMO_BASE_URL = os.environ.get("DEMO_BASE_URL", "http://localhost:9301")
DEMO_CLIENT_ID = os.environ["DEMO_CLIENT_ID"]
DEMO_CLIENT_SECRET = os.environ["DEMO_CLIENT_SECRET"]
DEMO_PRODUCT_ID = os.environ["DEMO_PRODUCT_ID"]
PLATFORM_AUTH_BASE_URL = os.environ.get("PLATFORM_AUTH_BASE_URL", "http://localhost:8100")
REDIRECT_URI = f"{DEMO_BASE_URL}/auth/callback"

app = FastAPI(title=f"{DEMO_NAME} (OIDC client demo)")

# This product's own local sessions - deliberately never the central
# session. session_id -> {sub, email, access_token}.
_sessions: dict[str, dict] = {}
_jwks_client = PyJWKClient(f"{PLATFORM_AUTH_BASE_URL}/.well-known/jwks.json")


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:64]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def _page(body: str) -> HTMLResponse:
    return HTMLResponse(f"""<!doctype html><html><head><meta charset="utf-8">
<title>{escape(DEMO_NAME)}</title>
<style>
  body{{margin:0;min-height:100vh;background:#0b0f1a;color:#e2e8f0;font-family:system-ui,sans-serif;
    display:flex;align-items:center;justify-content:center;}}
  .card{{width:420px;background:rgba(17,24,39,.75);border:1px solid rgba(255,255,255,.08);border-radius:18px;
    padding:32px;box-shadow:0 20px 60px -12px {DEMO_ACCENT}55;}}
  h1{{margin:0 0 4px;font-size:20px;color:{DEMO_ACCENT}}}
  p.sub{{color:#94a3b8;font-size:13px;margin:0 0 20px}}
  a.btn, button{{display:inline-block;margin-top:10px;padding:10px 16px;border-radius:10px;border:none;
    background:{DEMO_ACCENT};color:#0b0f1a;font-weight:600;text-decoration:none;cursor:pointer;font-size:14px}}
  dl{{font-size:13px;color:#cbd3e8}}
  dt{{color:#64748b;margin-top:8px}}
  dd{{margin:0;font-family:monospace;word-break:break-all}}
  .badge{{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;margin-top:4px}}
  .yes{{background:rgba(34,211,238,.15);color:#22d3ee}}
  .no{{background:rgba(255,255,255,.06);color:#94a3b8}}
</style></head><body><div class="card">{body}</div></body></html>""")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request, demo_session: str | None = Cookie(default=None)):
    session = _sessions.get(demo_session or "")
    if not session:
        return _page(f"""
        <h1>{escape(DEMO_NAME)}</h1>
        <p class="sub">This product delegates sign-in to the ecosystem's central identity - no local password exists here.</p>
        <a class="btn" href="/auth/login">Sign in with Central Identity</a>
        """)

    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(
                f"{PLATFORM_AUTH_BASE_URL}/api/v1/entitlements/me",
                headers={"Authorization": f"Bearer {session['access_token']}"},
                timeout=5,
            )
            entitlement = r.json() if r.status_code == 200 else {"entitled": False, "entitlement": None}
        except httpx.HTTPError:
            entitlement = {"entitled": False, "entitlement": None}

    ent = entitlement.get("entitlement")
    badge = (
        f'<span class="badge yes">{escape(ent["plan_slug"] or "")} · {escape(ent["source"])}</span>'
        if entitlement.get("entitled") and ent
        else '<span class="badge no">No active entitlement</span>'
    )
    return _page(f"""
    <h1>{escape(DEMO_NAME)}</h1>
    <p class="sub">Signed in via the central identity - no separate account was created here.</p>
    <dl>
      <dt>Email</dt><dd>{escape(session['email'])}</dd>
      <dt>Global user ID (sub)</dt><dd>{escape(session['sub'])}</dd>
      <dt>Entitlement in {escape(DEMO_PRODUCT_ID)}</dt><dd>{badge}</dd>
    </dl>
    <a class="btn" href="/logout">Sign out of {escape(DEMO_NAME)}</a>
    """)


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
    # Short-lived, httpOnly - never readable by this page's own JavaScript.
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
        return _page("<h1>Sign-in failed</h1><p class='sub'>State mismatch - possible CSRF, aborting.</p>")

    async with httpx.AsyncClient() as client:
        token_r = await client.post(
            f"{PLATFORM_AUTH_BASE_URL}/oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": DEMO_CLIENT_ID,
                "client_secret": DEMO_CLIENT_SECRET,
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "code_verifier": pkce_verifier,
            },
            timeout=5,
        )
    if token_r.status_code != 200:
        return _page(f"<h1>Sign-in failed</h1><p class='sub'>{escape(token_r.text)}</p>")

    tokens = token_r.json()
    signing_key = _jwks_client.get_signing_key_from_jwt(tokens["id_token"])
    claims = jwt.decode(
        tokens["id_token"], signing_key.key, algorithms=["RS256"],
        audience=DEMO_CLIENT_ID, issuer=PLATFORM_AUTH_BASE_URL,
    )

    session_id = secrets.token_urlsafe(24)
    _sessions[session_id] = {
        "sub": claims["sub"], "email": claims["email"], "access_token": tokens["access_token"],
        "created_at": time.time(),
    }
    resp = RedirectResponse(url="/", status_code=302)
    resp.set_cookie("demo_session", session_id, httponly=True, samesite="lax")
    resp.delete_cookie("pkce_verifier")
    resp.delete_cookie("pkce_state")
    return resp


@app.get("/logout")
async def logout(demo_session: str | None = Cookie(default=None)):
    if demo_session:
        _sessions.pop(demo_session, None)
    resp = RedirectResponse(url="/", status_code=302)
    resp.delete_cookie("demo_session")
    return resp


@app.get("/health")
async def health():
    return {"status": "ok", "product": DEMO_PRODUCT_ID}
