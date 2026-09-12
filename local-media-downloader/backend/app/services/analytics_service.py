"""First-party, privacy-conscious web analytics: visitor identification,
event recording, and admin reporting queries.

Nothing here stores a media URL, a raw IP address, or a full User-Agent -
see docs/ANALYTICS.md for the full privacy model. This module is the ONLY
writer of AnalyticsEvent rows and the only place admin reporting queries
live, so every metric definition has exactly one implementation.
"""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from fastapi import Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import VISITOR_COOKIE_NAME
from app.config.commercial_settings import get_commercial_settings
from app.database.commercial_models import AnalyticsEvent, Subscription, User
from app.models.analytics_schemas import (
    AnalyticsOverviewOut,
    AnalyticsRange,
    BreakdownRowOut,
    CountryRowOut,
    DevicesOut,
    DownloadsOut,
    FailureRowOut,
    FunnelOut,
    FunnelStageOut,
    GeographyOut,
    PagesOut,
    PlanMovementRowOut,
    PlatformRowOut,
    RevenueOut,
    SourceRowOut,
    SourcesOut,
    StageStatsOut,
    TopPageOut,
    TrafficOut,
    TrafficPointOut,
)
from app.models.commercial_enums import AnalyticsEventType, SubscriptionProvider
from app.models.schemas import CreateDownloadRequest
from app.utils.bot_detect import is_probable_bot
from app.utils.exceptions import (
    AgeRestrictedError,
    DiskFullError,
    ExtractorFailureError,
    FfmpegMissingError,
    FfmpegProcessingError,
    FormatUnavailableError,
    GeoRestrictedError,
    InvalidPathError,
    NetworkError,
    NoDownloadableMediaError,
    PermissionDeniedError,
    PrivateOrLoginRequiredError,
    RateLimitedError,
    UnavailableMediaError,
    UnsupportedUrlError,
)
from app.utils.ua_parse import parse_browser_family, parse_device_type, parse_os_family

_VISITOR_COOKIE_TTL_DAYS = 365
ACTIVE_NOW_WINDOW_MINUTES = 5

# ---------- Visitor identity ----------


def ensure_visitor_id(request: Request, response: Response) -> str:
    """Reads the visitor cookie, minting a new opaque random one if absent.
    This id grants no privilege (unlike the guest download-quota cookie in
    guest_service.py) - it is never checked against a server-side row, so a
    forged or cleared value only ever affects that one browser's own
    analytics, never another visitor's data or any entitlement."""
    existing = request.cookies.get(VISITOR_COOKIE_NAME)
    if existing:
        return existing
    settings = get_commercial_settings()
    visitor_id = secrets.token_urlsafe(24)
    response.set_cookie(
        VISITOR_COOKIE_NAME,
        visitor_id,
        max_age=_VISITOR_COOKIE_TTL_DAYS * 24 * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        domain=settings.cookie_domain,
        path="/",
    )
    return visitor_id


def read_visitor_id(request: Request) -> str | None:
    return request.cookies.get(VISITOR_COOKIE_NAME)


# ---------- Request context (derived server-side only) ----------


def request_is_bot(request: Request) -> bool:
    return is_probable_bot(request.headers.get("user-agent"))


def request_country_code(request: Request) -> str | None:
    """Cloudflare-provided country only (see frontend/nginx.conf, which
    forwards CF-IPCountry verbatim from Cloudflare's edge - trustworthy here
    because only Cloudflare can reach this origin). "XX" is Cloudflare's own
    "could not determine" sentinel and is treated the same as absent. There
    is no other geolocation source, and no persisted IP address anywhere in
    Loady to derive one from."""
    country = (request.headers.get("cf-ipcountry") or "").strip().upper()
    if len(country) == 2 and country != "XX":
        return country
    return None


def request_device_context(request: Request) -> dict[str, str]:
    ua = request.headers.get("user-agent")
    return {
        "device_type": parse_device_type(ua),
        "browser_family": parse_browser_family(ua),
        "os_family": parse_os_family(ua),
    }


