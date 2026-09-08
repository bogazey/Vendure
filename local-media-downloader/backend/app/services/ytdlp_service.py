"""Thin, typed wrapper around yt-dlp for metadata extraction and downloads.

All extraction logic is delegated to yt-dlp itself; this module only adapts
its output to our Pydantic schemas and translates its errors into the app's
friendly exception types. No site-specific scraping or DRM/paywall bypass
logic lives here.
"""
from __future__ import annotations

import os
import re
import shutil
from typing import Any, Callable, Optional
from urllib.parse import urlparse

import yt_dlp
from yt_dlp.utils import DownloadCancelled, DownloadError

from app.config.logging_config import get_logger
from app.models.enums import ContainerMode, CookieSource, FormatKind, MediaType, Platform
from app.models.schemas import (
    AnalyzeResponse,
    AppSettings,
    ClipRange,
    CreateDownloadRequest,
    FormatOption,
    MediaEntryOut,
    PlaylistEntryPreview,
    QualityPreset,
)
from app.utils.exceptions import (
    AgeRestrictedError,
    AppError,
    DiskFullError,
    ExtractorFailureError,
    FfmpegMissingError,
    GeoRestrictedError,
    NetworkError,
    NoDownloadableMediaError,
    PermissionDeniedError,
    PrivateOrLoginRequiredError,
    UnavailableMediaError,
    UnsupportedUrlError,
)
from app.utils.timecode import validate_clip_range
from app.utils.url_detect import detect_platform, is_supported_platform, looks_like_playlist_url
from app.services import tiktok_photo_service

logger = get_logger("ytdlp")

VIDEO_HEIGHT_PRESETS = [2160, 1440, 1080, 720, 480, 360]


def get_ytdlp_version() -> str:
    return yt_dlp.version.__version__


# Homebrew doesn't always end up on PATH for GUI-launched processes (Apple
# Silicon installs to /opt/homebrew, Intel to /usr/local); check the common
# install locations directly as a fallback so the app doesn't misreport
# FFmpeg as "missing" on a correctly-set-up Mac.
_FFMPEG_FALLBACK_PATHS = (
    "/opt/homebrew/bin/ffmpeg",
    "/usr/local/bin/ffmpeg",
    "/usr/bin/ffmpeg",
)


def check_ffmpeg() -> tuple[bool, Optional[str]]:
    path = shutil.which("ffmpeg")
    if path:
        return True, path

    for candidate in _FFMPEG_FALLBACK_PATHS:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return True, candidate
    return False, None


def classify_error(exc: Exception, url: str = "") -> Exception:
    """Map a yt-dlp/OS exception to one of our friendly AppError subclasses."""
    if isinstance(exc, AppError):
        return exc

    text = str(exc).lower()

    if isinstance(exc, FileNotFoundError) and "ffmpeg" in text:
        return FfmpegMissingError(
            "FFmpeg is required for this operation but was not found.",
            technical=str(exc),
        )
    if "ffmpeg" in text and "not found" in text:
        return FfmpegMissingError(
            "FFmpeg is required for this operation but was not found.",
            technical=str(exc),
        )
    if isinstance(exc, OSError) and getattr(exc, "errno", None) == 28:
        return DiskFullError("The download destination is out of disk space.", technical=str(exc))
    if any(k in text for k in ("no space left on device", "disk full")):
        return DiskFullError("The download destination is out of disk space.", technical=str(exc))
    if isinstance(exc, PermissionError) or "permission denied" in text or "not writable" in text:
        return PermissionDeniedError(
            "Permission denied writing to the download folder. Choose a different folder in Settings.",
            technical=str(exc),
        )
    if "cookie" in text and any(k in text for k in ("no such file", "not found", "could not open", "unable to open")):
        return PrivateOrLoginRequiredError(
            "Could not read the configured cookie file. Check the cookie file path in Settings.",
            technical=str(exc),
        )
    if any(
        k in text
        for k in (
            "private video",
            "login required",
            "requires authentication",
            "rate-limit reached",
            "rate-limit for accessing posts anonymously",
            "only available for registered users",
            "redirected to the login page",
        )
    ):
        return PrivateOrLoginRequiredError(
            "Instagram requires authentication to access this post."
            if "instagram" in text or detect_platform(url) == Platform.INSTAGRAM
            else "This content is private or requires a logged-in session. "
            "Add browser cookies in Settings if you have access.",
            technical=str(exc),
        )
    if "empty media response" in text:
        return UnavailableMediaError(
            "This post is unavailable or you may not have access to it.", technical=str(exc)
        )
    if any(k in text for k in ("no video in this post", "no formats")):
        return NoDownloadableMediaError(
            "This post does not contain downloadable media.", technical=str(exc)
        )
    if "age" in text and "restrict" in text:
        return AgeRestrictedError(
            "This content is age-restricted and could not be accessed.",
            technical=str(exc),
        )
    if "not available in your country" in text or "geo" in text and "restrict" in text:
        return GeoRestrictedError(
            "This content is not available in your region.", technical=str(exc)
        )
    if any(k in text for k in ("video unavailable", "has been removed", "no longer available", "404")):
        return UnavailableMediaError(
            "This content is unavailable or has been removed.", technical=str(exc)
        )
    if any(k in text for k in ("unsupported url", "no extractor", "is not a valid url")):
        return UnsupportedUrlError(
            "This URL isn't supported. Only YouTube, TikTok, Instagram, and Facebook links are supported.",
            technical=str(exc),
        )
    if any(k in text for k in ("urlopen error", "timed out", "connection", "network", "temporary failure")):
        return NetworkError(
            "A network error occurred while contacting the platform. Check your connection and try again.",
            technical=str(exc),
        )
    return ExtractorFailureError(
        "This content could not be processed. It may be unavailable or unsupported.",
        technical=str(exc),
    )


