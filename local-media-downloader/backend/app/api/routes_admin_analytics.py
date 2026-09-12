"""Admin-only web analytics reporting. Every route requires the `admin`
role (see api/deps.require_admin) - never trust a frontend-only "isAdmin"
flag. All query ranges are a fixed, small set (see AnalyticsRange) so a
request can never trigger an unbounded/expensive scan.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.models.analytics_schemas import (
    AnalyticsOverviewOut,
    AnalyticsRange,
    DevicesOut,
    DownloadsOut,
    FunnelOut,
    GeographyOut,
    PagesOut,
    RevenueOut,
    SourcesOut,
    TrafficOut,
)
from app.services import analytics_service

router = APIRouter(prefix="/api/admin/analytics", tags=["admin-analytics"], dependencies=[Depends(require_admin)])


@router.get("/overview", response_model=AnalyticsOverviewOut)
async def overview(range: AnalyticsRange = Query(default="30d"), db: Session = Depends(get_db)) -> AnalyticsOverviewOut:
    return analytics_service.get_overview(db, range)


@router.get("/traffic", response_model=TrafficOut)
async def traffic(range: AnalyticsRange = Query(default="30d"), db: Session = Depends(get_db)) -> TrafficOut:
    return analytics_service.get_traffic(db, range)


@router.get("/pages", response_model=PagesOut)
async def pages(range: AnalyticsRange = Query(default="30d"), db: Session = Depends(get_db)) -> PagesOut:
    return analytics_service.get_pages(db, range)


@router.get("/sources", response_model=SourcesOut)
async def sources(range: AnalyticsRange = Query(default="30d"), db: Session = Depends(get_db)) -> SourcesOut:
    return analytics_service.get_sources(db, range)


@router.get("/geography", response_model=GeographyOut)
async def geography(range: AnalyticsRange = Query(default="30d"), db: Session = Depends(get_db)) -> GeographyOut:
    return analytics_service.get_geography(db, range)


@router.get("/devices", response_model=DevicesOut)
async def devices(range: AnalyticsRange = Query(default="30d"), db: Session = Depends(get_db)) -> DevicesOut:
    return analytics_service.get_devices(db, range)


@router.get("/downloads", response_model=DownloadsOut)
async def downloads(range: AnalyticsRange = Query(default="30d"), db: Session = Depends(get_db)) -> DownloadsOut:
    return analytics_service.get_downloads(db, range)


@router.get("/funnel", response_model=FunnelOut)
async def funnel(range: AnalyticsRange = Query(default="30d"), db: Session = Depends(get_db)) -> FunnelOut:
    return analytics_service.get_funnel(db, range)


@router.get("/revenue", response_model=RevenueOut)
async def revenue(range: AnalyticsRange = Query(default="30d"), db: Session = Depends(get_db)) -> RevenueOut:
    return analytics_service.get_revenue(db, range)
