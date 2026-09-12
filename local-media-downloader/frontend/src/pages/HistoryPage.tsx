import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import AdSlot from "../components/AdSlot";
import ErrorBanner from "../components/ErrorBanner";
import { ApiError, api, downloadFileUrl } from "../services/api";
import { appPageShell } from "../styles/ui";
import type { HistoryRecordOut, Platform } from "../types/api";
import { formatBytes, formatDate } from "../utils/format";
import { PLATFORM_LABELS } from "../utils/platform";

const PLATFORM_OPTIONS: Platform[] = ["youtube", "tiktok", "instagram", "facebook"];
const STATUS_OPTIONS = ["completed", "failed", "cancelled", "downloading", "queued"];

export default function HistoryPage() {
  const { t } = useTranslation();
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
      setError(err instanceof ApiError ? err.message : t("historyPage.loadError"));
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
      setError(err instanceof ApiError ? err.message : t("historyPage.removeError"));
    }
  };

  const handleClear = async (deleteFiles: boolean) => {
    try {
      await api.clearHistory(deleteFiles);
      setRecords([]);
      setConfirmClear(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("historyPage.clearError"));
    }
  };

  const handleRetry = async (id: string) => {
    try {
      await api.retryDownload(id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("historyPage.retryError"));
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
        <h1 className="font-display text-xl font-bold text-slate-50">{t("app.history")}</h1>
        <button
          type="button"
          onClick={() => setConfirmClear(true)}
          className="rounded-full border border-white/10 px-3 py-1.5 text-sm text-slate-400 transition-colors hover:border-red-500/40 hover:text-red-300"
        >
          {t("app.clearHistory")}
        </button>
      </div>

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      <AdSlot placement="DOWNLOAD_HISTORY" />

      {confirmClear && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200 backdrop-blur-xl">
          <span>{t("historyPage.clearPrompt")}</span>
          <div className="flex gap-2">
            <button onClick={() => handleClear(false)} className="rounded-full bg-amber-500 px-3 py-1 text-black">
              {t("historyPage.recordsOnly")}
            </button>
            <button onClick={() => handleClear(true)} className="rounded-full bg-red-600 px-3 py-1 text-white">
              {t("historyPage.recordsFiles")}
            </button>
            <button onClick={() => setConfirmClear(false)} className="rounded-full px-3 py-1 text-amber-200/70">
              {t("common.cancel")}
            </button>
          </div>
        </div>
      )}

      <div className="glass-panel flex flex-wrap gap-3 p-3">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t("app.search")}
          className="input-glass min-w-[220px] flex-1 py-2"
        />
        <select
          value={platform}
          onChange={(e) => setPlatform(e.target.value)}
          className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-slate-200 backdrop-blur-xl focus:border-brand-purple/60 focus:outline-none"
        >
          <option value="">{t("app.allPlatforms")}</option>
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
          <option value="">{t("app.allStatuses")}</option>
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {t(`status.${s}`)}
            </option>
          ))}
        </select>
        <select
          value={order}
          onChange={(e) => setOrder(e.target.value as "newest" | "oldest")}
          className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-slate-200 backdrop-blur-xl focus:border-brand-purple/60 focus:outline-none"
        >
          <option value="newest">{t("app.newest")}</option>
          <option value="oldest">{t("app.oldest")}</option>
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
  const { t } = useTranslation();
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
        <h3 className="font-display text-base font-semibold text-slate-100">{t("app.nothing")}</h3>
        <p className="max-w-xs text-sm text-slate-400">
          {t("app.nothingBody")}
        </p>
      </div>
      <Link to="/dashboard" className="btn-gradient !px-4 !py-2 text-sm">
        {t("app.downloadSomething")}
      </Link>
    </div>
  );
}

function FilteredEmptyState({ onClearFilters }: { onClearFilters: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col items-center gap-4 rounded-2xl border border-white/[0.08] bg-white/[0.015] px-8 py-14 text-center">
      <span className="flex h-14 w-14 items-center justify-center rounded-2xl border border-brand-purple/25 bg-brand-purple/10 text-brand-purple">
        <svg viewBox="0 0 24 24" width={26} height={26} fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round">
          <circle cx="11" cy="11" r="6.5" />
          <path d="m20 20-3.2-3.2" />
        </svg>
      </span>
      <div className="flex flex-col gap-1.5">
        <h3 className="font-display text-base font-semibold text-slate-100">{t("app.noMatches")}</h3>
        <p className="max-w-xs text-sm text-slate-400">
          {t("app.noMatchesBody")}
        </p>
      </div>
      <button type="button" onClick={onClearFilters} className="btn-glass !px-4 !py-2 text-sm">
        {t("app.clearFilters")}
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
  const { t } = useTranslation();
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

      <span className={`text-xs font-medium ${statusColor}`}>{t(`status.${record.status}`, { defaultValue: record.status })}</span>
      {record.status === "failed" && record.error_message && (
        <span className="max-w-[220px] truncate text-xs text-red-400/80" title={record.error_message}>
          {record.error_message}
        </span>
      )}

      <div className="flex shrink-0 gap-1.5">
        {record.status === "completed" && record.filepath && (
          <>
            <a
              href={downloadFileUrl(record.id)}
              className="rounded-full border border-white/10 px-2.5 py-1 text-xs text-slate-300 hover:border-white/30"
            >
              {t("app.downloadAgain")}
            </a>
          </>
        )}
        {(record.status === "failed" || record.status === "cancelled") && (
          <button
            onClick={() => onRetry(record.id)}
            className="rounded-full border border-brand-aqua/40 px-2.5 py-1 text-xs text-brand-aqua hover:border-brand-aqua/70"
          >
            {t("app.retry")}
          </button>
        )}
        <button
          onClick={() => onDelete(record.id, false)}
          className="rounded-full border border-white/10 px-2.5 py-1 text-xs text-slate-400 hover:border-red-500/40 hover:text-red-300"
        >
          {t("app.remove")}
        </button>
      </div>
    </div>
  );
}
