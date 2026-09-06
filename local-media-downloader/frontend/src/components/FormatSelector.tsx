import { useMemo, useState } from "react";
import type { AnalyzeResponse, CreateDownloadRequest, FormatOption, MediaType, PlaylistMode } from "../types/api";
import AdvancedFormats from "./AdvancedFormats";
import CarouselPicker from "./CarouselPicker";
import ClipRangeInput from "./ClipRangeInput";
import PlaylistChooser from "./PlaylistChooser";
import { parseTimecode } from "../utils/timecode";
import { useTranslation } from "react-i18next";

interface FormatSelectorProps {
  media: AnalyzeResponse;
  onStartDownload: (request: CreateDownloadRequest) => void;
  submitting: boolean;
}

const MP3_BITRATES = [128, 192, 256, 320];

export default function FormatSelector({ media, onStartDownload, submitting }: FormatSelectorProps) {
  const { t } = useTranslation();
  const [mediaType, setMediaType] = useState<MediaType>("video");
  const [videoQuality, setVideoQuality] = useState("best");
  const [audioFormat, setAudioFormat] = useState<"best" | "mp3" | "m4a">("best");
  const [mp3Bitrate, setMp3Bitrate] = useState(192);
  const [selectedFormat, setSelectedFormat] = useState<FormatOption | null>(null);
  const [playlistMode, setPlaylistMode] = useState<PlaylistMode>("single");
  const [clipEnabled, setClipEnabled] = useState(false);
  const [clipStart, setClipStart] = useState("00:00");
  const [clipEnd, setClipEnd] = useState("00:30");

  const clipError = useMemo(() => {
    if (!clipEnabled) return null;
    try {
      const startS = parseTimecode(clipStart);
      const endS = parseTimecode(clipEnd);
      if (endS <= startS) return t("format.endAfterStart");
      return null;
    } catch {
      return t("format.invalidTime");
    }
  }, [clipEnabled, clipStart, clipEnd, t]);

  const canSubmit = !submitting && !clipError;

  const selectedVideoPreset = useMemo(
    () => (selectedFormat ? null : media.video_presets.find((p) => p.key === videoQuality) ?? null),
    [media.video_presets, videoQuality, selectedFormat],
  );

  const handleSubmit = () => {
    if (!canSubmit) return;
    const request: CreateDownloadRequest = {
      url: media.url,
      media_type: mediaType,
      quality_key: mediaType === "video" ? videoQuality : audioFormat,
      format_id: selectedFormat?.format_id ?? null,
      format_has_video: selectedFormat?.has_video ?? null,
      format_has_audio: selectedFormat?.has_audio ?? null,
      audio_format: mediaType === "audio" ? audioFormat : null,
      mp3_bitrate: mediaType === "audio" && audioFormat === "mp3" ? mp3Bitrate : null,
      playlist_mode: media.is_playlist ? playlistMode : "single",
      clip: clipEnabled && !clipError ? { start: clipStart, end: clipEnd } : null,
    };
    onStartDownload(request);
  };

  const handleImageDownload = () => {
    if (submitting) return;
    onStartDownload({
      url: media.url,
      media_type: "image",
      quality_key: "best",
      playlist_mode: "single",
    });
  };

  if (media.media_items.length > 0) {
    return <CarouselPicker media={media} onStartDownload={onStartDownload} submitting={submitting} />;
  }

  if (media.media_type === "image") {
    return (
      <div className="glass-panel-raised flex flex-col gap-3 p-4">
        <button
          type="button"
          onClick={handleImageDownload}
          disabled={submitting}
          className="btn-gradient w-full disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? t("format.starting") : t("format.downloadImage")}
        </button>
      </div>
    );
  }

  return (
    <div className="glass-panel-raised flex flex-col gap-4 p-4">
      {media.is_playlist && (
        <PlaylistChooser media={media} mode={playlistMode} onChange={setPlaylistMode} />
      )}

      <div className="flex gap-2 rounded-xl bg-white/[0.03] p-1">
        <button
          type="button"
          onClick={() => setMediaType("video")}
          className={`flex-1 rounded-lg px-4 py-2 text-sm font-semibold transition-colors ${
            mediaType === "video" ? "bg-brand-gradient text-white shadow-glow" : "text-slate-400 hover:text-slate-200"
          }`}
        >
          {t("format.video")}
        </button>
        <button
          type="button"
          onClick={() => setMediaType("audio")}
          className={`flex-1 rounded-lg px-4 py-2 text-sm font-semibold transition-colors ${
            mediaType === "audio" ? "bg-brand-gradient text-white shadow-glow" : "text-slate-400 hover:text-slate-200"
          }`}
        >
          {t("format.audioOnly")}
        </button>
      </div>

      {mediaType === "video" ? (
        <div className="flex flex-col gap-2">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {media.video_presets.map((preset) => (
              <button
                key={preset.key}
                type="button"
                disabled={!preset.available}
                onClick={() => setVideoQuality(preset.key)}
                className={`rounded-lg border px-3 py-2 text-sm font-medium transition-colors ${
                  videoQuality === preset.key
                    ? "border-brand-aqua/50 bg-brand-aqua/10 text-brand-aqua"
                    : "border-white/10 text-slate-300 hover:border-white/25"
                } ${!preset.available ? "cursor-not-allowed opacity-30" : ""}`}
              >
                <div>{preset.label}</div>
                {preset.expected_container && (
                  <div className="mt-0.5 text-[10px] font-normal uppercase tracking-wide text-slate-500">
                    {preset.expected_container}
                    {preset.will_transcode ? " · converts" : ""}
                  </div>
                )}
              </button>
            ))}
          </div>
          {selectedVideoPreset?.expected_container && (
            <p className="text-xs text-slate-500">
              Output: <span className="font-medium text-slate-300">{selectedVideoPreset.expected_container.toUpperCase()}</span>
              {selectedVideoPreset.will_transcode && " (source will be converted with FFmpeg to preserve compatibility)"}
            </p>
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <div className="grid grid-cols-3 gap-2">
            {media.audio_presets.map((preset) => (
              <button
                key={preset.key}
                type="button"
                disabled={!preset.available}
                onClick={() => setAudioFormat(preset.key as "best" | "mp3" | "m4a")}
                className={`rounded-lg border px-3 py-2 text-sm font-medium transition-colors ${
                  audioFormat === preset.key
                    ? "border-brand-aqua/50 bg-brand-aqua/10 text-brand-aqua"
                    : "border-white/10 text-slate-300 hover:border-white/25"
                } ${!preset.available ? "cursor-not-allowed opacity-30" : ""}`}
              >
                {preset.label}
              </button>
            ))}
          </div>

          {audioFormat === "mp3" && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-500">{t("format.bitrate")}</span>
              {MP3_BITRATES.map((rate) => (
                <button
                  key={rate}
                  type="button"
                  onClick={() => setMp3Bitrate(rate)}
                  className={`rounded-md px-2.5 py-1 text-xs font-medium ${
                    mp3Bitrate === rate
                      ? "bg-brand-gradient text-white shadow-glow"
                      : "bg-white/[0.04] text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {rate} kbps
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {mediaType === "video" && (
        <ClipRangeInput
          enabled={clipEnabled}
          start={clipStart}
          end={clipEnd}
          onToggle={setClipEnabled}
          onStartChange={setClipStart}
          onEndChange={setClipEnd}
          error={clipError}
        />
      )}

      <AdvancedFormats
        formats={media.advanced_formats}
        selectedFormatId={selectedFormat?.format_id ?? null}
        onSelect={setSelectedFormat}
      />

      <button
        type="button"
        onClick={handleSubmit}
        disabled={!canSubmit}
        className="btn-gradient w-full disabled:cursor-not-allowed disabled:opacity-50"
      >
        {submitting ? t("format.starting") : t("format.startDownload")}
      </button>
    </div>
  );
}
