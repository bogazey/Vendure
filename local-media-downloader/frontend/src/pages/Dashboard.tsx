import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import AdSlot from "../components/AdSlot";
import DownloadQueue from "../components/DownloadQueue";
import ErrorBanner from "../components/ErrorBanner";
import FormatSelector from "../components/FormatSelector";
import MediaCard from "../components/MediaCard";
import UrlInput from "../components/UrlInput";
import { useDownloadProgress } from "../hooks/useDownloadProgress";
import { track } from "../lib/analytics";
import { ApiError, api } from "../services/api";
import { appPageShell } from "../styles/ui";
import type { AnalyzeResponse, CreateDownloadRequest, DownloadStage } from "../types/api";

const UPGRADE_ERROR_CODES = new Set(["PLAN_LIMIT_REACHED", "DAILY_LIMIT_REACHED", "FEATURE_NOT_INCLUDED", "UPGRADE_REQUIRED"]);

export default function Dashboard() {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const [media, setMedia] = useState<AnalyzeResponse | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<{ message: string; technical?: string | null } | null>(null);
  const [queuedMessage, setQueuedMessage] = useState<string | null>(null);
  const { jobs, connected } = useDownloadProgress();
  const previousStages = useRef<Map<string, DownloadStage>>(new Map());

  // A URL pasted into the hero input before signing up (or while logged
  // out) arrives here via router state - pick it up once and run it
  // through the normal analyze flow, then clear the state so a refresh or
  // back-navigation doesn't silently re-trigger it.
  useEffect(() => {
    const initialUrl = (location.state as { initialUrl?: string } | null)?.initialUrl;
    if (initialUrl) {
      handleAnalyze(initialUrl);
      navigate(location.pathname, { replace: true, state: null });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    for (const job of jobs) {
      const prevStage = previousStages.current.get(job.id);
      if (prevStage !== job.stage) {
        if (job.stage === "completed") track("download_completed");
        else if (job.stage === "failed") track("download_failed");
        previousStages.current.set(job.id, job.stage);
      }
    }
  }, [jobs]);

  const handleAnalyze = async (url: string) => {
    setAnalyzing(true);
    setError(null);
    setMedia(null);
    try {
      const result = await api.analyze(url);
      setMedia(result);
    } catch (err) {
      if (err instanceof ApiError) {
        setError({ message: err.message, technical: err.technical });
      } else {
        setError({ message: t("app.analyzeError") });
      }
    } finally {
      setAnalyzing(false);
    }
  };

  const handleStartDownload = async (request: CreateDownloadRequest) => {
    setSubmitting(true);
    setError(null);
    try {
      await api.createDownload(request);
      track("download_started");
      setQueuedMessage(t("app.queued"));
      setTimeout(() => setQueuedMessage(null), 4000);
    } catch (err) {
      if (err instanceof ApiError) {
        setError({ message: err.message, technical: err.technical });
        if (err.code && UPGRADE_ERROR_CODES.has(err.code)) {
          track("upgrade_prompt_shown", { code: err.code });
        }
      } else {
        setError({ message: t("app.downloadError") });
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleCancel = async (id: string) => {
    try {
      await api.cancelDownload(id);
    } catch {
      // Cancellation failures aren't critical; the job will simply keep running.
    }
  };

  return (
    <div className={appPageShell}>
      <div className="dashboard-intro flex flex-col gap-3 text-center">
        <h1 className="font-display text-2xl font-bold tracking-tight text-slate-50">{t("app.download")}</h1>
        <p className="text-sm text-slate-400">
          {t("app.downloadBody")}
        </p>
      </div>

      <UrlInput onAnalyze={handleAnalyze} loading={analyzing} />
      <AdSlot placement="LANDING_DOWNLOADER" />

      {error && <ErrorBanner message={error.message} technical={error.technical} onDismiss={() => setError(null)} />}

      {media && (
        <div className="flex flex-col gap-4">
          <MediaCard media={media} />
          <FormatSelector media={media} onStartDownload={handleStartDownload} submitting={submitting} />
          {queuedMessage && (
            <p className="rounded-2xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-2 text-sm text-emerald-300 backdrop-blur-xl">
              {queuedMessage}
            </p>
          )}
        </div>
      )}

      <div className="download-area flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">{t("app.active")}</h2>
          <span className="flex items-center gap-1.5 text-xs text-slate-500">
            <span className={`h-1.5 w-1.5 rounded-full ${connected ? "bg-emerald-400" : "bg-amber-400"}`} />
            {connected ? t("app.live") : t("app.reconnecting")}
          </span>
        </div>
        <DownloadQueue jobs={jobs} onCancel={handleCancel} />
        {jobs.some((j) => j.stage === "completed") && <AdSlot placement="DOWNLOAD_RESULT" />}
      </div>

      <AdSlot placement="USER_DASHBOARD" />
    </div>
  );
}
