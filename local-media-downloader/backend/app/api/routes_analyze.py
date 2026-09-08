from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_optional_user
from app.database.commercial_models import User
from app.models.schemas import AnalyzeRequest, AnalyzeResponse
from app.services import ytdlp_service
from app.services.settings_service import get_settings
from app.services.rate_limit_service import analyze_limiter
from app.services.user_preferences_service import user_preferences_service
from app.utils.exceptions import RateLimitedError, UnsupportedUrlError
from app.utils.url_detect import is_valid_url

router = APIRouter(prefix="/api", tags=["analyze"])


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    payload: AnalyzeRequest,
    request: Request,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> AnalyzeResponse:
    identity = f"user:{user.id}" if user else f"ip:{request.client.host if request.client else 'unknown'}"
    if not analyze_limiter.allow(identity, max_events=60, window_seconds=300):
        raise RateLimitedError("Too many links were analyzed. Please wait a few minutes and try again.")

    if not is_valid_url(payload.url):
        raise UnsupportedUrlError("That doesn't look like a valid URL.")

    # Anonymous previews (landing/pricing funnel, before signup) get the
    # sensible defaults; a signed-in user's preview reflects their own
    # container_mode/cookie settings - never the global row, which would
    # leak one user's choice into every other (including anonymous) preview.
    settings = user_preferences_service.get_effective_settings(db, user.id if user else None, get_settings())
    return await asyncio.to_thread(ytdlp_service.analyze, payload.url, settings)
