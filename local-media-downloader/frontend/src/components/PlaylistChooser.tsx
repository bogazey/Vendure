import type { AnalyzeResponse, PlaylistMode } from "../types/api";
import { useTranslation } from "react-i18next";

interface PlaylistChooserProps {
  media: AnalyzeResponse;
  mode: PlaylistMode;
  onChange: (mode: PlaylistMode) => void;
}

export default function PlaylistChooser({ media, mode, onChange }: PlaylistChooserProps) {
  const { t } = useTranslation();
  return (
    <div className="rounded-2xl border border-amber-500/20 bg-amber-500/[0.06] p-4 backdrop-blur-xl">
      <p className="text-sm font-medium text-amber-200">
        {media.playlist_title || t("playlist.detected")}
        {media.playlist_count != null && (
          <span className="ml-2 text-xs font-normal text-amber-300/70">
            {t("playlist.videos", { count: media.playlist_count })}
          </span>
        )}
      </p>

      {media.playlist_entries_preview.length > 0 && (
        <ul className="mt-2 space-y-1 text-xs text-amber-100/70">
          {media.playlist_entries_preview.map((entry) => (
            <li key={entry.id} className="truncate">
              • {entry.title}
            </li>
          ))}
          {media.playlist_count != null && media.playlist_count > media.playlist_entries_preview.length && (
            <li className="text-amber-300/50">
              {t("playlist.more", { count: media.playlist_count - media.playlist_entries_preview.length })}
            </li>
          )}
        </ul>
      )}

      <div className="mt-3 flex gap-2">
        <button
          type="button"
          onClick={() => onChange("single")}
          className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
            mode === "single" ? "bg-amber-500 text-black" : "bg-black/20 text-amber-200 hover:bg-black/30"
          }`}
        >
          {t("playlist.single")}
        </button>
        <button
          type="button"
          onClick={() => onChange("full")}
          className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
            mode === "full" ? "bg-amber-500 text-black" : "bg-black/20 text-amber-200 hover:bg-black/30"
          }`}
        >
          {t("playlist.full")}
        </button>
      </div>
    </div>
  );
}
