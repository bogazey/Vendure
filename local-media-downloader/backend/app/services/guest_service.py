"""Anonymous "try before you sign up" download allowance.

Identity: an opaque, server-minted token (never a client-chosen value,
never linked to a User row) carried in a long-lived httpOnly cookie - see
api/deps.py's get_guest_id and routes_downloads.py. Clearing cookies resets
this identity; that is a known, accepted limitation (see task notes) - this
is deliberately NOT hardware/browser fingerprinting.

Quota: the same atomic reserve -> commit/refund shape as usage_service, just
counting downloads instead of credits (see GuestQuota), and deliberately
never creating a Subscription/UsagePeriod/credit row for an anonymous
visitor - guests are not a Free-plan *account*, they just get the same
feature ceiling (see authorize_and_reserve below, which reuses
entitlement_service against Plan.FREE without ever touching usage_service).
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.config.commercial_settings import get_commercial_settings
from app.database.commercial_models import GuestQuota
from app.models.commercial_enums import Plan
from app.models.enums import MediaType
from app.models.schemas import CreateDownloadRequest
from app.services import plan_policy
from app.services.entitlement_service import entitlement_service
from app.utils.exceptions import GuestQuotaExceededError, PlanLimitReachedError

_TOKEN_BYTES = 32


def _new_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def quota_exists(session: Session, guest_id: str) -> bool:
    return session.get(GuestQuota, guest_id) is not None


def resolve_or_create(session: Session, presented_token: Optional[str]) -> tuple[str, bool]:
    """Returns (guest_id, is_new). If `presented_token` matches a known
    guest, reuses it (no new cookie needs to be set). Otherwise - no cookie
    at all, or a value this server never issued - mints a fresh one. Never
    trusts a client-chosen value as an existing identity without a DB hit,
    so a client can't "become" another guest by guessing/setting an id."""
    if presented_token and quota_exists(session, presented_token):
        return presented_token, False

    guest_id = _new_token()
    session.add(GuestQuota(id=guest_id, downloads_reserved=0, downloads_completed=0))
    session.flush()
    return guest_id, True


def _height_for_gating(quality_key: str) -> Optional[int]:
    if not quality_key or quality_key == "best":
        return None
    try:
        return int(quality_key)
    except ValueError:
        return None


def get_quota_status(session: Session, guest_id: str) -> tuple[int, int]:
    """Returns (used, limit) where `used` counts both completed downloads
    and any currently in-flight (reserved) ones - i.e. "how many of the
    allowance are already spoken for", which is what the UI's remaining
    count should reflect."""
    limit = get_commercial_settings().guest_download_limit
    quota = session.get(GuestQuota, guest_id)
    if quota is None:
        return 0, limit
    return quota.downloads_completed + quota.downloads_reserved, limit


def authorize_and_reserve(session: Session, guest_id: str, request: CreateDownloadRequest) -> None:
    """Raises PlanLimitReachedError/FeatureNotIncludedError for anything a
    Free-plan account couldn't do either (guests get exactly Free's feature
    ceiling), or GuestQuotaExceededError once the allowance is spent.
    Reserves one unit of the allowance on success - the caller must call
    commit_download() on genuine success or refund_download() on failure/
    cancellation (mirrors usage_service.reserve/commit/refund)."""
    if request.media_type == MediaType.VIDEO:
        policy = plan_policy.get_policy(Plan.FREE)
        if request.quality_key == "best" and policy.max_resolution_height is not None:
            raise PlanLimitReachedError(
                f"Guest downloads support up to {policy.max_resolution_height}p. "
                "Create a free account to unlock Best Available."
            )
        height = _height_for_gating(request.quality_key)
        entitlement_service.check_resolution(Plan.FREE, height)
        if request.format_id:
            entitlement_service.check_feature(Plan.FREE, "advanced_formats")
        if request.clip is not None:
            entitlement_service.check_feature(Plan.FREE, "clip_range")
        if request.playlist_mode == "full":
            entitlement_service.check_feature(Plan.FREE, "batch")

    limit = get_commercial_settings().guest_download_limit
    result = session.execute(
        update(GuestQuota)
        .where(
            GuestQuota.id == guest_id,
            (GuestQuota.downloads_completed + GuestQuota.downloads_reserved) < limit,
        )
        .values(downloads_reserved=GuestQuota.downloads_reserved + 1)
    )
    if result.rowcount == 0:
        raise GuestQuotaExceededError(
            "You've used your free downloads. Create a free account to keep downloading."
        )


def commit_download(session: Session, guest_id: str) -> None:
    session.execute(
        update(GuestQuota)
        .where(GuestQuota.id == guest_id)
        .values(
            downloads_completed=GuestQuota.downloads_completed + 1,
            downloads_reserved=GuestQuota.downloads_reserved - 1,
        )
    )


def refund_download(session: Session, guest_id: str) -> None:
    session.execute(
        update(GuestQuota)
        .where(GuestQuota.id == guest_id, GuestQuota.downloads_reserved > 0)
        .values(downloads_reserved=GuestQuota.downloads_reserved - 1)
    )


def cleanup_expired(session: Session) -> list[str]:
    """One-shot startup sweep (same pattern as
    history_repo.mark_interrupted_as_failed) - deletes guest quota rows
    untouched for longer than GUEST_DATA_TTL_HOURS and returns their ids, so
    the caller can also remove the matching guest_storage_service
    directories (see main.py's lifespan)."""
    ttl_hours = get_commercial_settings().guest_data_ttl_hours
    cutoff = datetime.now(timezone.utc) - timedelta(hours=ttl_hours)
    expired_ids = list(
        session.execute(select(GuestQuota.id).where(GuestQuota.last_used_at < cutoff)).scalars()
    )
    if expired_ids:
        session.execute(delete(GuestQuota).where(GuestQuota.id.in_(expired_ids)))
    return expired_ids