_SELF_HOST_STRIP_RE = re.compile(r"^www\.", re.IGNORECASE)


def extract_referrer_domain(referrer: str | None, request: Request) -> str | None:
    """Registrable domain only - never the full referring URL, which could
    carry a search query, a session token, or other sensitive path/query
    data. Returns None for empty/invalid/self-referrals (in-app SPA
    navigation), which the reporting layer buckets as "Direct"."""
    if not referrer:
        return None
    try:
        parsed = urlparse(referrer)
    except ValueError:
        return None
    domain = _SELF_HOST_STRIP_RE.sub("", (parsed.netloc or "").lower())
    if not domain:
        return None
    own_host = _SELF_HOST_STRIP_RE.sub("", (request.headers.get("host") or "").lower().split(":")[0])
    if own_host and domain == own_host:
        return None
    return domain[:255]


_UTM_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,100}$")


def sanitize_utm(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    return value if _UTM_RE.match(value) else None


# ---------- Path normalization ----------

_STATIC_PATHS = {
    "/", "/pricing", "/login", "/signup", "/forgot-password", "/reset-password",
    "/verify-email", "/terms", "/privacy", "/copyright", "/acceptable-use",
    "/refund-policy", "/dashboard", "/history", "/settings", "/account",
    "/billing", "/usage", "/admin", "/admin/users", "/admin/billing",
    "/admin/activity", "/admin/system", "/admin/ads", "/admin/statistics",
}
_LOCALE_TOOL_RE = re.compile(r"^/(en|ar)(/(video-downloader|audio-downloader|image-downloader))?/?$")


def normalize_path(raw_path: str) -> str:
    """Collapses a raw SPA path into a bounded, known set of canonical page
    keys. EN/AR variants of the same logical SEO page (e.g. /en/video-
    downloader and /ar/video-downloader) aggregate under one canonical path
    (/video-downloader) for the Top Pages report - locale is tracked
    separately via the `locale` field. Anything unrecognized (which should
    never happen from Loady's own frontend, only from a malformed or forged
    request) buckets into "/other" rather than persisting an arbitrary
    attacker-controlled string."""
    path = (raw_path or "/").split("?", 1)[0].split("#", 1)[0]
    if len(path) > 1:
        path = path.rstrip("/")
    if path == "":
        path = "/"
    if path in _STATIC_PATHS:
        return path
    match = _LOCALE_TOOL_RE.match(path)
    if match:
        tool = match.group(3)
        return f"/{tool}" if tool else "/"
    return "/other"


# ---------- Download format / failure classification ----------


def derive_format_label(request: CreateDownloadRequest) -> str:
    """A small, bounded set of format labels for aggregate reporting -
    mirrors the same shape download_manager._save_history already uses for
    history, without repeating any user-chosen filename/title."""
    media_type = request.media_type.value
    if media_type == "audio":
        return (request.audio_format or "best").lower()
    if media_type == "image":
        return "image"
    if request.quality_key == "best":
        return "best_available"
    if request.quality_key.isdigit():
        return f"{request.quality_key}p"
    return "advanced"


_FAILURE_MAP: tuple[tuple[tuple[type[Exception], ...], str], ...] = (
    ((RateLimitedError,), "rate_limited"),
    ((UnsupportedUrlError,), "unsupported_source"),
    (
        (UnavailableMediaError, NoDownloadableMediaError, PrivateOrLoginRequiredError,
         GeoRestrictedError, AgeRestrictedError, ExtractorFailureError),
        "metadata_failure",
    ),
    ((FormatUnavailableError,), "format_unavailable"),
    ((FfmpegMissingError, FfmpegProcessingError), "processing_failure"),
    ((NetworkError,), "timeout"),
    ((DiskFullError, PermissionDeniedError, InvalidPathError), "download_failure"),
)


def classify_failure(exc: Exception) -> str:
    """Maps an internal exception to one sanitized, admin-safe category -
    never the exception's own message/technical detail (which can carry
    yt-dlp output or other operational detail); those stay in server logs."""
    for exc_types, category in _FAILURE_MAP:
        if isinstance(exc, exc_types):
            return category
    return "other"


# ---------- Recording ----------


def record_event(db: Session, event_type: AnalyticsEventType, **fields) -> None:
    """The single writer for analytics_events. Every caller is internal
    code, not user input - callers pass only keyword fields matching
    AnalyticsEvent's own whitelisted columns; there is no generic metadata
    blob here to smuggle arbitrary data through."""
    db.add(AnalyticsEvent(event_type=event_type.value, **fields))


# ---------- Admin reporting ----------


def resolve_range(range_key: AnalyticsRange) -> tuple[datetime, datetime]:
    """Bounds every admin analytics query to a fixed, small set of windows
    (see AnalyticsRange) so a caller can never request an arbitrarily wide,
    expensive scan - FastAPI's Literal type already rejects anything else
    with a 422 before this ever runs. "Today" is a UTC calendar day, matching
    how every timestamp in this app is stored (see UTCDateTime) - there is no
    separate "admin timezone" convention elsewhere to follow instead."""
    now = datetime.now(timezone.utc)
    if range_key == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif range_key == "7d":
        start = now - timedelta(days=7)
    elif range_key == "30d":
        start = now - timedelta(days=30)
    else:
        start = now - timedelta(days=90)
    return start, now


def _count(db: Session, *filters) -> int:
    return db.execute(select(func.count()).select_from(AnalyticsEvent).where(*filters)).scalar_one() or 0


def _distinct_visitors(db: Session, *filters) -> int:
    return db.execute(
        select(func.count(func.distinct(AnalyticsEvent.visitor_id))).where(
            AnalyticsEvent.visitor_id.is_not(None), *filters
        )
    ).scalar_one() or 0


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator * 100, 1)


