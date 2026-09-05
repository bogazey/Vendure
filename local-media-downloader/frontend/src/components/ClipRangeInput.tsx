import { useTranslation } from "react-i18next";

interface ClipRangeInputProps {
  enabled: boolean;
  start: string;
  end: string;
  onToggle: (enabled: boolean) => void;
  onStartChange: (value: string) => void;
  onEndChange: (value: string) => void;
  error?: string | null;
}

export default function ClipRangeInput({
  enabled,
  start,
  end,
  onToggle,
  onStartChange,
  onEndChange,
  error,
}: ClipRangeInputProps) {
  const { t } = useTranslation();
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-3 backdrop-blur-xl">
      <label className="flex items-center gap-2 text-sm font-medium text-slate-300">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => onToggle(e.target.checked)}
          className="h-4 w-4 rounded border-white/20 bg-transparent accent-brand-aqua"
        />
        {t("format.clip")}
      </label>

      {enabled && (
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500">{t("format.start")}</span>
            <input
              type="text"
              value={start}
              onChange={(e) => onStartChange(e.target.value)}
              placeholder="00:00"
              className="input-glass w-24 px-2 py-1.5"
            />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500">{t("format.end")}</span>
            <input
              type="text"
              value={end}
              onChange={(e) => onEndChange(e.target.value)}
              placeholder="00:30"
              className="input-glass w-24 px-2 py-1.5"
            />
          </div>
          <span className="text-xs text-slate-500">{t("format.timeFormat")}</span>
        </div>
      )}
      {enabled && error && <p className="mt-2 text-xs text-red-400">{error}</p>}
    </div>
  );
}