def _cookie_opts(settings: AppSettings) -> dict[str, Any]:
    opts: dict[str, Any] = {}
    if settings.cookie_source == CookieSource.FILE and settings.cookie_file_path:
        opts["cookiefile"] = settings.cookie_file_path
    elif settings.cookie_source in (
        CookieSource.CHROME, CookieSource.FIREFOX, CookieSource.EDGE, CookieSource.SAFARI,
    ):
        opts["cookiesfrombrowser"] = (settings.cookie_source.value,)
    return opts


def _base_opts(settings: AppSettings) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "socket_timeout": settings.network_timeout_seconds,
        "retries": settings.retries,
        "logger": _YtdlpLogAdapter(),
        # Some extractors (e.g. Instagram single-image posts) call
        # raise_no_formats()/raise_login_required(metadata_available=True)
        # whenever a post genuinely has no video formats. Without this, that
        # raises before we ever see the info dict - even though the post's
        # metadata (including its actual image URLs, under `thumbnails`) was
        # already fetched. This only changes behavior for extractions that
        # would otherwise hard-fail with "no formats"; a normal video/audio
        # extraction is unaffected.
        "ignore_no_formats_error": True,
    }
    ffmpeg_available, ffmpeg_path = check_ffmpeg()
    if ffmpeg_available and ffmpeg_path:
        # Point yt-dlp at the exact binary our own health check found, rather
        # than letting it re-search PATH (which may resolve differently, e.g.
        # under a GUI-launched process with a thinner PATH than a terminal).
        opts["ffmpeg_location"] = ffmpeg_path
    opts.update(_cookie_opts(settings))
    return opts


_SENSITIVE_LOG_PATTERN = re.compile(
    r"(cookie|authorization|set-cookie)\s*:\s*\S+", re.IGNORECASE
)


def _redact(msg: str) -> str:
    """Defense-in-depth scrub: yt-dlp's normal (non-verbose) logging never
    includes raw cookie/auth header values, but this strips them if it ever
    did, so a cookie can never end up in the log file."""
    return _SENSITIVE_LOG_PATTERN.sub(lambda m: f"{m.group(1)}: [redacted]", msg)


class _YtdlpLogAdapter:
    """Routes yt-dlp's internal logging into our rotating app log, without leaking cookies."""

    def debug(self, msg: str) -> None:
        if msg.startswith("[debug] "):
            return
        logger.debug(_redact(msg))

    def info(self, msg: str) -> None:
        logger.info(_redact(msg))

    def warning(self, msg: str) -> None:
        logger.warning(_redact(msg))

    def error(self, msg: str) -> None:
        logger.error(_redact(msg))


