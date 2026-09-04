export type Platform = "youtube" | "tiktok" | "instagram" | "facebook" | "unknown";
export type MediaType = "video" | "audio" | "playlist";
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
export type ContainerPref = "auto" | "mp4" | "mkv";
export type Theme = "system" | "light" | "dark";
export type CookieSource = "none" | "chrome" | "firefox" | "edge" | "safari" | "file";
export type PlaylistMode = "single" | "full" | "selected";

export interface FormatOption {
  format_id: string;
  kind: FormatKind;
  ext: string;
  resolution: string | null;
  height: number | null;
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
}

export interface PlaylistEntryPreview {
  id: string;
  title: string;
  duration: number | null;
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
  is_playlist: boolean;
  playlist_title: string | null;
  playlist_count: number | null;
  playlist_entries_preview: PlaylistEntryPreview[];
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
  preferred_container: ContainerPref;
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
}

export interface ValidateFolderResponse {
  valid: boolean;
  reason?: string | null;
  resolved_path?: string | null;
}
