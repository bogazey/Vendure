from __future__ import annotations

from enum import Enum


class Platform(str, Enum):
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"
    INSTAGRAM = "instagram"
    FACEBOOK = "facebook"
    UNKNOWN = "unknown"


class MediaType(str, Enum):
    VIDEO = "video"
    AUDIO = "audio"


class DownloadStage(str, Enum):
    QUEUED = "queued"
    ANALYZING = "analyzing"
    DOWNLOADING = "downloading"
    MERGING = "merging"
    CONVERTING = "converting"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class FormatKind(str, Enum):
    VIDEO = "video"
    AUDIO = "audio"


class ContainerPref(str, Enum):
    AUTO = "auto"
    MP4 = "mp4"
    MKV = "mkv"


class Theme(str, Enum):
    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


class CookieSource(str, Enum):
    NONE = "none"
    CHROME = "chrome"
    FIREFOX = "firefox"
    EDGE = "edge"
    SAFARI = "safari"
    FILE = "file"