def get_overview(db: Session, range_key: AnalyticsRange) -> AnalyticsOverviewOut:
    start, end = resolve_range(range_key)
    in_range = (AnalyticsEvent.timestamp >= start, AnalyticsEvent.timestamp < end)
    pv = AnalyticsEvent.event_type == AnalyticsEventType.PAGE_VIEW.value
    visitors = _distinct_visitors(db, pv, *in_range)
    page_views = _count(db, pv, *in_range)
    completed = _count(db, AnalyticsEvent.event_type == AnalyticsEventType.DOWNLOAD_COMPLETED.value, *in_range)
    failed = _count(db, AnalyticsEvent.event_type == AnalyticsEventType.DOWNLOAD_FAILED.value, *in_range)
    new_users = db.execute(
        select(func.count()).select_from(User).where(User.created_at >= start, User.created_at < end)
    ).scalar_one() or 0
    # Authoritative and paid-only: a provider="paddle" Subscription row is
    # only ever created when a real Paddle subscription is first created
    # for that user (see paddle_service._upsert_subscription_from_event) -
    # Free has no row at all - so `created_at` within the window IS the
    # moment that user first paid. Explicitly excludes provider="gifted"
    # rows (see gift_subscription_service.py) - a gifted grant is never a
    # paid conversion (see docs/ANALYTICS.md "Gifted subscriptions are not
    # revenue").
    paid_conversions = db.execute(
        select(func.count()).select_from(Subscription).where(
            Subscription.created_at >= start, Subscription.created_at < end,
            Subscription.provider == SubscriptionProvider.PADDLE.value,
        )
    ).scalar_one() or 0
    active_now_start = datetime.now(timezone.utc) - timedelta(minutes=ACTIVE_NOW_WINDOW_MINUTES)
    active_now = _distinct_visitors(db, AnalyticsEvent.timestamp >= active_now_start)
    return AnalyticsOverviewOut(
        range=range_key,
        visitors=visitors,
        page_views=page_views,
        downloads_completed=completed,
        new_users=new_users,
        paid_conversions=paid_conversions,
        active_now=active_now,
        download_success_rate=_rate(completed, completed + failed),
    )