def _format_to_option(fmt: dict[str, Any]) -> FormatOption:
    vcodec = fmt.get("vcodec")
    acodec = fmt.get("acodec")
    has_video = bool(vcodec and vcodec != "none")
    has_audio = bool(acodec and acodec != "none")
    kind = FormatKind.VIDEO if has_video else FormatKind.AUDIO
    return FormatOption(
        format_id=fmt.get("format_id", ""),
        kind=kind,
        ext=fmt.get("ext", ""),
        resolution=fmt.get("resolution"),
        height=fmt.get("height"),
        fps=fmt.get("fps"),
        vcodec=vcodec if has_video else None,
        acodec=acodec if has_audio else None,
        abr=fmt.get("abr"),
        vbr=fmt.get("vbr"),
        filesize=fmt.get("filesize"),
        filesize_approx=fmt.get("filesize_approx"),
        has_video=has_video,
        has_audio=has_audio,
        note=fmt.get("format_note"),
    )


# --- Image support (e.g. Instagram single-image posts and carousels) ------
#
# yt-dlp has no first-class "image" media type: an image-only extraction
# result carries no `formats` at all, just `thumbnails` (the image itself,
# at various resolutions - for Instagram this candidate list already IS the
# actual photo, not a separate small preview). These helpers are the only
# place that reads that shape.

_IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "gif", "heic", "bmp", "tiff"}


def _guess_image_ext(url: str) -> str:
    suffix = os.path.splitext(urlparse(url).path)[1].lstrip(".").lower()
    if suffix == "jpeg":
        return "jpg"
    if suffix in _IMAGE_EXTS:
        return suffix
    return "jpg"


def _pick_best_image(info: dict[str, Any]) -> Optional[tuple[str, Optional[int], Optional[int], str]]:
    """Picks the highest-resolution image candidate for an image-only
    extraction result. Never assumes list ordering (some extractors sort
    largest-first, some smallest-first) - always compares by area."""
    candidates: list[dict[str, Any]] = list(info.get("thumbnails") or [])
    thumb = info.get("thumbnail")
    if thumb and not any(c.get("url") == thumb for c in candidates):
        candidates = [*candidates, {"url": thumb}]
    candidates = [c for c in candidates if c.get("url")]
    if not candidates:
        return None

    best = max(candidates, key=lambda c: (c.get("width") or 0) * (c.get("height") or 0))
    url = best["url"]
    return url, best.get("width"), best.get("height"), _guess_image_ext(url)


def _entry_media_type_and_formats(entry: dict[str, Any]) -> tuple[Optional[MediaType], list[FormatOption]]:
    """Classifies one extraction result (top-level or one carousel entry):
    VIDEO if it has any downloadable format, IMAGE if it has no formats but
    does have an image, otherwise None (genuinely no downloadable media)."""
    formats = [_format_to_option(f) for f in entry.get("formats") or [] if f.get("format_id")]
    if formats:
        return MediaType.VIDEO, formats
    if _pick_best_image(entry) is not None:
        return MediaType.IMAGE, []
    return None, []


def _build_media_entry(index: int, entry: dict[str, Any]) -> Optional[MediaEntryOut]:
    media_type, _formats = _entry_media_type_and_formats(entry)
    if media_type == MediaType.VIDEO:
        return MediaEntryOut(
            index=index,
            media_type=MediaType.VIDEO,
            title=entry.get("title"),
            thumbnail=entry.get("thumbnail"),
            duration=entry.get("duration"),
        )
    if media_type == MediaType.IMAGE:
        image = _pick_best_image(entry)
        image_url, image_width, image_height, image_ext = image if image else (None, None, None, None)
        return MediaEntryOut(
            index=index,
            media_type=MediaType.IMAGE,
            title=entry.get("title"),
            thumbnail=entry.get("thumbnail") or image_url,
            image_url=image_url,
            image_width=image_width,
            image_height=image_height,
            image_ext=image_ext,
        )
    return None


