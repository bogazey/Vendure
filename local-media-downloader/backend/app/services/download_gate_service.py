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
from app.models.schemas import CreateDownloadRequest
from app.services import plan_policy
from app.services.entitlement_service import entitlement_service
from app.services.usage_service import usage_service
from app.services.user_preferences_service import user_preferences_service
from app.utils.exceptions import PlanLimitReachedError

# Credit costs assume the worst case for an unconstrained "best available"
# request, so a user is never undercharged relative to what they might
# actually receive - see COMMERCIAL_ARCHITECTURE.md for the reasoning. Only
# used when the plan itself has no resolution cap (Pro/Creator today); a
# capped plan's own cap is a tighter, still-safe worst case (see
# _height_for_cost below).
_WORST_CASE_HEIGHT_FOR_BEST = 2160


def _height_for_cost(quality_key: str, max_resolution_height: Optional[int]) -> Optional[int]:
    height = plan_policy.parse_explicit_height(quality_key)
    if height is None and quality_key == "best":
        return max_resolution_height if max_resolution_height is not None else _WORST_CASE_HEIGHT_FOR_BEST
    return height


class DownloadGateService:
    def authorize_and_reserve(
        self,
        session: Session,
        user: User,
        plan: Plan,
        subscription: Optional[Subscription],
        request: CreateDownloadRequest,
        download_job_id: str,
    ) -> tuple[str, Optional[int]]:
        """Raises a PlanLimitReachedError/FeatureNotIncludedError/
        DailyLimitReachedError/InsufficientCreditsError if this request
        isn't allowed right now. Otherwise reserves the credit cost and
        returns (reservation_id, max_resolution_height) - the reservation id
        to pass through to the download job (for commit-on-success /
        refund-on-failure), and this plan's resolution cap (None if
        uncapped) so the caller can pass it into DownloadManager.create_job,
        which is what actually makes "Best Available" resolve to at most
        this height (see ytdlp_service.build_format_selector's max_height
        parameter) - the request's own quality_key is never rewritten here,
        so history/retry always re-resolve "best" against whatever the
        user's plan is *at that later time*, not what it was when they first
        asked.

        Gates against *this user's own* container_mode/cookie_source
        (user_preferences_service) - never the personal app's global
        settings, which would let one account's choice block or unblock
        every other account's downloads."""
        policy = plan_policy.get_policy(plan)
        prefs = user_preferences_service.get_or_create(session, user.id)
        max_resolution_height: Optional[int] = None

        if request.media_type == MediaType.VIDEO:
            max_resolution_height = policy.max_resolution_height
            # An explicit numeric pick (e.g. "1080") is still checked against
            # the plan's ceiling and rejected with the existing upgrade
            # message if it exceeds it. "Best Available" (height=None here)
            # is never rejected - it's capped instead, via max_resolution_height
            # above, which flows through to the actual format selector.
            height = plan_policy.parse_explicit_height(request.quality_key)
            entitlement_service.check_resolution(plan, height)
            if height is not None and height >= 2160 and not policy.can_use_4k:
                raise PlanLimitReachedError("4K downloads require Pro or Creator.")

            if request.format_id:
                entitlement_service.check_feature(plan, "advanced_formats")
            if request.clip is not None:
                entitlement_service.check_feature(plan, "clip_range")
            if request.playlist_mode == "full":
                entitlement_service.check_feature(plan, "batch")
            if prefs.container_mode == ContainerMode.ORIGINAL.value:
                entitlement_service.check_feature(plan, "original_container")
            if prefs.cookie_source != CookieSource.NONE.value:
                entitlement_service.check_feature(plan, "browser_cookies")

            cost = plan_policy.credit_cost_for_video(_height_for_cost(request.quality_key, max_resolution_height))
        elif request.media_type == MediaType.IMAGE:
            if prefs.cookie_source != CookieSource.NONE.value:
                entitlement_service.check_feature(plan, "browser_cookies")
            cost = plan_policy.credit_cost_for_image()
        else:
            if prefs.cookie_source != CookieSource.NONE.value:
                entitlement_service.check_feature(plan, "browser_cookies")
            cost = plan_policy.credit_cost_for_audio()

        reservation_id = usage_service.reserve(session, user, plan, subscription, cost, download_job_id)
        return reservation_id, max_resolution_height


download_gate_service = DownloadGateService()
