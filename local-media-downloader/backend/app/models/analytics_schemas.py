"""Pydantic request/response schemas for first-party web analytics.

TrackEventRequest is the ONLY shape the browser may ever submit (see
routes_analytics.py) - it deliberately excludes user_id, visitor_id,
country, device info, and any business/revenue field. Everything else here
is admin-only reporting output.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

AnalyticsRange = Literal["today", "7d", "30d", "90d"]


class TrackEventRequest(BaseModel):
    """Browser-submitted analytics event. Only `page_view` is accepted -
    every authoritative business event (downloads, signups, plan changes)
    is recorded server-side instead (see docs/ANALYTICS.md)."""

    event_type: Literal["page_view"]
    path: str = Field(min_length=1, max_length=255)
    locale: Optional[Literal["en", "ar"]] = None
    # Full referrer URL as the browser reports it - the backend extracts and
    # stores only the registrable domain, never the full URL/query string.
    referrer: Optional[str] = Field(default=None, max_length=2048)
    utm_source: Optional[str] = Field(default=None, max_length=100)
    utm_medium: Optional[str] = Field(default=None, max_length=100)
    utm_campaign: Optional[str] = Field(default=None, max_length=100)


class AnalyticsOverviewOut(BaseModel):
    range: AnalyticsRange
    visitors: int
    page_views: int
    downloads_completed: int
    new_users: int
    paid_conversions: int
    active_now: int
    download_success_rate: Optional[float] = None


class TrafficPointOut(BaseModel):
    date: str
    visitors: int
    page_views: int


class TrafficOut(BaseModel):
    range: AnalyticsRange
    points: list[TrafficPointOut]


class TopPageOut(BaseModel):
    path: str
    views: int
    visitors: int
    pct_of_total: float


class PagesOut(BaseModel):
    range: AnalyticsRange
    pages: list[TopPageOut]


class SourceRowOut(BaseModel):
    source: str
    visitors: int
    pct_of_total: float


class SourcesOut(BaseModel):
    range: AnalyticsRange
    sources: list[SourceRowOut]


class CountryRowOut(BaseModel):
    country_code: str
    visitors: int
    page_views: int
    downloads: int


class GeographyOut(BaseModel):
    range: AnalyticsRange
    # False when no country data has been observed yet in this deployment
    # (e.g. Cloudflare's CF-IPCountry header isn't reaching the backend) -
    # the frontend shows an honest empty state instead of a fabricated one.
    available: bool
    countries: list[CountryRowOut]


class BreakdownRowOut(BaseModel):
    key: str
    count: int
    pct: float


class DevicesOut(BaseModel):
    range: AnalyticsRange
    devices: list[BreakdownRowOut]
    browsers: list[BreakdownRowOut]
    os: list[BreakdownRowOut]
    languages: list[BreakdownRowOut]


class StageStatsOut(BaseModel):
    started: int
    completed: int
    failed: int
    success_rate: Optional[float] = None
    avg_processing_seconds: Optional[float] = None


class PlatformRowOut(BaseModel):
    platform: str
    analyses: int
    downloads: int
    successful: int
    failed: int
    success_rate: Optional[float] = None


class FailureRowOut(BaseModel):
    category: str
    count: int


class DownloadsOut(BaseModel):
    range: AnalyticsRange
    analyze: StageStatsOut
    downloads: StageStatsOut
    platforms: list[PlatformRowOut]
    failures: list[FailureRowOut]


class FunnelStageOut(BaseModel):
    key: str
    label: str
    count: int
    pct_of_previous: Optional[float] = None


class FunnelOut(BaseModel):
    range: AnalyticsRange
    stages: list[FunnelStageOut]
    # Honesty label per the mission's explicit requirement: this is a
    # period-aggregate funnel, not per-visitor cohort attribution.
    methodology_note: str


class PlanMovementRowOut(BaseModel):
    kind: str
    count: int


class RevenueOut(BaseModel):
    range: AnalyticsRange
    # Paid (provider="paddle") only - see gift_subscription_service.py and
    # docs/ANALYTICS.md "Gifted subscriptions are not revenue". Never
    # combine these with gifted_active_subscriptions below.
    active_paid_subscribers: int
    new_paid_subscribers: int
    cancellations: int
    movements: list[PlanMovementRowOut]
    # Gifted (provider="gifted") - reported entirely separately, never
    # counted as paid subscribers/revenue/conversions.
    gifted_active_subscriptions: int
    gifted_events_this_period: int
    # Loady does not persist each subscription's billing period (monthly vs
    # annual - see Subscription in commercial_models.py), so a true MRR
    # figure can't be computed without guessing which price applies. Per the
    # "accuracy over visual completeness" rule, MRR is omitted rather than
    # estimated - mrr_note explains why and what would need to change.
    mrr_available: bool = False
    mrr_note: str