# --- MP4 (H.264 + AAC) compatibility detection -----------------------------
#
# yt-dlp's own `merge_output_format`/rename-based approaches can produce a
# ".mp4" file that actually contains VP9/AV1 video or Opus audio, which many
# players (QuickTime, older TVs, etc.) refuse to play - a "fake" MP4. This app
# never does that: it only reports a stream as MP4-compatible when the codec
# itself is H.264 (+AAC), and otherwise genuinely transcodes with FFmpeg (see
# download_manager._blocking_download / needs_mp4_transcode below).
_MP4_COMPATIBLE_VIDEO_PREFIXES = ("avc1", "h264")
_MP4_COMPATIBLE_AUDIO_PREFIXES = ("mp4a", "aac")


def _is_mp4_compatible_video_codec(vcodec: Optional[str]) -> bool:
    return bool(vcodec) and vcodec != "none" and vcodec.lower().startswith(_MP4_COMPATIBLE_VIDEO_PREFIXES)


def _is_mp4_compatible_audio_codec(acodec: Optional[str]) -> bool:
    return bool(acodec) and acodec != "none" and acodec.lower().startswith(_MP4_COMPATIBLE_AUDIO_PREFIXES)


def _has_compatible_mp4_video(formats: list[FormatOption], max_height: Optional[int]) -> bool:
    """Whether an H.264 video stream exists (at or under max_height, if given).

    Used to both bias the download format selector toward native MP4 (so we
    only transcode when actually necessary) and to predict the "expected
    container" shown in the UI before downloading.
    """
    for f in formats:
        if not f.has_video or not _is_mp4_compatible_video_codec(f.vcodec):
            continue
        if max_height is not None and f.height and f.height > max_height:
            continue
        return True
    return False


def needs_mp4_transcode(info: dict[str, Any]) -> bool:
    """Given yt-dlp's final info dict for a completed video download, whether
    the actual downloaded streams are NOT already H.264 video + AAC/M4A audio
    - i.e. whether Compatibility mode must run FFmpeg to produce a genuine
    MP4, rather than a plain remux (or nothing at all)."""
    parts = info.get("requested_formats") or [info]
    video_ok = True
    audio_ok = True
    for part in parts:
        vcodec = part.get("vcodec")
        if vcodec and vcodec != "none":
            video_ok = _is_mp4_compatible_video_codec(vcodec)
        acodec = part.get("acodec")
        if acodec and acodec != "none":
            audio_ok = _is_mp4_compatible_audio_codec(acodec)
    return not (video_ok and audio_ok)


def _build_presets(
    formats: list[FormatOption], container_mode: ContainerMode = ContainerMode.COMPATIBILITY
) -> tuple[list[QualityPreset], list[QualityPreset]]:
    video_heights = {f.height for f in formats if f.has_video and f.height}
    has_audio_stream = any(f.has_audio for f in formats)
    compat = container_mode == ContainerMode.COMPATIBILITY

    def _video_preset(key: str, label: str, available: bool, height: Optional[int]) -> QualityPreset:
        if not available:
            return QualityPreset(key=key, label=label, kind=FormatKind.VIDEO, available=False, height=height)
        if compat:
            # Compatibility mode always ends in a genuine MP4 (transcoding if
            # needed - see needs_mp4_transcode), so the expected container is
            # always mp4; will_transcode tells the UI whether that conversion
            # step is actually expected to run for this preset.
            has_native = _has_compatible_mp4_video(formats, height)
            return QualityPreset(
                key=key, label=label, kind=FormatKind.VIDEO, available=True, height=height,
                expected_container="mp4", will_transcode=not has_native,
            )
        # Original/Best Quality mode: best-effort guess at the container the
        # highest-quality matching stream naturally uses (for display only -
        # history records the real, final container after downloading).
        candidates = [f for f in formats if f.has_video and (height is None or (f.height or 0) <= height)]
        best = max(candidates, key=lambda f: f.height or 0, default=None)
        return QualityPreset(
            key=key, label=label, kind=FormatKind.VIDEO, available=True, height=height,
            expected_container=best.ext if best else None, will_transcode=False,
        )

    video_presets = [_video_preset("best", "Best Available", bool(video_heights), None)]
    for h in VIDEO_HEIGHT_PRESETS:
        available = any(vh >= h for vh in video_heights) if video_heights else False
        video_presets.append(_video_preset(str(h), f"{h}p", available, h))

    audio_presets = [
        QualityPreset(key="best", label="Best Audio", kind=FormatKind.AUDIO, available=has_audio_stream),
        QualityPreset(key="mp3", label="MP3", kind=FormatKind.AUDIO, available=has_audio_stream, expected_container="mp3"),
        QualityPreset(key="m4a", label="M4A", kind=FormatKind.AUDIO, available=has_audio_stream, expected_container="m4a"),
    ]
    return video_presets, audio_presets


