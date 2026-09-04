"""The single choke point a download request passes through before a job is
ever created: entitlement checks, then an atomic credit reservation.

routes_downloads.py calls this and only this - no plan/credit logic should
live in the route handlers or in DownloadManager itself, which stays
entirely about *how* a download runs, not *whether* it's allowed.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.database.commercial_models import Subscription, User
from app.models.commercial_enums import Plan
from app.models.enums import ContainerMode, CookieSource, MediaType
from app.models.schemas import AppSettings, CreateDownloadRequest
from app.services import plan_policy
from app.services.entitlement_service import entitlement_service
from app.services.usage_service import usage_service
from app.utils.exceptions import PlanLimitReachedError

# Credit costs assume the worst case for an unconstrained "best available"
# request, so a user is never undercharged relative to what they might
# actually receive - see COMMERCIAL_ARCHITECTURE.md for the reasoning.
_WORST_CASE_HEIGHT_FOR_BEST = 2160


def _height_for_gating(quality_key: str) -> Optional[int]:
    if not quality_key or quality_key == "best":
        return None
    try:
        return int(quality_key)
    except ValueError:
        return None


def _height_for_cost(quality_key: str) -> Optional[int]:
    height = _height_for_gating(quality_key)
    if height is None and quality_key == "best":
        return _WORST_CASE_HEIGHT_FOR_BEST
    return height


class DownloadGateService:
    def authorize_and_reserve(
        self,
        session: Session,
        user: User,
        plan: Plan,
        subscription: Optional[Subscription],
        app_settings: AppSettings,
        request: CreateDownloadRequest,
        download_job_id: str,
    ) -> str:
        """Raises a PlanLimitReachedError/FeatureNotIncludedError/
        DailyLimitReachedError/InsufficientCreditsError if this request
        isn't allowed right now. Otherwise reserves the credit cost and
        returns a reservation id to pass through to the download job (for
        commit-on-success / refund-on-failure)."""
        policy = plan_policy.get_policy(plan)

        if request.media_type == MediaType.VIDEO:
            if request.quality_key == "best" and policy.max_resolution_height is not None:
                raise PlanLimitReachedError(
                    f"Your plan supports up to {policy.max_resolution_height}p. "
                    "Pick a specific resolution, or upgrade for Best Available."
                )
            height = _height_for_gating(request.quality_key)
            entitlement_service.check_resolution(plan, height)
            if height is not None and height >= 2160 and not policy.can_use_4k:
                raise PlanLimitReachedError("4K downloads require Pro or Creator.")

            if request.format_id:
                entitlement_service.check_feature(plan, "advanced_formats")
            if request.clip is not None:
                entitlement_service.check_feature(plan, "clip_range")
            if request.playlist_mode == "full":
                entitlement_service.check_feature(plan, "batch")
            if app_settings.container_mode == ContainerMode.ORIGINAL:
                entitlement_service.check_feature(plan, "original_container")
            if app_settings.cookie_source != CookieSource.NONE:
                entitlement_service.check_feature(plan, "browser_cookies")

            cost = plan_policy.credit_cost_for_video(_height_for_cost(request.quality_key))
        else:
            if app_settings.cookie_source != CookieSource.NONE:
                entitlement_service.check_feature(plan, "browser_cookies")
            cost = plan_policy.credit_cost_for_audio()

        return usage_service.reserve(session, user, plan, subscription, cost, download_job_id)


download_gate_service = DownloadGateService()