def get_traffic(db: Session, range_key: AnalyticsRange) -> TrafficOut:
    start, end = resolve_range(range_key)
    pv = AnalyticsEvent.event_type == AnalyticsEventType.PAGE_VIEW.value
    day = func.date(AnalyticsEvent.timestamp)
    rows = db.execute(
        select(day.label("day"), func.count(func.distinct(AnalyticsEvent.visitor_id)), func.count())
        .where(pv, AnalyticsEvent.timestamp >= start, AnalyticsEvent.timestamp < end)
        .group_by(day)
        .order_by(day)
    ).all()
    points = [TrafficPointOut(date=str(d), visitors=v, page_views=p) for d, v, p in rows]
    return TrafficOut(range=range_key, points=points)


def get_pages(db: Session, range_key: AnalyticsRange) -> PagesOut:
    start, end = resolve_range(range_key)
    pv = AnalyticsEvent.event_type == AnalyticsEventType.PAGE_VIEW.value
    rows = db.execute(
        select(AnalyticsEvent.path, func.count(), func.count(func.distinct(AnalyticsEvent.visitor_id)))
        .where(pv, AnalyticsEvent.timestamp >= start, AnalyticsEvent.timestamp < end)
        .group_by(AnalyticsEvent.path)
        .order_by(func.count().desc())
        .limit(20)
    ).all()
    total_views = sum(views for _, views, _ in rows) or 0
    pages = [
        TopPageOut(path=path or "/other", views=views, visitors=visitors, pct_of_total=_rate(views, total_views) or 0.0)
        for path, views, visitors in rows
    ]
    return PagesOut(range=range_key, pages=pages)


def get_sources(db: Session, range_key: AnalyticsRange) -> SourcesOut:
    start, end = resolve_range(range_key)
    pv = AnalyticsEvent.event_type == AnalyticsEventType.PAGE_VIEW.value
    rows = db.execute(
        select(AnalyticsEvent.referrer_domain, AnalyticsEvent.utm_source, func.count(func.distinct(AnalyticsEvent.visitor_id)))
        .where(pv, AnalyticsEvent.timestamp >= start, AnalyticsEvent.timestamp < end)
        .group_by(AnalyticsEvent.referrer_domain, AnalyticsEvent.utm_source)
    ).all()
    counts: dict[str, int] = {}
    for referrer_domain, utm_source, visitors in rows:
        label = utm_source or referrer_domain or "Direct"
        counts[label] = counts.get(label, 0) + visitors
    total = sum(counts.values()) or 0
    sources = sorted(
        (SourceRowOut(source=label, visitors=v, pct_of_total=_rate(v, total) or 0.0) for label, v in counts.items()),
        key=lambda r: r.visitors,
        reverse=True,
    )[:20]
    return SourcesOut(range=range_key, sources=sources)


def get_geography(db: Session, range_key: AnalyticsRange) -> GeographyOut:
    start, end = resolve_range(range_key)
    in_range = (AnalyticsEvent.timestamp >= start, AnalyticsEvent.timestamp < end)
    pv = AnalyticsEvent.event_type == AnalyticsEventType.PAGE_VIEW.value
    dl = AnalyticsEvent.event_type == AnalyticsEventType.DOWNLOAD_COMPLETED.value
    rows = db.execute(
        select(AnalyticsEvent.country_code, func.count(func.distinct(AnalyticsEvent.visitor_id)), func.count())
        .where(pv, AnalyticsEvent.country_code.is_not(None), *in_range)
        .group_by(AnalyticsEvent.country_code)
        .order_by(func.count().desc())
        .limit(20)
    ).all()
    downloads_by_country = dict(
        db.execute(
            select(AnalyticsEvent.country_code, func.count())
            .where(dl, AnalyticsEvent.country_code.is_not(None), *in_range)
            .group_by(AnalyticsEvent.country_code)
        ).all()
    )
    countries = [
        CountryRowOut(country_code=code, visitors=v, page_views=pvs, downloads=downloads_by_country.get(code, 0))
        for code, v, pvs in rows
    ]
    return GeographyOut(range=range_key, available=bool(countries), countries=countries)