def pick_best_image(info: dict[str, Any]) -> Optional[tuple[str, Optional[int], Optional[int], str]]:
    """Public wrapper around _pick_best_image for DownloadManager's image
    download path (keeps the underscore-prefixed extraction internals
    private to this module)."""
    return _pick_best_image(info)


def _tiktok_photo_fallback(url: str, settings: AppSettings, original_error: DownloadError) -> dict[str, Any]:
    """Try the public-photo fallback without broadening normal extraction."""
    classified = classify_error(original_error, url)
    direct_photo = tiktok_photo_service.is_photo_url(url)
    short_url = tiktok_photo_service.is_short_url(url)
    if detect_platform(url) != Platform.TIKTOK or not (direct_photo or short_url):
        raise classified from original_error
    if direct_photo and not isinstance(classified, UnsupportedUrlError):
        raise classified from original_error
    try:
        return tiktok_photo_service.extract_photo_info(
            url, timeout=settings.network_timeout_seconds, retries=settings.retries
        )
    except tiktok_photo_service.NotTikTokPhotoUrl:
        # In particular, a vm/vt short link which resolves to a normal video
        # must keep yt-dlp's original behavior and friendly error mapping.
        raise classified from original_error


def extract_entry_for_download(
    url: str, settings: AppSettings, playlist_item_indices: Optional[list[int]] = None
) -> dict[str, Any]:
    """Re-extracts metadata (no download) for exactly one item of `url` -
    the whole post, or, when playlist_item_indices is given, just that one
    1-based carousel entry. Used by DownloadManager's image download path,
    which needs a fresh info dict at download time (analyze()'s cached
    response isn't threaded through to CreateDownloadRequest)."""
    opts = _base_opts(settings)
    opts["skip_download"] = True
    if playlist_item_indices:
        opts["noplaylist"] = False
        opts["playlist_items"] = ",".join(str(i) for i in playlist_item_indices)
    else:
        opts["noplaylist"] = True

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as exc:
        info = _tiktok_photo_fallback(url, settings, exc)

    if info is None:
        raise UnavailableMediaError("No media information could be extracted from this URL.")

    if info.get("_type") == "playlist":
        entries = [e for e in info.get("entries") or [] if e]
        if not entries:
            raise NoDownloadableMediaError("This post does not contain downloadable media.")
        if playlist_item_indices:
            selected = set(playlist_item_indices)
            entries = [entry for index, entry in enumerate(entries, start=1) if index in selected]
            if not entries:
                raise NoDownloadableMediaError("This post does not contain the selected media item.")
        info = entries[0]
    return info


def _analyze_carousel(url: str, platform: Platform, info: dict[str, Any]) -> AnalyzeResponse:
    """A single post that itself contains multiple full media items (e.g. an
    Instagram carousel) - yt-dlp reports this as `_type: "playlist"` with
    fully-resolved `entries` already in hand (unlike a URL-level playlist,
    where entries are IDs to analyze one at a time - see the `list=` branch
    below `analyze()`), so no second extraction pass is needed."""
    entries = [e for e in info.get("entries") or [] if e]
    media_items = [item for item in (_build_media_entry(i, e) for i, e in enumerate(entries, start=1)) if item]
    if not media_items:
        raise NoDownloadableMediaError("This post does not contain downloadable media.")

    first = media_items[0]
    return AnalyzeResponse(
        url=url,
        platform=platform,
        media_type=first.media_type,
        id=str(info.get("id") or entries[0].get("id") or ""),
        title=info.get("title") or "Untitled",
        uploader=info.get("uploader") or info.get("channel"),
        thumbnail=first.thumbnail,
        description=(info.get("description") or "")[:500] or None,
        is_playlist=True,
        playlist_title=info.get("title"),
        playlist_count=len(media_items),
        media_items=media_items,
    )


