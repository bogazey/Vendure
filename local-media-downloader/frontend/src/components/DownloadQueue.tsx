import type { DownloadJobOut } from "../types/api";
import DownloadQueueItem from "./DownloadQueueItem";

interface DownloadQueueProps {
  jobs: DownloadJobOut[];
  onCancel: (id: string) => void;
}

export default function DownloadQueue({ jobs, onCancel }: DownloadQueueProps) {
  if (jobs.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-white/10 bg-white/[0.02] p-6 text-center text-sm text-slate-500 backdrop-blur-xl">
        No downloads yet. Paste a URL above to get started.
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
