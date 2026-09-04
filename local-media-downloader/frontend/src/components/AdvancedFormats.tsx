import { useState } from "react";
import type { FormatOption } from "../types/api";
import { formatBytes } from "../utils/format";

interface AdvancedFormatsProps {
  formats: FormatOption[];
  selectedFormatId: string | null;
  onSelect: (format: FormatOption | null) => void;
}

export default function AdvancedFormats({ formats, selectedFormatId, onSelect }: AdvancedFormatsProps) {
  const [open, setOpen] = useState(false);

  if (formats.length === 0) return null;

  return (
    <div className="rounded-lg border border-surface-border">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium text-slate-300"
      >
        Advanced Formats ({formats.length} streams)
        <span className="text-slate-500">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="max-h-72 overflow-auto border-t border-surface-border">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-surface-raised text-slate-500">
              <tr>
                <th className="px-3 py-2 font-medium">Use</th>
                <th className="px-3 py-2 font-medium">Type</th>
                <th className="px-3 py-2 font-medium">Res</th>
                <th className="px-3 py-2 font-medium">FPS</th>
                <th className="px-3 py-2 font-medium">Codec</th>
                <th className="px-3 py-2 font-medium">Ext</th>
                <th className="px-3 py-2 font-medium">Bitrate</th>
                <th className="px-3 py-2 font-medium">Size</th>
              </tr>
            </thead>
            <tbody>
              {formats.map((f) => (
                <tr
                  key={f.format_id}
                  className={`cursor-pointer border-t border-surface-border/60 hover:bg-surface-border/30 ${
                    selectedFormatId === f.format_id ? "bg-indigo-500/10" : ""
                  }`}
                  onClick={() => onSelect(selectedFormatId === f.format_id ? null : f)}
                >
                  <td className="px-3 py-2">
                    <input
                      type="radio"
                      checked={selectedFormatId === f.format_id}
                      onChange={() => onSelect(f)}
                      className="accent-indigo-500"
                    />
                  </td>
                  <td className="px-3 py-2 text-slate-300">
                    {f.has_video ? "Video" : "Audio"}
                    {f.has_audio && f.has_video ? " + audio" : ""}
                  </td>
                  <td className="px-3 py-2 text-slate-400">{f.resolution || "—"}</td>
                  <td className="px-3 py-2 text-slate-400">{f.fps ?? "—"}</td>
                  <td className="px-3 py-2 text-slate-400">{f.vcodec || f.acodec || "—"}</td>
                  <td className="px-3 py-2 text-slate-400">{f.ext}</td>
                  <td className="px-3 py-2 text-slate-400">
                    {f.vbr ? `${Math.round(f.vbr)}k` : f.abr ? `${Math.round(f.abr)}k` : "—"}
                  </td>
                  <td className="px-3 py-2 text-slate-400">{formatBytes(f.filesize ?? f.filesize_approx)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
