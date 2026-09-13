"""OIDC-style endpoints: authorize (browser, redirect-based),
token (server-to-server, confidential client), userinfo, JWKS, and OpenID
discovery. This is the SSO core described in mission-brief section 5 —
Authorization Code + PKCE, no custom protocol.
"""
from __future__ import annotations

from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import BearerPrincipal, get_bearer_principal, get_db, get_optional_user
from app.config.settings import get_settings
from app.database.models import User
from app.security.jwt_keys import get_jwks
from app.services import oidc_service
from app.services.rate_limit_service import oauth_token_limiter
from app.utils.exceptions import AppError, InvalidClientError, InvalidGrantError, InvalidRedirectUriError, RateLimitedError

router = APIRouter(tags=["oauth"])


def _error_page(title: str, detail: str) -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html><html><head><meta charset="utf-8">
        <title>{title}</title>
        <style>body{{background:#0b0f1a;color:#e2e8f0;font-family:system-ui,sans-serif;
        display:flex;align-items:center;justify-content:center;height:100vh;margin:0}}
        .card{{background:#111827;border:1px solid rgba(255,255,255,.08);border-radius:16px;
        padding:32px 40px;max-width:440px;text-align:center}}
        h1{{font-size:18px;color:#f87171;margin:0 0 8px}}</style></head>
        <body><div class="card"><h1>{title}</h1><p>{detail}</p></div></body></html>""",
        status_code=400,
    )


@router.get("/oauth/authorize")
async def authorize(
    request: Request,
    response_type: str = Query(...),
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    scope: str = Query(default="openid profile"),
    state: str | None = Query(default=None),
    code_challenge: str = Query(...),
    code_challenge_method: str = Query(default="S256"),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    if response_type != "code":
        return _error_page("Unsupported response_type", "Only response_type=code is supported.")
    try:
        client = oidc_service.validate_authorize_request(db, client_id, redirect_uri, code_challenge_method)
    except (InvalidClientError, InvalidRedirectUriError, AppError) as exc:
        # Deliberately NOT a redirect: an unvalidated client_id/redirect_uri
        # must never cause this endpoint to bounce the browser to an
        # attacker-controlled URL (mission-brief section 24: open redirect).
        return _error_page("Sign-in request rejected", exc.message)

    if user is None:
        # A relative path, never an absolute URL - routes_pages._safe_next
        # only ever accepts a same-origin `/oauth/authorize?...` path, so
        # this must match that shape exactly for silent SSO to work.
        next_path = f"{request.url.path}?{request.url.query}" if request.url.query else request.url.path
        return RedirectResponse(url=f"/login?next={quote(next_path, safe='')}", status_code=302)

    code = oidc_service.issue_authorization_code(
        db, client, user, redirect_uri, code_challenge, code_challenge_method, scope, state
    )
    params = {"code": code}
    if state is not None:
        params["state"] = state
    return RedirectResponse(url=f"{redirect_uri}?{urlencode(params)}", status_code=302)


@router.post("/oauth/token")
async def token(request: Request, db: Session = Depends(get_db)) -> dict:
    form = await request.form()
    grant_type = form.get("grant_type")
    client_id = str(form.get("client_id", ""))
    client_key = f"{request.client.host if request.client else 'unknown'}:{client_id}"
    if not oauth_token_limiter.allow(client_key, max_events=30, window_seconds=60):
        raise RateLimitedError("Too many token requests. Please slow down.")

    if grant_type == "authorization_code":
        access_token, id_token, refresh_token, user = oidc_service.exchange_authorization_code(
            db,
            client_id=client_id,
            client_secret=str(form.get("client_secret", "")),
            code=str(form.get("code", "")),
            redirect_uri=str(form.get("redirect_uri", "")),
            code_verifier=str(form.get("code_verifier", "")),
        )
        return {
            "access_token": access_token,
            "id_token": id_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": get_settings().oidc_access_token_ttl_minutes * 60,
        }
    if grant_type == "refresh_token":
        access_token, user = oidc_service.refresh_oidc_token(
            db,
            client_id=client_id,
            client_secret=str(form.get("client_secret", "")),
            refresh_token_raw=str(form.get("refresh_token", "")),
        )
        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": get_settings().oidc_access_token_ttl_minutes * 60,
        }
    raise InvalidGrantError("Unsupported grant_type.")


@router.get("/oauth/userinfo")
async def userinfo(principal: BearerPrincipal = Depends(get_bearer_principal)) -> dict:
    return {
        "sub": principal.user.id,
        "email": principal.user.email,
        "email_verified": principal.user.email_verified,
    }


@router.get("/.well-known/jwks.json")
async def jwks() -> dict:
    return get_jwks()


@router.get("/.well-known/openid-configuration")
async def openid_configuration() -> dict:
    settings = get_settings()
    base = settings.platform_auth_base_url
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "userinfo_endpoint": f"{base}/oauth/userinfo",
        "jwks_uri": f"{base}/.well-known/jwks.json",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "scopes_supported": ["openid", "profile"],
    }
