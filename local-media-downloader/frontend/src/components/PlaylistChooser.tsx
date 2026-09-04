import type { AnalyzeResponse, PlaylistMode } from "../types/api";

interface PlaylistChooserProps {
  media: AnalyzeResponse;
  mode: PlaylistMode;
  onChange: (mode: PlaylistMode) => void;
}

export default function PlaylistChooser({ media, mode, onChange }: PlaylistChooserProps) {
  return (
    <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-4">
      <p className="text-sm font-medium text-amber-200">
        {media.playlist_title || "This URL is part of a playlist"}
        {media.playlist_count != null && (
          <span className="ml-2 text-xs font-normal text-amber-300/70">
            {media.playlist_count} videos detected
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
              …and {media.playlist_count - media.playlist_entries_preview.length} more
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
          Current video only
        </button>
        <button
          type="button"
          onClick={() => onChange("full")}
          className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
            mode === "full" ? "bg-amber-500 text-black" : "bg-black/20 text-amber-200 hover:bg-black/30"
          }`}
        >
          Entire playlist
        </button>
      </div>
    </div>
  );
}
