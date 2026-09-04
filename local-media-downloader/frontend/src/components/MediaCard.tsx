import type { AnalyzeResponse } from "../types/api";
import { formatDuration } from "../utils/format";
import { PLATFORM_COLORS, PLATFORM_ICONS, PLATFORM_LABELS } from "../utils/platform";

interface MediaCardProps {
  media: AnalyzeResponse;
}

export default function MediaCard({ media }: MediaCardProps) {
  return (
    <div className="flex flex-col gap-4 rounded-xl border border-surface-border bg-surface-raised p-4 sm:flex-row">
      <div className="aspect-video w-full shrink-0 overflow-hidden rounded-lg bg-black/40 sm:w-64">
        {media.thumbnail ? (
          <img src={media.thumbnail} alt={media.title} className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full items-center justify-center text-slate-600">No preview</div>
        )}
      </div>

      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${PLATFORM_COLORS[media.platform]}`}
          >
            <span>{PLATFORM_ICONS[media.platform]}</span>
            {PLATFORM_LABELS[media.platform]}
          </span>
          {media.duration != null && (
            <span className="text-xs text-slate-500">{formatDuration(media.duration)}</span>
          )}
          {media.is_playlist && (
            <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-300">
              Playlist detected
            </span>
          )}
        </div>

        <h2 className="truncate text-lg font-semibold text-slate-50" title={media.title}>
          {media.title}
        </h2>

        {media.uploader && <p className="text-sm text-slate-400">{media.uploader}</p>}

        {media.description && (
          <p className="line-clamp-2 text-sm text-slate-500">{media.description}</p>
        )}
      </div>
    </div>
  );
}
