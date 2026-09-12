"""Pydantic request/response schemas for the API."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.models.enums import (
    ContainerMode,
    CookieSource,
    DownloadStage,
    FormatKind,
    MediaType,
    Platform,
    Theme,
)


# ---------- Analyze ----------

class AnalyzeRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)

    @field_validator("url")
    @classmethod
    def strip_url(cls, v: str) -> str:
        return v.strip()


class FormatOption(BaseModel):
    format_id: str
    kind: FormatKind
    ext: str
    resolution: Optional[str] = None
    height: Optional[int] = None
    # Absent for older/mocked FormatOption instances (e.g. existing tests) -
    # every consumer must keep working with width=None, falling back to
    # height alone (see ytdlp_service._effective_quality_dimension).
    width: Optional[int] = None
    fps: Optional[float] = None
    vcodec: Optional[str] = None
    acodec: Optional[str] = None
    abr: Optional[float] = None
    vbr: Optional[float] = None
    filesize: Optional[int] = None
    filesize_approx: Optional[int] = None
    has_video: bool = False
    has_audio: bool = False
    note: Optional[str] = None


class QualityPreset(BaseModel):
    key: str
    label: str
    kind: FormatKind
    available: bool
    height: Optional[int] = None
    # Best-effort prediction shown in the UI before downloading. For video
    # presets in Compatibility mode this is always "mp4" (guaranteed by
    # post-download conversion if needed); will_transcode flags whether that
    # conversion is actually expected to run for this particular preset.
    expected_container: Optional[str] = None
    will_transcode: Optional[bool] = None


class PlaylistEntryPreview(BaseModel):
    id: str
    title: str
    duration: Optional[float] = None


class MediaEntryOut(BaseModel):
    """One item of a multi-media post (e.g. an Instagram carousel). `index`
    is 1-based and matches yt-dlp's own `playlist_items` convention, so it
    can be passed straight back in CreateDownloadRequest.playlist_item_indices
    to download just this one entry."""

    index: int
    media_type: MediaType
    title: Optional[str] = None
    thumbnail: Optional[str] = None
    duration: Optional[float] = None
    image_url: Optional[str] = None
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    image_ext: Optional[str] = None


class AnalyzeResponse(BaseModel):
    url: str
    platform: Platform
    media_type: MediaType
    id: str
    title: str
    uploader: Optional[str] = None
    thumbnail: Optional[str] = None
    duration: Optional[float] = None
    description: Optional[str] = None
    # Populated when media_type == IMAGE: the best available full-resolution
    # image (distinct from `thumbnail`, which some platforms treat as a
    # separate, smaller preview - see ytdlp_service._pick_best_image).
    image_url: Optional[str] = None
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    image_ext: Optional[str] = None
    is_playlist: bool = False
    playlist_title: Optional[str] = None
    playlist_count: Optional[int] = None
    playlist_entries_preview: list[PlaylistEntryPreview] = Field(default_factory=list)
    # A single post that itself contains multiple full media items (e.g. an
    # Instagram carousel) - distinct from playlist_entries_preview, which is
    # a lightweight preview of a much larger URL-level playlist (list=...)
    # the user would analyze one entry of at a time.
    media_items: list[MediaEntryOut] = Field(default_factory=list)
    video_presets: list[QualityPreset] = Field(default_factory=list)
    audio_presets: list[QualityPreset] = Field(default_factory=list)
    advanced_formats: list[FormatOption] = Field(default_factory=list)


# ---------- Downloads ----------

class ClipRange(BaseModel):
    start: str
    end: str

    @field_validator("start", "end")
    @classmethod
    def validate_timecode(cls, v: str) -> str:
        from app.utils.timecode import parse_timecode

        parse_timecode(v)  # raises ValueError if invalid
        return v


class CreateDownloadRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    media_type: MediaType = MediaType.VIDEO
    quality_key: str = "best"
    format_id: Optional[str] = None
    # Whether the chosen advanced format_id already carries video/audio, so the
    # backend can build a correct format selector (see build_format_selector).
    format_has_video: Optional[bool] = None
    format_has_audio: Optional[bool] = None
    audio_format: Optional[str] = None  # "mp3" | "m4a" | "best"
    mp3_bitrate: Optional[int] = Field(default=None, ge=32, le=320)
    playlist_mode: Literal["single", "full", "selected"] = "single"
    playlist_item_indices: Optional[list[int]] = None
    clip: Optional[ClipRange] = None

    @field_validator("url")
    @classmethod
    def strip_url(cls, v: str) -> str:
        return v.strip()


class DownloadJobOut(BaseModel):
    id: str
    url: str
    platform: Platform
    title: Optional[str]
    uploader: Optional[str]
    thumbnail: Optional[str]
    media_type: MediaType
    stage: DownloadStage
    progress_percent: float = 0.0
    speed_bps: Optional[float] = None
    downloaded_bytes: Optional[int] = None
    total_bytes: Optional[int] = None
    eta_seconds: Optional[int] = None
    filepath: Optional[str] = None
    error_message: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None


# ---------- History ----------

class HistoryRecordOut(BaseModel):
    id: str
    url: str
    platform: Platform
    title: Optional[str]
    uploader: Optional[str]
    thumbnail: Optional[str]
    format_label: Optional[str]
    resolution: Optional[str]
    filepath: Optional[str]
    filesize: Optional[int]
    created_at: str
    completed_at: Optional[str]
    status: DownloadStage
    error_message: Optional[str]


class ClearHistoryRequest(BaseModel):
    delete_files: bool = False


# ---------- Settings ----------

class AppSettings(BaseModel):
    download_dir: str
    max_concurrent_downloads: int = Field(default=2, ge=1, le=10)
    theme: Theme = Theme.SYSTEM

    default_video_quality: str = "best"
    container_mode: ContainerMode = ContainerMode.COMPATIBILITY
    embed_metadata: bool = True
    save_thumbnail: bool = False

    preferred_audio_format: str = "mp3"
    mp3_bitrate: int = Field(default=192, ge=32, le=320)
    embed_thumbnail_in_audio: bool = True

    cookie_source: CookieSource = CookieSource.NONE
    cookie_file_path: Optional[str] = None

    network_timeout_seconds: int = Field(default=30, ge=5, le=300)
    retries: int = Field(default=3, ge=0, le=20)


class UpdateSettingsRequest(BaseModel):
    download_dir: Optional[str] = None
    max_concurrent_downloads: Optional[int] = Field(default=None, ge=1, le=10)
    theme: Optional[Theme] = None

    default_video_quality: Optional[str] = None
    container_mode: Optional[ContainerMode] = None
    embed_metadata: Optional[bool] = None
    save_thumbnail: Optional[bool] = None

    preferred_audio_format: Optional[str] = None
    mp3_bitrate: Optional[int] = Field(default=None, ge=32, le=320)
    embed_thumbnail_in_audio: Optional[bool] = None

    cookie_source: Optional[CookieSource] = None
    cookie_file_path: Optional[str] = None

    network_timeout_seconds: Optional[int] = Field(default=None, ge=5, le=300)
    retries: Optional[int] = Field(default=None, ge=0, le=20)


# ---------- Health ----------

class HealthResponse(BaseModel):
    status: str
    ytdlp_version: Optional[str]
    ffmpeg_available: bool
    ffmpeg_path: Optional[str]
    download_dir: str
    download_dir_writable: bool
    database_ok: bool


# ---------- Filesystem ----------

class OpenPathRequest(BaseModel):
    path: str


class ValidateFolderRequest(BaseModel):
    path: str


class ValidateFolderResponse(BaseModel):
    valid: bool
    reason: Optional[str] = None
    resolved_path: Optional[str] = None
