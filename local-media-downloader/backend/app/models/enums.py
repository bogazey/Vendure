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


class ContainerMode(str, Enum):
    """How video downloads pick their final container/codec.

    COMPATIBILITY (default): always ends in a genuine, broadly-playable MP4
    (H.264 + AAC), transcoding via FFmpeg when the source streams are
    WebM/VP9/AV1/Opus rather than just renaming the file.
    ORIGINAL: keeps whatever container/codec the best source streams
    naturally use (may be WebM/MKV), never transcodes.
    """

    COMPATIBILITY = "compatibility"
    ORIGINAL = "original"


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
