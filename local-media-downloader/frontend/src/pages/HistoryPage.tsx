import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import AdSlot from "../components/AdSlot";
import ErrorBanner from "../components/ErrorBanner";
import { ApiError, api } from "../services/api";
import { appPageShell } from "../styles/ui";
import type { HistoryRecordOut, Platform } from "../types/api";
import { formatBytes, formatDate } from "../utils/format";
import { PLATFORM_LABELS } from "../utils/platform";

const PLATFORM_OPTIONS: Platform[] = ["youtube", "tiktok", "instagram", "facebook"];
const STATUS_OPTIONS = ["completed", "failed", "cancelled", "downloading", "queued"];

export default function HistoryPage() {
  const [records, setRecords] = useState<HistoryRecordOut[]>([]);
  const [search, setSearch] = useState("");
  const [platform, setPlatform] = useState<string>("");
  const [status, setStatus] = useState<string>("");
  const [order, setOrder] = useState<"newest" | "oldest">("newest");
  const [error, setError] = useState<string | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);

  const load = async () => {
    try {
      const result = await api.listHistory({ search: search || undefined, platform: platform || undefined, status: status || undefined, order });
      setRecords(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load download history.");
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, platform, status, order]);

  const handleDelete = async (id: string, deleteFile: boolean) => {
    try {
      await api.deleteHistoryRecord(id, deleteFile);
      setRecords((prev) => prev.filter((r) => r.id !== id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not remove this record.");
    }
  };

  const handleClear = async (deleteFiles: boolean) => {
    try {
      await api.clearHistory(deleteFiles);
      setRecords([]);
      setConfirmClear(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not clear history.");
    }
  };

  const handleRetry = async (id: string) => {
    try {
      await api.retryDownload(id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not retry this download.");
    }
  };

  const filtersActive = !!(search || platform || status);

  const clearFilters = () => {
    setSearch("");
    setPlatform("");
    setStatus("");
  };

  return (
    <div className={appPageShell}>
      <div className="flex items-center justify-between">
        <h1 className="font-display text-xl font-bold text-slate-50">Download History</h1>
        <button
          type="button"
          onClick={() => setConfirmClear(true)}
          className="rounded-full border border-white/10 px-3 py-1.5 text-sm text-slate-400 transition-colors hover:border-red-500/40 hover:text-red-300"
        >
          Clear History
        </button>
      </div>

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      <AdSlot placement="history-page" />

      {confirmClear && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200 backdrop-blur-xl">
          <span>Clear all history records? Files on disk are kept unless you choose to delete them too.</span>
          <div className="flex gap-2">
            <button onClick={() => handleClear(false)} className="rounded-full bg-amber-500 px-3 py-1 text-black">
              Clear records only
            </button>
            <button onClick={() => handleClear(true)} className="rounded-full bg-red-600 px-3 py-1 text-white">
              Clear + delete files
            </button>
            <button onClick={() => setConfirmClear(false)} className="rounded-full px-3 py-1 text-amber-200/70">
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="glass-panel flex flex-wrap gap-3 p-3">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search title, uploader, or URL"
          className="input-glass min-w-[220px] flex-1 py-2"
        />
        <select
          value={platform}
          onChange={(e) => setPlatform(e.target.value)}
          className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-slate-200 backdrop-blur-xl focus:border-brand-purple/60 focus:outline-none"
        >
          <option value="">All platforms</option>
          {PLATFORM_OPTIONS.map((p) => (
            <option key={p} value={p}>
              {PLATFORM_LABELS[p]}
            </option>
          ))}
        </select>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-slate-200 backdrop-blur-xl focus:border-brand-purple/60 focus:outline-none"
        >
          <option value="">All statuses</option>
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select
          value={order}
          onChange={(e) => setOrder(e.target.value as "newest" | "oldest")}
          className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-slate-200 backdrop-blur-xl focus:border-brand-purple/60 focus:outline-none"
        >
          <option value="newest">Newest first</option>
          <option value="oldest">Oldest first</option>
        </select>
      </div>

      <div className="flex flex-col gap-2">
        {records.length === 0 &&
          (filtersActive ? (
            <FilteredEmptyState onClearFilters={clearFilters} />
          ) : (
            <NoDownloadsEmptyState />
          ))}
        {records.map((record) => (
          <HistoryRow key={record.id} record={record} onDelete={handleDelete} onRetry={handleRetry} />
        ))}
      </div>
    </div>
  );
}

function NoDownloadsEmptyState() {
  return (
    <div className="flex flex-col items-center gap-4 rounded-2xl border border-white/[0.08] bg-white/[0.015] px-8 py-14 text-center">
      <span className="flex h-14 w-14 items-center justify-center rounded-2xl border border-brand-blue/25 bg-brand-blue/10 text-brand-blue">
        <svg viewBox="0 0 24 24" width={26} height={26} fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 4v11" />
          <path d="m7 11 5 5 5-5" />
          <path d="M5 19h14" />
        </svg>
      </span>
      <div className="flex flex-col gap-1.5">
        <h3 className="font-display text-base font-semibold text-slate-100">Nothing here yet</h3>
        <p className="max-w-xs text-sm text-slate-400">
          Everything you save from YouTube, TikTok, Instagram, or Facebook will show up here.
        </p>
      </div>
      <Link to="/dashboard" className="btn-gradient !px-4 !py-2 text-sm">
        Download something
      </Link>
    </div>
  );
}

function FilteredEmptyState({ onClearFilters }: { onClearFilters: () => void }) {
  return (
    <div className="flex flex-col items-center gap-4 rounded-2xl border border-white/[0.08] bg-white/[0.015] px-8 py-14 text-center">
      <span className="flex h-14 w-14 items-center justify-center rounded-2xl border border-brand-purple/25 bg-brand-purple/10 text-brand-purple">
        <svg viewBox="0 0 24 24" width={26} height={26} fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
          <circle cx="11" cy="11" r="6.5" />
          <path d="m20 20-3.2-3.2" />
        </svg>
      </span>
      <div className="flex flex-col gap-1.5">
        <h3 className="font-display text-base font-semibold text-slate-100">No matches for these filters</h3>
        <p className="max-w-xs text-sm text-slate-400">
          Nothing in your download history matches the current search or filters.
        </p>
      </div>
      <button type="button" onClick={onClearFilters} className="btn-glass !px-4 !py-2 text-sm">
        Clear filters
      </button>
    </div>
  );
}

function HistoryRow({
  record,
  onDelete,
  onRetry,
}: {
  record: HistoryRecordOut;
  onDelete: (id: string, deleteFile: boolean) => void;
  onRetry: (id: string) => void;
}) {
  const statusColor =
    record.status === "completed"
      ? "text-emerald-400"
      : record.status === "failed"
        ? "text-red-400"
        : record.status === "cancelled"
          ? "text-slate-500"
          : "text-brand-aqua";

  return (
    <div className="glass-panel flex flex-wrap items-center gap-4 p-3 transition-colors hover:border-white/20">
      <div className="h-12 w-20 shrink-0 overflow-hidden rounded-lg bg-black/40">
        {record.thumbnail && <img src={record.thumbnail} alt="" className="h-full w-full object-cover" />}
      </div>

      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-slate-100" title={record.title ?? record.url}>
          {record.title || record.url}
        </p>
        <p className="text-xs text-slate-500">
          {PLATFORM_LABELS[record.platform]} · {record.format_label || "—"} · {formatBytes(record.filesize)} ·{" "}
          {formatDate(record.created_at)}
        </p>
      </div>

      <span className={`text-xs font-medium ${statusColor}`}>{record.status}</span>
      {record.status === "failed" && record.error_message && (
        <span className="max-w-[220px] truncate text-xs text-red-400/80" title={record.error_message}>
          {record.error_message}
        </span>
      )}

      <div className="flex shrink-0 gap-1.5">
        {record.status === "completed" && record.filepath && (
          <>
            <button
              onClick={() => api.openPath(record.filepath!).catch(() => undefined)}
              className="rounded-full border border-white/10 px-2.5 py-1 text-xs text-slate-300 hover:border-white/30"
            >
              Open file
            </button>
            <button
              onClick={() => api.openContainingFolder(record.filepath!).catch(() => undefined)}
              className="rounded-full border border-white/10 px-2.5 py-1 text-xs text-slate-300 hover:border-white/30"
            >
              Open folder
            </button>
          </>
        )}
        {(record.status === "failed" || record.status === "cancelled") && (
          <button
            onClick={() => onRetry(record.id)}
            className="rounded-full border border-brand-aqua/40 px-2.5 py-1 text-xs text-brand-aqua hover:border-brand-aqua/70"
          >
            Retry
          </button>
        )}
        <button
          onClick={() => onDelete(record.id, false)}
          className="rounded-full border border-white/10 px-2.5 py-1 text-xs text-slate-400 hover:border-red-500/40 hover:text-red-300"
        >
          Remove
        </button>
      </div>
    </div>
  );
}