def _breakdown(db: Session, column, *filters) -> list[BreakdownRowOut]:
    rows = db.execute(
        select(column, func.count()).where(column.is_not(None), *filters).group_by(column).order_by(func.count().desc())
    ).all()
    total = sum(c for _, c in rows) or 0
    return [BreakdownRowOut(key=key, count=c, pct=_rate(c, total) or 0.0) for key, c in rows]


def get_devices(db: Session, range_key: AnalyticsRange) -> DevicesOut:
    start, end = resolve_range(range_key)
    pv = AnalyticsEvent.event_type == AnalyticsEventType.PAGE_VIEW.value
    in_range = (pv, AnalyticsEvent.timestamp >= start, AnalyticsEvent.timestamp < end)
    return DevicesOut(
        range=range_key,
        devices=_breakdown(db, AnalyticsEvent.device_type, *in_range),
        browsers=_breakdown(db, AnalyticsEvent.browser_family, *in_range),
        os=_breakdown(db, AnalyticsEvent.os_family, *in_range),
        languages=_breakdown(db, AnalyticsEvent.locale, *in_range),
    )


def _stage_stats(db: Session, start: datetime, end: datetime, started_type: str, completed_type: str, failed_type: str) -> StageStatsOut:
    in_range = (AnalyticsEvent.timestamp >= start, AnalyticsEvent.timestamp < end)
    started = _count(db, AnalyticsEvent.event_type == started_type, *in_range)
    completed = _count(db, AnalyticsEvent.event_type == completed_type, *in_range)
    failed = _count(db, AnalyticsEvent.event_type == failed_type, *in_range)
    avg_seconds = None
    if completed_type == AnalyticsEventType.DOWNLOAD_COMPLETED.value:
        # Join start/completion events for the same job_id to get a genuine
        # processing-time measurement - never a guess, and never counted for
        # a job whose start event predates the selected window (job_id join
        # only matches rows actually present, so this simply yields fewer
        # samples rather than a wrong one).
        start_alias = select(AnalyticsEvent.job_id, AnalyticsEvent.timestamp.label("started_at")).where(
            AnalyticsEvent.event_type == AnalyticsEventType.DOWNLOAD_STARTED.value, AnalyticsEvent.job_id.is_not(None)
        ).subquery()
        rows = db.execute(
            select(AnalyticsEvent.timestamp, start_alias.c.started_at)
            .join(start_alias, start_alias.c.job_id == AnalyticsEvent.job_id)
            .where(AnalyticsEvent.event_type == completed_type, *in_range)
        ).all()
        durations = [
            (completed_at - started_at).total_seconds()
            for completed_at, started_at in rows
            if completed_at is not None and started_at is not None and completed_at >= started_at
        ]
        if durations:
            avg_seconds = round(sum(durations) / len(durations), 1)
    return StageStatsOut(
        started=started, completed=completed, failed=failed,
        success_rate=_rate(completed, completed + failed), avg_processing_seconds=avg_seconds,
    )


