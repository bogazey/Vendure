from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_optional_user
from app.database.commercial_models import User
from app.models.schemas import AnalyzeRequest, AnalyzeResponse
from app.services import ytdlp_service
from app.services.settings_service import get_settings
from app.services.user_preferences_service import user_preferences_service
from app.utils.exceptions import UnsupportedUrlError
from app.utils.url_detect import is_valid_url

router = APIRouter(prefix="/api", tags=["analyze"])


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    request: AnalyzeRequest,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> AnalyzeResponse:
    if not is_valid_url(request.url):
        raise UnsupportedUrlError("That doesn't look like a valid URL.")

    # Anonymous previews (landing/pricing funnel, before signup) get the
    # sensible defaults; a signed-in user's preview reflects their own
    # container_mode/cookie settings - never the global row, which would
    # leak one user's choice into every other (including anonymous) preview.
    settings = user_preferences_service.get_effective_settings(db, user.id if user else None, get_settings())
    return await asyncio.to_thread(ytdlp_service.analyze, request.url, settings)
