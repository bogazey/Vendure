"""Minimal, dependency-free User-Agent parsing for aggregate analytics only.

Deliberately not a full UA-parser library (avoids a new dependency for a
handful of coarse buckets - see docs/ANALYTICS.md "Devices & Browsers").
Returns broad families only; the raw User-Agent string itself is never
persisted (see analytics_service.record_event).
"""
from __future__ import annotations

import re


def parse_device_type(user_agent: str | None) -> str:
    if not user_agent:
        return "other"
    ua = user_agent.lower()
    if "ipad" in ua or ("tablet" in ua) or ("android" in ua and "mobile" not in ua):
        return "tablet"
    if "mobi" in ua or "iphone" in ua or "ipod" in ua:
        return "mobile"
    if any(marker in ua for marker in ("windows", "macintosh", "mac os x", "linux", "x11", "cros")):
        return "desktop"
    return "other"


def parse_browser_family(user_agent: str | None) -> str:
    if not user_agent:
        return "other"
    ua = user_agent
    # Order matters: many browsers include "Safari" or "Chrome" tokens for
    # WebKit/Blink compatibility, so the more specific engine must be
    # checked first.
    if re.search(r"edg/|edga/|edgios/", ua, re.IGNORECASE):
        return "edge"
    if re.search(r"opr/|opera", ua, re.IGNORECASE):
        return "other"
    if re.search(r"firefox/|fxios/", ua, re.IGNORECASE):
        return "firefox"
    if re.search(r"crios/|chrome/|chromium/", ua, re.IGNORECASE):
        return "chrome"
    if re.search(r"safari/", ua, re.IGNORECASE) and "version/" in ua.lower():
        return "safari"
    return "other"


def parse_os_family(user_agent: str | None) -> str:
    if not user_agent:
        return "other"
    ua = user_agent.lower()
    if "android" in ua:
        return "android"
    if "iphone" in ua or "ipad" in ua or "ipod" in ua:
        return "ios"
    if "mac os x" in ua or "macintosh" in ua:
        return "macos"
    if "windows" in ua:
        return "windows"
    if "linux" in ua:
        return "linux"
    return "other"