def get_downloads(db: Session, range_key: AnalyticsRange) -> DownloadsOut:
    start, end = resolve_range(range_key)
    in_range = (AnalyticsEvent.timestamp >= start, AnalyticsEvent.timestamp < end)
    analyze = _stage_stats(
        db, start, end, AnalyticsEventType.ANALYZE_STARTED.value,
        AnalyticsEventType.ANALYZE_COMPLETED.value, AnalyticsEventType.ANALYZE_FAILED.value,
    )
    downloads = _stage_stats(
        db, start, end, AnalyticsEventType.DOWNLOAD_STARTED.value,
        AnalyticsEventType.DOWNLOAD_COMPLETED.value, AnalyticsEventType.DOWNLOAD_FAILED.value,
    )
    platform_rows = db.execute(
        select(AnalyticsEvent.source_platform, AnalyticsEvent.event_type, func.count())
        .where(
            AnalyticsEvent.source_platform.is_not(None),
            AnalyticsEvent.event_type.in_([
                AnalyticsEventType.ANALYZE_STARTED.value,
                AnalyticsEventType.DOWNLOAD_STARTED.value,
                AnalyticsEventType.DOWNLOAD_COMPLETED.value,
                AnalyticsEventType.DOWNLOAD_FAILED.value,
            ]),
            *in_range,
        )
        .group_by(AnalyticsEvent.source_platform, AnalyticsEvent.event_type)
    ).all()
    by_platform: dict[str, dict[str, int]] = {}
    for platform, event_type, count in platform_rows:
        by_platform.setdefault(platform, {})[event_type] = count
    platforms = [
        PlatformRowOut(
            platform=platform,
            analyses=counts.get(AnalyticsEventType.ANALYZE_STARTED.value, 0),
            downloads=counts.get(AnalyticsEventType.DOWNLOAD_STARTED.value, 0),
            successful=counts.get(AnalyticsEventType.DOWNLOAD_COMPLETED.value, 0),
            failed=counts.get(AnalyticsEventType.DOWNLOAD_FAILED.value, 0),
            success_rate=_rate(
                counts.get(AnalyticsEventType.DOWNLOAD_COMPLETED.value, 0),
                counts.get(AnalyticsEventType.DOWNLOAD_COMPLETED.value, 0) + counts.get(AnalyticsEventType.DOWNLOAD_FAILED.value, 0),
            ),
        )
        for platform, counts in sorted(by_platform.items(), key=lambda kv: sum(kv[1].values()), reverse=True)
    ]
    failure_rows = db.execute(
        select(AnalyticsEvent.failure_category, func.count())
        .where(
            AnalyticsEvent.failure_category.is_not(None),
            AnalyticsEvent.event_type.in_([AnalyticsEventType.ANALYZE_FAILED.value, AnalyticsEventType.DOWNLOAD_FAILED.value]),
            *in_range,
        )
        .group_by(AnalyticsEvent.failure_category)
        .order_by(func.count().desc())
    ).all()
    failures = [FailureRowOut(category=cat, count=c) for cat, c in failure_rows]
    return DownloadsOut(range=range_key, analyze=analyze, downloads=downloads, platforms=platforms, failures=failures)


def get_funnel(db: Session, range_key: AnalyticsRange) -> FunnelOut:
    start, end = resolve_range(range_key)
    in_range = (AnalyticsEvent.timestamp >= start, AnalyticsEvent.timestamp < end)
    visitors = _distinct_visitors(db, AnalyticsEvent.event_type == AnalyticsEventType.PAGE_VIEW.value, *in_range)
    analyzed = _distinct_visitors(db, AnalyticsEvent.event_type == AnalyticsEventType.ANALYZE_STARTED.value, *in_range)
    downloaded = _distinct_visitors(db, AnalyticsEvent.event_type == AnalyticsEventType.DOWNLOAD_STARTED.value, *in_range)
    signed_up = db.execute(
        select(func.count()).select_from(User).where(User.created_at >= start, User.created_at < end)
    ).scalar_one() or 0
    paid = db.execute(
        select(func.count()).select_from(Subscription).where(Subscription.created_at >= start, Subscription.created_at < end)
    ).scalar_one() or 0
    stages_raw = [
        ("visitors", "Visitors", visitors),
        ("analyzed", "Analyzed", analyzed),
        ("downloaded", "Downloaded", downloaded),
        ("signed_up", "Signed up", signed_up),
        ("paid", "Paid", paid),
    ]
    stages: list[FunnelStageOut] = []
    previous: int | None = None
    for key, label, count in stages_raw:
        stages.append(FunnelStageOut(key=key, label=label, count=count, pct_of_previous=_rate(count, previous) if previous else None))
        previous = count
    return FunnelOut(
        range=range_key,
        stages=stages,
        methodology_note=(
            "Aggregate counts for the selected period, not a per-visitor cohort funnel - "
            "a visitor counted at one stage is not guaranteed to be the same person counted at the next."
        ),
    )


