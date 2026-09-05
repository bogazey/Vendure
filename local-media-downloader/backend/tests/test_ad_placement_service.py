"""Unit tests for the centralized ad-eligibility decision (see
ad_placement_service.is_ad_eligible). HTTP-level coverage for the placement
registry routes themselves lives in test_commercial_api.py."""
from app.models.commercial_enums import Plan
from app.services.ad_placement_service import is_ad_eligible


class TestAdEligibility:
    def test_free_plan_is_ad_eligible(self):
        assert is_ad_eligible(Plan.FREE) is True

    def test_pro_plan_is_not_ad_eligible(self):
        assert is_ad_eligible(Plan.PRO) is False

    def test_creator_plan_is_not_ad_eligible(self):
        assert is_ad_eligible(Plan.CREATOR) is False