def analyze(url: str, settings: AppSettings) -> AnalyzeResponse:
    platform = detect_platform(url)
    if not is_supported_platform(platform):
        raise UnsupportedUrlError(
            "This URL isn't supported. Only YouTube, TikTok, Instagram, and Facebook links are supported."
        )

    opts = _base_opts(settings)
    opts.update({"noplaylist": True, "skip_download": True})

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as exc:
        info = _tiktok_photo_fallback(url, settings, exc)

    if info is None:
        raise UnavailableMediaError("No media information could be extracted from this URL.")

    if info.get("_type") == "playlist" and info.get("entries"):
        return _analyze_carousel(url, platform, info)

    media_type, formats = _entry_media_type_and_formats(info)
    if media_type is None:
        raise NoDownloadableMediaError("This post does not contain downloadable media.")

    if media_type == MediaType.IMAGE:
        image = _pick_best_image(info)
        if image is None:
            raise NoDownloadableMediaError("This post does not contain downloadable media.")
        image_url, image_width, image_height, image_ext = image
        return AnalyzeResponse(
            url=url,
            platform=platform,
            media_type=MediaType.IMAGE,
            id=str(info.get("id")),
            title=info.get("title") or "Untitled",
            uploader=info.get("uploader") or info.get("channel"),
            thumbnail=info.get("thumbnail") or image_url,
            description=(info.get("description") or "")[:500] or None,
            image_url=image_url,
            image_width=image_width,
            image_height=image_height,
            image_ext=image_ext,
        )

    video_presets, audio_presets = _build_presets(formats, settings.container_mode)

    response = AnalyzeResponse(
        url=url,
        platform=platform,
        media_type=MediaType.VIDEO,
        id=str(info.get("id")),
        title=info.get("title") or "Untitled",
        uploader=info.get("uploader") or info.get("channel"),
        thumbnail=info.get("thumbnail"),
        duration=info.get("duration"),
        description=(info.get("description") or "")[:500] or None,
        video_presets=video_presets,
        audio_presets=audio_presets,
        advanced_formats=formats,
    )

    if looks_like_playlist_url(url):
        try:
            playlist_opts = _base_opts(settings)
            playlist_opts.update(
                {"noplaylist": False, "extract_flat": "in_playlist", "playlistend": 6, "skip_download": True}
            )
            with yt_dlp.YoutubeDL(playlist_opts) as ydl:
                playlist_info = ydl.extract_info(url, download=False)
            entries = playlist_info.get("entries") if playlist_info else None
            if entries:
                entries = list(entries)
                response.is_playlist = True
                response.playlist_title = playlist_info.get("title")
                response.playlist_count = playlist_info.get("playlist_count") or len(entries)
                response.playlist_entries_preview = [
                    PlaylistEntryPreview(
                        id=str(e.get("id")), title=e.get("title") or "Untitled", duration=e.get("duration")
                    )
                    for e in entries[:5]
                    if e
                ]
        except DownloadError as exc:
            logger.warning("Playlist preview extraction failed: %s", exc)

    return response


