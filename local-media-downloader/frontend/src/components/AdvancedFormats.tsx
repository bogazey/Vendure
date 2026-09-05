import { useState } from "react";
import type { FormatOption } from "../types/api";
import { formatBytes } from "../utils/format";
import { useTranslation } from "react-i18next";

interface AdvancedFormatsProps {
  formats: FormatOption[];
  selectedFormatId: string | null;
  onSelect: (format: FormatOption | null) => void;
}

export default function AdvancedFormats({ formats, selectedFormatId, onSelect }: AdvancedFormatsProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  if (formats.length === 0) return null;

  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.02] backdrop-blur-xl">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium text-slate-300"
      >
        {t("format.advanced", { count: formats.length })}
        <span className="text-slate-500">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="max-h-72 overflow-auto border-t border-white/10">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-[#0b0e1a] text-slate-500">
              <tr>
                <th className="px-3 py-2 font-medium">{t("format.use")}</th>
                <th className="px-3 py-2 font-medium">{t("format.type")}</th>
                <th className="px-3 py-2 font-medium">{t("format.resolution")}</th>
                <th className="px-3 py-2 font-medium">FPS</th>
                <th className="px-3 py-2 font-medium">{t("format.codec")}</th>
                <th className="px-3 py-2 font-medium">{t("format.extension")}</th>
                <th className="px-3 py-2 font-medium">{t("format.bitrate")}</th>
                <th className="px-3 py-2 font-medium">{t("format.size")}</th>
              </tr>
            </thead>
            <tbody>
              {formats.map((f) => (
                <tr
                  key={f.format_id}
                  className={`cursor-pointer border-t border-white/[0.06] hover:bg-white/[0.03] ${
                    selectedFormatId === f.format_id ? "bg-brand-purple/10" : ""
                  }`}
                  onClick={() => onSelect(selectedFormatId === f.format_id ? null : f)}
                >
                  <td className="px-3 py-2">
                    <input
                      type="radio"
                      checked={selectedFormatId === f.format_id}
                      onChange={() => onSelect(f)}
                      className="accent-brand-aqua"
                    />
                  </td>
                  <td className="px-3 py-2 text-slate-300">
                    {f.has_video ? t("format.video") : t("format.audio")}
                    {f.has_audio && f.has_video ? t("format.withAudio") : ""}
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
