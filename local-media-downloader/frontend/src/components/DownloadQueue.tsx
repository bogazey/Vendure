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
        <span className="mb-3 inline-block h-2 w-2 rounded-full bg-brand-aqua/70 shadow-[0_0_14px_rgba(34,211,238,.5)]" />
        <p>No downloads yet. Paste a URL above to get started.</p>
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
