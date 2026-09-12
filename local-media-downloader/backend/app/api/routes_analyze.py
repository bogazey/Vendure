from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_optional_user
from app.database.commercial_models import User
from app.models.commercial_enums import AnalyticsEventType
from app.models.schemas import AnalyzeRequest, AnalyzeResponse
from app.services import analytics_service, ytdlp_service
from app.services.settings_service import get_settings
from app.services.rate_limit_service import analyze_limiter
from app.services.user_preferences_service import user_preferences_service
from app.utils.exceptions import RateLimitedError, UnsupportedUrlError
from app.utils.url_detect import detect_platform, is_valid_url

router = APIRouter(prefix="/api", tags=["analyze"])


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    payload: AnalyzeRequest,
    request: Request,
    response: Response,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> AnalyzeResponse:
    identity = f"user:{user.id}" if user else f"ip:{request.client.host if request.client else 'unknown'}"
    if not analyze_limiter.allow(identity, max_events=60, window_seconds=300):
        raise RateLimitedError("Too many links were analyzed. Please wait a few minutes and try again.")

    if not is_valid_url(payload.url):
        raise UnsupportedUrlError("That doesn't look like a valid URL.")

    # Analytics is best-effort and must never affect the analyze flow itself
    # (see docs/ANALYTICS.md "Frontend/backend resilience") - each event is
    # committed immediately since get_db() rolls back the whole session on
    # any exception the route raises below, which would otherwise wipe out
    # an already-recorded analyze_started/analyze_failed event too.
    visitor_id = analytics_service.ensure_visitor_id(request, response)
    is_bot = analytics_service.request_is_bot(request)
    platform = detect_platform(payload.url).value
    if not is_bot:
        analytics_service.record_event(
            db, AnalyticsEventType.ANALYZE_STARTED,
            visitor_id=visitor_id, user_id=user.id if user else None,
            source_platform=platform, country_code=analytics_service.request_country_code(request),
            **analytics_service.request_device_context(request),
        )
        db.commit()

    # Anonymous previews (landing/pricing funnel, before signup) get the
    # sensible defaults; a signed-in user's preview reflects their own
    # container_mode/cookie settings - never the global row, which would
    # leak one user's choice into every other (including anonymous) preview.
    settings = user_preferences_service.get_effective_settings(db, user.id if user else None, get_settings())
    try:
        result = await asyncio.to_thread(ytdlp_service.analyze, payload.url, settings)
    except Exception as exc:
        if not is_bot:
            analytics_service.record_event(
                db, AnalyticsEventType.ANALYZE_FAILED,
                visitor_id=visitor_id, user_id=user.id if user else None,
                source_platform=platform, failure_category=analytics_service.classify_failure(exc),
            )
            db.commit()
        raise

    if not is_bot:
        analytics_service.record_event(
            db, AnalyticsEventType.ANALYZE_COMPLETED,
            visitor_id=visitor_id, user_id=user.id if user else None,
            source_platform=platform, media_type=result.media_type.value,
        )
        db.commit()
    return result