def get_revenue(db: Session, range_key: AnalyticsRange) -> RevenueOut:
    from app.services.account_service import ACTIVE_SUBSCRIPTION_STATUSES

    start, end = resolve_range(range_key)
    in_range = (AnalyticsEvent.timestamp >= start, AnalyticsEvent.timestamp < end)
    # Every count below is restricted to provider="paddle" - these are
    # revenue/paid-conversion figures and must never include a gifted
    # subscription (see gift_subscription_service.py and
    # docs/ANALYTICS.md "Gifted subscriptions are not revenue"). Gifted
    # activity is reported entirely separately below, never summed in.
    active_paid = db.execute(
        select(func.count()).select_from(Subscription).where(
            Subscription.status.in_(ACTIVE_SUBSCRIPTION_STATUSES),
            Subscription.provider == SubscriptionProvider.PADDLE.value,
        )
    ).scalar_one() or 0
    new_paid = db.execute(
        select(func.count()).select_from(Subscription).where(
            Subscription.created_at >= start, Subscription.created_at < end,
            Subscription.provider == SubscriptionProvider.PADDLE.value,
        )
    ).scalar_one() or 0
    cancellations = _count(db, AnalyticsEvent.event_type == AnalyticsEventType.SUBSCRIPTION_CANCELLED.value, *in_range)
    movement_rows = db.execute(
        select(AnalyticsEvent.from_plan, AnalyticsEvent.plan, func.count())
        .where(
            AnalyticsEvent.event_type.in_([AnalyticsEventType.PLAN_UPGRADED.value, AnalyticsEventType.PLAN_DOWNGRADED.value]),
            AnalyticsEvent.from_plan.is_not(None),
            AnalyticsEvent.plan.is_not(None),
            *in_range,
        )
        .group_by(AnalyticsEvent.from_plan, AnalyticsEvent.plan)
    ).all()
    movements = [PlanMovementRowOut(kind=f"{frm}_to_{to}", count=c) for frm, to, c in movement_rows]

    # Gifted Subscriptions: counted and reported entirely separately - see
    # AdminOverviewOut.gifted_subscribers for the same rule applied to the
    # admin Overview page. Never combined with active_paid/new_paid above.
    gifted_active = db.execute(
        select(func.count(func.distinct(Subscription.user_id))).where(
            Subscription.status.in_(ACTIVE_SUBSCRIPTION_STATUSES),
            Subscription.provider == SubscriptionProvider.GIFTED.value,
        )
    ).scalar_one() or 0
    gifted_events_this_period = _count(
        db,
        AnalyticsEvent.event_type.in_([
            AnalyticsEventType.GIFTED_SUBSCRIPTION_GRANTED.value,
            AnalyticsEventType.GIFTED_SUBSCRIPTION_CHANGED.value,
            AnalyticsEventType.GIFTED_SUBSCRIPTION_REVOKED.value,
        ]),
        *in_range,
    )

    return RevenueOut(
        range=range_key,
        active_paid_subscribers=active_paid,
        new_paid_subscribers=new_paid,
        cancellations=cancellations,
        movements=movements,
        gifted_active_subscriptions=gifted_active,
        gifted_events_this_period=gifted_events_this_period,
        mrr_available=False,
        mrr_note=(
            "MRR is not shown because Loady does not persist each subscription's billing period "
            "(monthly vs annual), so a monthly-normalized revenue figure can't be computed without "
            "guessing which price applies. Persisting billing_period on Subscription would unlock this."
        ),
    )


def purge_expired_events(db: Session) -> int:
    """Deletes analytics_events older than ANALYTICS_RETENTION_DAYS. Called
    from the existing periodic media-cleanup loop (see
    media_cleanup_service.py) rather than a new scheduler."""
    settings = get_commercial_settings()
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.analytics_retention_days)
    result = db.execute(
        AnalyticsEvent.__table__.delete().where(AnalyticsEvent.timestamp < cutoff)
    )
    return result.rowcount or 0