def build_format_selector(
    media_type: MediaType,
    quality_key: str,
    format_id: Optional[str],
    format_has_video: Optional[bool] = None,
    format_has_audio: Optional[bool] = None,
    container_mode: ContainerMode = ContainerMode.COMPATIBILITY,
) -> str:
    if format_id:
        if format_has_video and not format_has_audio:
            # Video-only stream (e.g. a DASH video track): merge with the best
            # available audio.
            return f"{format_id}+bestaudio/{format_id}/best"
        if format_has_audio and not format_has_video:
            # Audio-only stream: download it directly. Appending "+bestaudio"
            # here would ask yt-dlp to merge two audio-only streams, which is
            # invalid and fails.
            return f"{format_id}/bestaudio/best"
        # Either already has both video and audio, or we don't know (older
        # analyze responses / manual format id) — download it as-is and let
        # yt-dlp fall back to its own best-effort selection if unavailable.
        return f"{format_id}/best"

    if media_type == MediaType.AUDIO:
        return "bestaudio/best"

    compat = container_mode == ContainerMode.COMPATIBILITY

    if quality_key == "best" or not quality_key:
        if compat:
            # Prefer the best H.264 video (any resolution) + M4A audio; if the
            # video has NO H.264 option at all (common for 4K/8K, which
            # YouTube often only offers as VP9/AV1), fall back to true best.
            # needs_mp4_transcode() + the post-download conversion step is
            # what actually *guarantees* MP4 output either way.
            return "bestvideo*[vcodec^=avc1]+bestaudio[ext=m4a]/bestvideo*[vcodec^=avc1]+bestaudio/bestvideo*+bestaudio/best"
        return "bestvideo*+bestaudio/best"

    try:
        height = int(quality_key)
    except ValueError:
        return build_format_selector(media_type, "best", None, container_mode=container_mode)

    if compat:
        # Common preset heights (1080p and below) almost always have a native
        # H.264 option, so prefer it and avoid an unnecessary transcode;
        # still falls back to any codec at that height (and ultimately to the
        # post-download conversion step) if not.
        return (
            f"bestvideo[vcodec^=avc1][height<={height}]+bestaudio[ext=m4a]"
            f"/bestvideo[vcodec^=avc1][height<={height}]+bestaudio"
            f"/bestvideo[height<={height}]+bestaudio"
            f"/best[height<={height}]"
        )
    return f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"


def build_download_opts(
    request: CreateDownloadRequest,
    settings: AppSettings,
    output_template: str,
    progress_hook: Callable[[dict], None],
    postprocessor_hook: Callable[[dict], None],
) -> dict[str, Any]:
    opts = _base_opts(settings)
    opts.update(
        {
            "noplaylist": request.playlist_mode == "single",
            "outtmpl": output_template,
            "format": build_format_selector(
                request.media_type,
                request.quality_key,
                request.format_id,
                request.format_has_video,
                request.format_has_audio,
                settings.container_mode,
            ),
            "progress_hooks": [progress_hook],
            "postprocessor_hooks": [postprocessor_hook],
            "windowsfilenames": True,
            "trim_file_name": 150,
            "writethumbnail": settings.save_thumbnail or (
                request.media_type == MediaType.AUDIO and settings.embed_thumbnail_in_audio
            ),
        }
    )

    postprocessors: list[dict[str, Any]] = []

    if request.media_type == MediaType.AUDIO:
        audio_format = request.audio_format or "best"
        if audio_format in ("mp3", "m4a"):
            audio_pp: dict[str, Any] = {"key": "FFmpegExtractAudio", "preferredcodec": audio_format}
            if audio_format == "mp3":
                audio_pp["preferredquality"] = str(request.mp3_bitrate or settings.mp3_bitrate)
            postprocessors.append(audio_pp)
        if settings.embed_thumbnail_in_audio:
            # already_have_thumbnail=False tells yt-dlp to delete the temp
            # thumbnail file after embedding it, unless the user separately
            # asked to keep thumbnails (save_thumbnail) — otherwise a stray
            # .jpg/.webp would be left behind next to every audio download.
            postprocessors.append(
                {"key": "EmbedThumbnail", "already_have_thumbnail": settings.save_thumbnail}
            )
    # No merge_output_format is set for video here: forcing yt-dlp to mux
    # into ".mp4" regardless of the actual codecs is exactly the "fake MP4"
    # bug this app avoids. yt-dlp merges into whatever container naturally
    # fits the downloaded codecs; download_manager then inspects the actual
    # result and, in Compatibility mode, runs a genuine FFmpeg remux/
    # transcode to MP4 afterward if needed (see needs_mp4_transcode).

    if settings.embed_metadata:
        postprocessors.append({"key": "FFmpegMetadata", "add_metadata": True})

    if request.clip is not None:
        start_s, end_s = validate_clip_range(request.clip.start, request.clip.end)
        opts["download_ranges"] = _make_download_ranges(start_s, end_s)
        opts["force_keyframes_at_cuts"] = True

    opts["postprocessors"] = postprocessors
    return opts


def _make_download_ranges(start_s: float, end_s: float):
    from yt_dlp.utils import download_range_func

    return download_range_func(None, [(start_s, end_s)])
