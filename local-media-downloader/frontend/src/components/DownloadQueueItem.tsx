import type { DownloadJobOut } from "../types/api";
import { formatBytes, formatEta, formatSpeed } from "../utils/format";
import { PLATFORM_COLORS, PLATFORM_ICONS, PLATFORM_LABELS } from "../utils/platform";
import { useTranslation } from "react-i18next";
import { downloadFileUrl } from "../services/api";

interface DownloadQueueItemProps {
  job: DownloadJobOut;
  onCancel: (id: string) => void;
}

const ACTIVE_STAGES = new Set(["queued", "analyzing", "downloading", "merging", "converting"]);

export default function DownloadQueueItem({ job, onCancel }: DownloadQueueItemProps) {
  const { t } = useTranslation();
  const active = ACTIVE_STAGES.has(job.stage);
  const barColor =
    job.stage === "failed" ? "bg-red-500" : job.stage === "cancelled" ? "bg-slate-500" : "bg-brand-gradient";

  return (
    <div className="glass-panel flex gap-3 p-3">
      <div className="h-14 w-24 shrink-0 overflow-hidden rounded-md bg-black/40">
        {job.thumbnail ? (
          <img src={job.thumbnail} alt="" className="h-full w-full object-cover" />
        ) : (
          <div className={`flex h-full w-full items-center justify-center text-xs ${PLATFORM_COLORS[job.platform]}`}>
            {PLATFORM_ICONS[job.platform]}
          </div>
        )}
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <p className="truncate text-sm font-medium text-slate-100" title={job.title ?? job.url}>
            {job.title || job.url}
          </p>
          {active && (
            <button
              type="button"
              onClick={() => onCancel(job.id)}
              className="shrink-0 rounded-md border border-white/10 px-2 py-0.5 text-xs text-slate-400 hover:border-red-500/50 hover:text-red-300"
            >
              {t("common.cancel")}
            </button>
          )}
        </div>

        <div className="mt-1 flex items-center gap-2 text-xs text-slate-500">
          <span className={`rounded px-1.5 py-0.5 ${PLATFORM_COLORS[job.platform]}`}>
            {PLATFORM_LABELS[job.platform]}
          </span>
          <span>{t(`status.${job.stage}`, { defaultValue: job.stage })}</span>
        </div>

        <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-white/[0.06]">
          <div
            className={`h-full rounded-full transition-all ${barColor}`}
            style={{ width: `${job.stage === "failed" || job.stage === "cancelled" ? 100 : job.progress_percent}%` }}
          />
        </div>

        {active && (
          <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-slate-500">
            <span>{job.progress_percent.toFixed(0)}%</span>
            <span>{formatSpeed(job.speed_bps)}</span>
            <span>
              {formatBytes(job.downloaded_bytes)} / {formatBytes(job.total_bytes)}
            </span>
            <span>ETA {formatEta(job.eta_seconds)}</span>
          </div>
        )}

        {job.stage === "failed" && job.error_message && (
          <p className="mt-1 text-[11px] text-red-400">{job.error_message}</p>
        )}
        {job.stage === "completed" && job.filepath && (
          <a href={downloadFileUrl(job.id)} className="mt-2 inline-flex rounded-full border border-brand-aqua/40 px-2.5 py-1 text-xs text-brand-aqua hover:border-brand-aqua/70">
            {t("app.openFile")}
          </a>
        )}
      </div>
    </div>
  );
}
