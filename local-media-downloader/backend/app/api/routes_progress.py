"""Server-Sent Events endpoint pushing job-list snapshots on change only.

The backend watches an in-memory revision counter (bumped by yt-dlp progress
hooks) and only emits a new event when it changes, so the client never has to
poll and the wire stays quiet between real updates.
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from app.services.download_manager import manager

router = APIRouter(prefix="/api", tags=["progress"])

POLL_INTERVAL_SECONDS = 0.3


@router.get("/progress/stream")
async def progress_stream(request: Request) -> EventSourceResponse:
    async def event_generator():
        last_revision = -1
        while True:
            if await request.is_disconnected():
                break
            current_revision = manager.revision
            if current_revision != last_revision:
                last_revision = current_revision
                jobs = [job.model_dump() for job in manager.list_jobs()]
                yield {"event": "jobs", "data": json.dumps(jobs)}
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    return EventSourceResponse(event_generator())
