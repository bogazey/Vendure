"""Minimal analytics bot filtering.

This is NOT a security/firewall control - it only decides whether a request
looks like an automated crawler for the purposes of keeping human traffic
statistics honest. It must never be used to block a request (SEO crawling,
including Googlebot/Bingbot, must keep working exactly as before).
"""
from __future__ import annotations

import re

# Common, well-known crawler/bot substrings. Deliberately conservative (a
# missed bot just slightly inflates a stat; a false positive on a genuine
# human User-Agent would undercount real traffic, which is worse).
_BOT_MARKERS = re.compile(
    r"bot|crawler|spider|slurp|crawling|"
    r"googlebot|bingbot|yandexbot|duckduckbot|baiduspider|"
    r"facebookexternalhit|twitterbot|linkedinbot|whatsapp|telegrambot|"
    r"ahrefsbot|semrushbot|mj12bot|dotbot|petalbot|bytespider|"
    r"applebot|ia_archiver|archive\.org_bot|headlesschrome|phantomjs|"
    r"curl/|wget/|python-requests|axios/|go-http-client|okhttp|postmanruntime",
    re.IGNORECASE,
)


def is_probable_bot(user_agent: str | None) -> bool:
    if not user_agent:
        # A genuine browser always sends a User-Agent; a missing one is far
        # more likely a script than a human visitor.
        return True
    return bool(_BOT_MARKERS.search(user_agent))
