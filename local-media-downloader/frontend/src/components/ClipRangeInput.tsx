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
  return (
    <div className="rounded-lg border border-surface-border p-3">
      <label className="flex items-center gap-2 text-sm font-medium text-slate-300">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => onToggle(e.target.checked)}
          className="h-4 w-4 rounded border-surface-border bg-surface accent-indigo-500"
        />
        Download only part of this video (clip range)
      </label>

      {enabled && (
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500">Start</span>
            <input
              type="text"
              value={start}
              onChange={(e) => onStartChange(e.target.value)}
              placeholder="00:00"
              className="w-24 rounded-md border border-surface-border bg-surface px-2 py-1.5 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
            />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500">End</span>
            <input
              type="text"
              value={end}
              onChange={(e) => onEndChange(e.target.value)}
              placeholder="00:30"
              className="w-24 rounded-md border border-surface-border bg-surface px-2 py-1.5 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
            />
          </div>
          <span className="text-xs text-slate-500">Format: HH:MM:SS or MM:SS</span>
        </div>
      )}
      {enabled && error && <p className="mt-2 text-xs text-red-400">{error}</p>}
    </div>
  );
}
