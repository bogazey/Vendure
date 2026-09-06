import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { AnalyzeResponse, CreateDownloadRequest, MediaEntry } from "../types/api";
import { formatDuration } from "../utils/format";

interface CarouselPickerProps {
  media: AnalyzeResponse;
  onStartDownload: (request: CreateDownloadRequest) => void;
  submitting: boolean;
}

function requestForEntry(url: string, entry: MediaEntry): CreateDownloadRequest {
  return {
    url,
    media_type: entry.media_type,
    quality_key: "best",
    playlist_mode: "selected",
    playlist_item_indices: [entry.index],
  };
}

/**
 * A carousel post (e.g. Instagram) already returns every item fully
 * resolved in one analyze() call - see media_items on AnalyzeResponse -
 * unlike a URL-level playlist (PlaylistChooser), which only has lightweight
 * previews and analyzes one entry at a time. Each selected item becomes its
 * own download job (its own credit/history entry), reusing the existing
 * single-job pipeline rather than a new batch concept.
 */
export default function CarouselPicker({ media, onStartDownload, submitting }: CarouselPickerProps) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const toggle = (index: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  };

  const selectAll = () => setSelected(new Set(media.media_items.map((item) => item.index)));
  const deselectAll = () => setSelected(new Set());

  const downloadSelected = () => {
    for (const item of media.media_items) {
      if (selected.has(item.index)) onStartDownload(requestForEntry(media.url, item));
    }
  };

  const downloadAll = () => {
    for (const item of media.media_items) onStartDownload(requestForEntry(media.url, item));
  };

  return (
    <div className="glass-panel-raised flex flex-col gap-4 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-slate-400">
          {t("carousel.itemCount", { count: media.media_items.length })}
          {selected.size > 0 && ` · ${t("carousel.itemsSelected", { count: selected.size })}`}
        </p>
        <div className="flex gap-2">
          <button type="button" onClick={selectAll} className="btn-glass px-3 py-1.5 text-xs">
            {t("carousel.selectAll")}
          </button>
          <button type="button" onClick={deselectAll} className="btn-glass px-3 py-1.5 text-xs" disabled={selected.size === 0}>
            {t("carousel.deselectAll")}
          </button>
        </div>
      </div>

      <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {media.media_items.map((item) => (
          <li key={item.index}>
            <label
              className={`flex cursor-pointer flex-col gap-2 rounded-xl border p-2 transition-colors ${
                selected.has(item.index) ? "border-brand-aqua/50 bg-brand-aqua/10" : "border-white/10 hover:border-white/25"
              }`}
            >
              <div className="relative aspect-square w-full overflow-hidden rounded-lg bg-black/40">
                {(item.thumbnail || item.image_url) && (
                  <img src={item.thumbnail ?? item.image_url ?? undefined} alt="" className="h-full w-full object-cover" />
                )}
                <span className="absolute start-1.5 top-1.5 rounded-full bg-black/70 px-1.5 py-0.5 text-[10px] font-medium text-slate-100">
                  {item.media_type === "video" ? t("carousel.video") : t("carousel.image")}
                </span>
                {item.duration != null && (
                  <span className="absolute bottom-1.5 end-1.5 rounded-full bg-black/70 px-1.5 py-0.5 text-[10px] text-slate-100" dir="ltr">
                    {formatDuration(item.duration)}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1.5 px-0.5">
                <input
                  type="checkbox"
                  checked={selected.has(item.index)}
                  onChange={() => toggle(item.index)}
                  className="h-3.5 w-3.5 shrink-0"
                  aria-label={t("carousel.selectItem", { index: item.index })}
                />
                <span className="truncate text-xs text-slate-400">#{item.index}</span>
              </div>
            </label>
          </li>
        ))}
      </ul>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={downloadSelected}
          disabled={submitting || selected.size === 0}
          className="btn-gradient flex-1 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {t("carousel.downloadSelected")}
        </button>
        <button
          type="button"
          onClick={downloadAll}
          disabled={submitting || media.media_items.length === 0}
          className="btn-glass flex-1 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {t("carousel.downloadAll")}
        </button>
      </div>
    </div>
  );
}
