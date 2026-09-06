"""Server-Sent Events endpoint pushing job-list snapshots on change only.

The backend watches an in-memory revision counter (bumped by yt-dlp progress
hooks) and only emits a new event when it changes, so the client never has to
poll and the wire stays quiet between real updates.
"""
from __future__ import annotations

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

from app.api.deps import get_guest_id, get_optional_user
from app.database.commercial_models import User
from app.services.download_manager import manager

router = APIRouter(prefix="/api", tags=["progress"])

POLL_INTERVAL_SECONDS = 0.3


@router.get("/progress/stream")
async def progress_stream(
    request: Request,
    user: Optional[User] = Depends(get_optional_user),
    guest_id: Optional[str] = Depends(get_guest_id),
) -> EventSourceResponse:
    # Same ownership scoping as GET /api/downloads - without it this stream
    # would broadcast every user's (or every guest's) job titles/URLs/
    # progress to anyone connected, regardless of who started them. A
    # caller with neither identity (no account, no guest cookie yet) simply
    # has no jobs to see.
    async def event_generator():
        last_revision = -1
        while True:
            if await request.is_disconnected():
                break
            current_revision = manager.revision
            if current_revision != last_revision:
                last_revision = current_revision
                if user is not None:
                    jobs = [job.model_dump() for job in manager.list_jobs(user_id=user.id)]
                elif guest_id is not None:
                    jobs = [job.model_dump() for job in manager.list_jobs(guest_id=guest_id)]
                else:
                    jobs = []
                yield {"event": "jobs", "data": json.dumps(jobs)}
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    return EventSourceResponse(event_generator())
