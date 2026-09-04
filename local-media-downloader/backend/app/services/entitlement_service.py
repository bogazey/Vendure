"""Centralized feature gating: "can this user do X right now".

Every download-affecting check in the API goes through here rather than an
inline `if plan == "pro"` - see routes_downloads.py / routes_analyze.py. The
backend is the enforcement point; the frontend hiding a button is only a
convenience, never the actual gate.
"""
from __future__ import annotations

from typing import Optional

from app.database.commercial_models import User
from app.models.commercial_enums import Plan
from app.models.commercial_schemas import PlanFeaturesOut
from app.services.plan_policy import PlanPolicy, get_policy
from app.utils.exceptions import FeatureNotIncludedError, PlanLimitReachedError, UpgradeRequiredError

FEATURE_LABELS = {
    "batch": "Batch downloads",
    "advanced_formats": "Advanced format selection",
    "clip_range": "Clip-range downloads",
    "browser_cookies": "Browser cookie downloads",
    "original_container": "Best Quality / Original Container",
    "creator_tools": "Creator tools",
}


class EntitlementService:
    def get_policy(self, plan: Plan) -> PlanPolicy:
        return get_policy(plan)

    def to_features_out(self, plan: Plan) -> PlanFeaturesOut:
        policy = get_policy(plan)
        return PlanFeaturesOut(
            plan=policy.plan,
            max_resolution_height=policy.max_resolution_height,
            can_use_4k=policy.can_use_4k,
            can_use_batch=policy.can_use_batch,
            can_use_advanced_formats=policy.can_use_advanced_formats,
            can_use_clip_range=policy.can_use_clip_range,
            can_use_browser_cookies=policy.can_use_browser_cookies,
            can_use_original_container=policy.can_use_original_container,
            can_use_creator_tools=policy.can_use_creator_tools,
            ads_enabled=policy.ads_enabled,
            queue_priority=policy.queue_priority,
            monthly_credits=policy.monthly_credits,
            daily_free_downloads=policy.daily_free_downloads,
        )

    def check_feature(self, plan: Plan, feature: str) -> None:
        """Raises FeatureNotIncludedError if `feature` (one of the
        FEATURE_LABELS keys) isn't included in `plan`."""
        policy = get_policy(plan)
        flag_map = {
            "batch": policy.can_use_batch,
            "advanced_formats": policy.can_use_advanced_formats,
            "clip_range": policy.can_use_clip_range,
            "browser_cookies": policy.can_use_browser_cookies,
            "original_container": policy.can_use_original_container,
            "creator_tools": policy.can_use_creator_tools,
        }
        if not flag_map.get(feature, False):
            label = FEATURE_LABELS.get(feature, feature)
            raise FeatureNotIncludedError(
                f"{label} isn't included in your current plan. Upgrade to unlock it."
            )

    def check_resolution(self, plan: Plan, height: Optional[int]) -> None:
        """Raises PlanLimitReachedError if `height` exceeds the plan's max
        resolution. `height=None` means "best available" and is checked
        against can_use_4k as a proxy (an uncapped request could resolve to
        4K+) - the actual enforced ceiling still happens server-side when the
        real source resolution is known, via the credit-cost/height at
        download time."""
        policy = get_policy(plan)
        if policy.max_resolution_height is None:
            return
        if height is not None and height > policy.max_resolution_height:
            raise PlanLimitReachedError(
                f"Your plan supports up to {policy.max_resolution_height}p. "
                f"Upgrade to download at {height}p."
            )

    def require_paid(self, plan: Plan, reason: str) -> None:
        if plan == Plan.FREE:
            raise UpgradeRequiredError(reason)


entitlement_service = EntitlementService()
