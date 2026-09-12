export type Platform = "youtube" | "tiktok" | "instagram" | "facebook" | "unknown";
export type MediaType = "video" | "audio" | "image";
export type DownloadStage =
  | "queued"
  | "analyzing"
  | "downloading"
  | "merging"
  | "converting"
  | "completed"
  | "cancelled"
  | "failed";
export type FormatKind = "video" | "audio";
/** Compatibility: video downloads always end in a genuine, playable MP4
 * (H.264/AAC), transcoding via FFmpeg when needed. Original: keeps whatever
 * container/codec the best source streams naturally use (may be WebM/MKV). */
export type ContainerMode = "compatibility" | "original";
export type Theme = "system" | "light" | "dark";
export type CookieSource = "none" | "chrome" | "firefox" | "edge" | "safari" | "file";
export type PlaylistMode = "single" | "full" | "selected";

export interface FormatOption {
  format_id: string;
  kind: FormatKind;
  ext: string;
  resolution: string | null;
  height: number | null;
  width: number | null;
  fps: number | null;
  vcodec: string | null;
  acodec: string | null;
  abr: number | null;
  vbr: number | null;
  filesize: number | null;
  filesize_approx: number | null;
  has_video: boolean;
  has_audio: boolean;
  note: string | null;
}

export interface QualityPreset {
  key: string;
  label: string;
  kind: FormatKind;
  available: boolean;
  height: number | null;
  /** Best-effort prediction shown before downloading; the actual, final
   * container is always recorded in history after the download completes. */
  expected_container: string | null;
  will_transcode: boolean | null;
}

export interface PlaylistEntryPreview {
  id: string;
  title: string;
  duration: number | null;
}

/** One item of a multi-media post (e.g. an Instagram carousel). `index` is
 * 1-based and matches yt-dlp's own playlist_items convention - pass it back
 * in CreateDownloadRequest.playlist_item_indices to download just this one
 * entry. */
export interface MediaEntry {
  index: number;
  media_type: MediaType;
  title: string | null;
  thumbnail: string | null;
  duration: number | null;
  image_url: string | null;
  image_width: number | null;
  image_height: number | null;
  image_ext: string | null;
}

export interface AnalyzeResponse {
  url: string;
  platform: Platform;
  media_type: MediaType;
  id: string;
  title: string;
  uploader: string | null;
  thumbnail: string | null;
  duration: number | null;
  description: string | null;
  // Populated when media_type === "image": the best available
  // full-resolution image, distinct from `thumbnail`.
  image_url: string | null;
  image_width: number | null;
  image_height: number | null;
  image_ext: string | null;
  is_playlist: boolean;
  playlist_title: string | null;
  playlist_count: number | null;
  playlist_entries_preview: PlaylistEntryPreview[];
  // A single post that itself contains multiple full media items (e.g. an
  // Instagram carousel) - distinct from playlist_entries_preview, which is
  // a lightweight preview of a much larger URL-level playlist.
  media_items: MediaEntry[];
  video_presets: QualityPreset[];
  audio_presets: QualityPreset[];
  advanced_formats: FormatOption[];
}

export interface ClipRange {
  start: string;
  end: string;
}

export interface CreateDownloadRequest {
  url: string;
  media_type: MediaType;
  quality_key: string;
  format_id?: string | null;
  format_has_video?: boolean | null;
  format_has_audio?: boolean | null;
  audio_format?: string | null;
  mp3_bitrate?: number | null;
  playlist_mode: PlaylistMode;
  playlist_item_indices?: number[] | null;
  clip?: ClipRange | null;
}

export interface DownloadJobOut {
  id: string;
  url: string;
  platform: Platform;
  title: string | null;
  uploader: string | null;
  thumbnail: string | null;
  media_type: MediaType;
  stage: DownloadStage;
  progress_percent: number;
  speed_bps: number | null;
  downloaded_bytes: number | null;
  total_bytes: number | null;
  eta_seconds: number | null;
  filepath: string | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

/** Anonymous guest download allowance - see guest_service.py. Never a
 * fake AccountOut; guests have no user/subscription/credits at all. */
export interface GuestQuotaOut {
  remaining: number;
  limit: number;
}

export interface HistoryRecordOut {
  id: string;
  url: string;
  platform: Platform;
  title: string | null;
  uploader: string | null;
  thumbnail: string | null;
  format_label: string | null;
  resolution: string | null;
  filepath: string | null;
  filesize: number | null;
  created_at: string;
  completed_at: string | null;
  status: DownloadStage;
  error_message: string | null;
}

export interface AppSettings {
  download_dir: string;
  max_concurrent_downloads: number;
  theme: Theme;

  default_video_quality: string;
  container_mode: ContainerMode;
  embed_metadata: boolean;
  save_thumbnail: boolean;

  preferred_audio_format: string;
  mp3_bitrate: number;
  embed_thumbnail_in_audio: boolean;

  cookie_source: CookieSource;
  cookie_file_path: string | null;

  network_timeout_seconds: number;
  retries: number;
}

export type UpdateSettingsRequest = Partial<AppSettings>;

export interface HealthResponse {
  status: string;
  ytdlp_version: string | null;
  ffmpeg_available: boolean;
  ffmpeg_path: string | null;
  download_dir: string;
  download_dir_writable: boolean;
  database_ok: boolean;
}

export interface ApiErrorPayload {
  message: string;
  technical?: string | null;
  code?: string | null;
}

export interface ValidateFolderResponse {
  valid: boolean;
  reason?: string | null;
  resolved_path?: string | null;
}
