from __future__ import annotations

import asyncio

from fastapi import APIRouter

from app.models.schemas import AnalyzeRequest, AnalyzeResponse
from app.services import ytdlp_service
from app.services.settings_service import get_settings
from app.utils.exceptions import UnsupportedUrlError
from app.utils.url_detect import is_valid_url

router = APIRouter(prefix="/api", tags=["analyze"])


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    if not is_valid_url(request.url):
        raise UnsupportedUrlError("That doesn't look like a valid URL.")

    settings = get_settings()
    return await asyncio.to_thread(ytdlp_service.analyze, request.url, settings)
