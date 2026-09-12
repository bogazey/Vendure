"""Browser-submitted analytics event ingestion.

Only `page_view` can ever be submitted here - every authoritative business
event (downloads, signups, plan changes) is recorded server-side elsewhere
(see routes_analyze.py, routes_downloads.py, download_manager.py,
routes_auth.py, paddle_service.py) so a browser can never forge one. This
endpoint treats every field as untrusted: visitor_id and user_id are always
derived server-side (cookie / auth dependency), never read from the body.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_optional_user
from app.database.commercial_models import User
from app.models.analytics_schemas import TrackEventRequest
from app.models.commercial_enums import AnalyticsEventType
from app.services import analytics_service
from app.services.rate_limit_service import analytics_limiter
from app.utils.exceptions import RateLimitedError

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.post("/event", status_code=204, response_model=None)
async def track_event(
    payload: TrackEventRequest,
    request: Request,
    response: Response,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> None:
    visitor_id = analytics_service.ensure_visitor_id(request, response)
    if not analytics_limiter.allow(f"visitor:{visitor_id}", max_events=120, window_seconds=300):
        raise RateLimitedError("Too many analytics events.")
    if analytics_service.request_is_bot(request):
        # Cookie is still minted above (harmless either way) so a bot
        # retrying doesn't hammer the rate limiter differently each time,
        # but nothing is written for it - keeps human traffic stats honest
        # without touching SEO crawling itself (this is analytics, not a
        # firewall - crawlers are never blocked from the page itself).
        return
    device = analytics_service.request_device_context(request)
    analytics_service.record_event(
        db,
        AnalyticsEventType.PAGE_VIEW,
        visitor_id=visitor_id,
        user_id=user.id if user else None,
        path=analytics_service.normalize_path(payload.path),
        locale=payload.locale,
        referrer_domain=analytics_service.extract_referrer_domain(payload.referrer, request),
        utm_source=analytics_service.sanitize_utm(payload.utm_source),
        utm_medium=analytics_service.sanitize_utm(payload.utm_medium),
        utm_campaign=analytics_service.sanitize_utm(payload.utm_campaign),
        country_code=analytics_service.request_country_code(request),
        **device,
    )
