"""PlanPolicy / EntitlementService: the single source of truth for what each
plan can do. These are pure-logic tests - no DB needed."""
import pytest

from app.models.commercial_enums import Plan
from app.services import plan_policy
from app.services.entitlement_service import entitlement_service
from app.utils.exceptions import FeatureNotIncludedError, PlanLimitReachedError, UpgradeRequiredError


class TestResolutionGating:
    def test_free_capped_at_720p(self):
        entitlement_service.check_resolution(Plan.FREE, 720)  # ok, no raise
        with pytest.raises(PlanLimitReachedError):
            entitlement_service.check_resolution(Plan.FREE, 1080)

    def test_free_allows_lower_than_cap(self):
        entitlement_service.check_resolution(Plan.FREE, 480)

    def test_pro_and_creator_uncapped(self):
        entitlement_service.check_resolution(Plan.PRO, 2160)
        entitlement_service.check_resolution(Plan.CREATOR, 2160)


class TestFeatureGating:
    @pytest.mark.parametrize(
        "feature",
        ["batch", "advanced_formats", "clip_range", "browser_cookies", "original_container", "creator_tools"],
    )
    def test_free_lacks_all_paid_features(self, feature):
        with pytest.raises(FeatureNotIncludedError):
            entitlement_service.check_feature(Plan.FREE, feature)

    @pytest.mark.parametrize(
        "feature", ["batch", "advanced_formats", "clip_range", "browser_cookies", "original_container"]
    )
    def test_pro_has_pro_features(self, feature):
        entitlement_service.check_feature(Plan.PRO, feature)

    def test_only_creator_has_creator_tools(self):
        with pytest.raises(FeatureNotIncludedError):
            entitlement_service.check_feature(Plan.PRO, "creator_tools")
        entitlement_service.check_feature(Plan.CREATOR, "creator_tools")

    def test_require_paid_blocks_free(self):
        with pytest.raises(UpgradeRequiredError):
            entitlement_service.require_paid(Plan.FREE, "This needs a paid plan.")
        entitlement_service.require_paid(Plan.PRO, "This needs a paid plan.")


class TestCreditCosts:
    def test_video_cost_tiers(self):
        assert plan_policy.credit_cost_for_video(480) == 1
        assert plan_policy.credit_cost_for_video(1080) == 1
        assert plan_policy.credit_cost_for_video(1440) == 2
        assert plan_policy.credit_cost_for_video(2160) == 3
        assert plan_policy.credit_cost_for_video(None) == 1

    def test_audio_cost_is_flat(self):
        assert plan_policy.credit_cost_for_audio() == 1

    def test_free_plan_has_no_monthly_credits_but_has_daily_downloads(self):
        policy = plan_policy.get_policy(Plan.FREE)
        assert policy.monthly_credits is None
        assert policy.daily_free_downloads == 5

    def test_paid_plans_have_monthly_credits_not_daily_downloads(self):
        for plan in (Plan.PRO, Plan.CREATOR):
            policy = plan_policy.get_policy(plan)
            assert policy.monthly_credits is not None
            assert policy.daily_free_downloads is None
