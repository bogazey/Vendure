"""Single source of truth for what each plan includes.

Nothing else in the app should hardcode `if plan == "pro"` — everything
(entitlement checks, credit costs, queue priority, ads) reads from here, so
adding/adjusting a plan is a one-place change.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.models.commercial_enums import Plan


@dataclass(frozen=True)
class PlanPolicy:
    plan: Plan
    max_resolution_height: Optional[int]  # None = unlimited (e.g. 4K/8K)
    can_use_4k: bool
    can_use_batch: bool
    can_use_advanced_formats: bool
    can_use_clip_range: bool
    can_use_browser_cookies: bool
    can_use_original_container: bool
    can_use_creator_tools: bool
    ads_enabled: bool
    queue_priority: int
    monthly_credits: Optional[int]  # None for Free (uses daily allowance instead)
    daily_free_downloads: Optional[int]  # only meaningful for Free


PLAN_POLICIES: dict[Plan, PlanPolicy] = {
    Plan.FREE: PlanPolicy(
        plan=Plan.FREE,
        max_resolution_height=720,
        can_use_4k=False,
        can_use_batch=False,
        can_use_advanced_formats=False,
        can_use_clip_range=False,
        can_use_browser_cookies=False,
        can_use_original_container=False,
        can_use_creator_tools=False,
        ads_enabled=True,
        queue_priority=1,
        monthly_credits=None,
        daily_free_downloads=5,
    ),
    Plan.PRO: PlanPolicy(
        plan=Plan.PRO,
        max_resolution_height=None,
        can_use_4k=True,
        can_use_batch=True,
        can_use_advanced_formats=True,
        can_use_clip_range=True,
        can_use_browser_cookies=True,
        can_use_original_container=True,
        can_use_creator_tools=False,
        ads_enabled=False,
        queue_priority=5,
        monthly_credits=150,
        daily_free_downloads=None,
    ),
    Plan.CREATOR: PlanPolicy(
        plan=Plan.CREATOR,
        max_resolution_height=None,
        can_use_4k=True,
        can_use_batch=True,
        can_use_advanced_formats=True,
        can_use_clip_range=True,
        can_use_browser_cookies=True,
        can_use_original_container=True,
        can_use_creator_tools=True,
        ads_enabled=False,
        queue_priority=10,
        monthly_credits=500,
        daily_free_downloads=None,
    ),
}


def get_policy(plan: Plan) -> PlanPolicy:
    return PLAN_POLICIES[plan]


def parse_explicit_height(quality_key: str) -> Optional[int]:
    """The explicit numeric resolution height the caller asked for, or None
    for "best available" (or an unrecognized key, treated the same way).
    Shared by download_gate_service and guest_service so this parsing - and
    the "what does 'best' mean" question it feeds into - lives in exactly
    one place rather than two near-identical private copies."""
    if not quality_key or quality_key == "best":
        return None
    try:
        return int(quality_key)
    except ValueError:
        return None


def resolve_best_available_cap(plan: Plan) -> Optional[int]:
    """The height ceiling a "Best Available" request must respect for this
    plan - i.e. what "best" actually resolves to, before the download even
    knows what the source offers. None means uncapped: true best, whatever
    the source's own highest quality is (see PlanPolicy.max_resolution_height
    - this is a thin, named wrapper around it so callers ask "what's the cap"
    rather than reaching into policy internals directly, and so there is one
    obvious place to look if that ever needs to become more than a single
    field lookup)."""
    return get_policy(plan).max_resolution_height


# --- Credit cost model ---------------------------------------------------
#
# Kept here (not scattered into the download pipeline) so pricing changes are
# a one-place edit. media_type/height come straight off CreateDownloadRequest.

CREDIT_COST_AUDIO = 1
CREDIT_COST_IMAGE = 1
CREDIT_COST_VIDEO_UP_TO_1080P = 1
CREDIT_COST_VIDEO_1440P = 2
CREDIT_COST_VIDEO_4K = 3
CREDIT_COST_EXPENSIVE_TRANSCODE_SURCHARGE = 1


def credit_cost_for_video(height: Optional[int]) -> int:
    if height is None or height <= 1080:
        return CREDIT_COST_VIDEO_UP_TO_1080P
    if height <= 1440:
        return CREDIT_COST_VIDEO_1440P
    return CREDIT_COST_VIDEO_4K


def credit_cost_for_audio() -> int:
    return CREDIT_COST_AUDIO


def credit_cost_for_image() -> int:
    # Matches the cheapest existing per-item rate (audio, <=1080p video) -
    # an image is a single small file with no transcoding, so there's no
    # basis for charging more; this is a new rule (images never worked
    # before), not a change to any existing video/audio price.
    return CREDIT_COST_IMAGE
