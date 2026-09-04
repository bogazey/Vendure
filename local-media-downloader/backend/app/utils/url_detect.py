"""Platform detection and coarse URL validation.

Extraction itself is always delegated to yt-dlp; this module only decides
which platform badge to show and rejects obviously invalid input early.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from app.models.enums import Platform

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)

_PLATFORM_HOSTS: dict[Platform, tuple[str, ...]] = {
    Platform.YOUTUBE: ("youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "music.youtube.com"),
    Platform.TIKTOK: ("tiktok.com", "www.tiktok.com", "vm.tiktok.com", "vt.tiktok.com", "m.tiktok.com"),
    Platform.INSTAGRAM: ("instagram.com", "www.instagram.com"),
    Platform.FACEBOOK: ("facebook.com", "www.facebook.com", "m.facebook.com", "fb.watch"),
}


def is_valid_url(url: str) -> bool:
    if not url or len(url) > 2048:
        return False
    if not _URL_RE.match(url.strip()):
        return False
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return False
    return bool(parsed.netloc)


def detect_platform(url: str) -> Platform:
    if not is_valid_url(url):
        return Platform.UNKNOWN
    host = urlparse(url.strip()).netloc.lower()
    for platform, hosts in _PLATFORM_HOSTS.items():
        if host in hosts:
            return platform
    return Platform.UNKNOWN


def is_supported_platform(platform: Platform) -> bool:
    return platform != Platform.UNKNOWN


def looks_like_playlist_url(url: str) -> bool:
    parsed = urlparse(url.strip())
    return "list=" in parsed.query
