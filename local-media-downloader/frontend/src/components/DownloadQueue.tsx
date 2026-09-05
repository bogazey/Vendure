import type { DownloadJobOut } from "../types/api";
import DownloadQueueItem from "./DownloadQueueItem";

interface DownloadQueueProps {
  jobs: DownloadJobOut[];
  onCancel: (id: string) => void;
}

export default function DownloadQueue({ jobs, onCancel }: DownloadQueueProps) {
  if (jobs.length === 0) {
    return (
      <div className="download-empty rounded-2xl border border-dashed border-white/10 bg-white/[0.02] p-8 text-center text-sm text-slate-400 backdrop-blur-xl">
        <span className="mb-4 grid h-12 w-12 place-items-center rounded-2xl border border-white/10 bg-white/[0.035] shadow-[inset_0_1px_rgba(255,255,255,.07),0_12px_30px_rgba(0,0,0,.2)]">
          <img src="/assets/design/icons/features/save.svg" alt="" aria-hidden="true" className="h-8 w-8" />
        </span>
        <h3 className="font-display text-base font-semibold text-slate-100">Ready when you are</h3>
        <p className="mt-1.5 max-w-sm leading-6 text-slate-400">
          Downloads will appear here after you analyze a URL above.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {jobs.map((job) => (
        <DownloadQueueItem key={job.id} job={job} onCancel={onCancel} />
      ))}
    </div>
  );
}
