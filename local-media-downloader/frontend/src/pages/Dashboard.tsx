import { useState } from "react";
import DownloadQueue from "../components/DownloadQueue";
import ErrorBanner from "../components/ErrorBanner";
import FormatSelector from "../components/FormatSelector";
import MediaCard from "../components/MediaCard";
import UrlInput from "../components/UrlInput";
import { useDownloadProgress } from "../hooks/useDownloadProgress";
import { ApiError, api } from "../services/api";
import type { AnalyzeResponse, CreateDownloadRequest } from "../types/api";

export default function Dashboard() {
  const [media, setMedia] = useState<AnalyzeResponse | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<{ message: string; technical?: string | null } | null>(null);
  const [queuedMessage, setQueuedMessage] = useState<string | null>(null);
  const { jobs, connected } = useDownloadProgress();

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
        setError({ message: "An unexpected error occurred while analyzing this URL." });
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
      setQueuedMessage("Added to the download queue below.");
      setTimeout(() => setQueuedMessage(null), 4000);
    } catch (err) {
      if (err instanceof ApiError) {
        setError({ message: err.message, technical: err.technical });
      } else {
        setError({ message: "An unexpected error occurred while starting the download." });
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
    <div className="mx-auto flex max-w-3xl flex-col gap-8 px-6 py-10">
      <div className="flex flex-col gap-3 text-center">
        <h1 className="text-2xl font-bold tracking-tight text-slate-50">Download media from a URL</h1>
        <p className="text-sm text-slate-500">
          Supports YouTube, TikTok, Instagram, and Facebook. Only content you're lawfully allowed to access.
        </p>
      </div>

      <UrlInput onAnalyze={handleAnalyze} loading={analyzing} />

      {error && <ErrorBanner message={error.message} technical={error.technical} onDismiss={() => setError(null)} />}

      {media && (
        <div className="flex flex-col gap-4">
          <MediaCard media={media} />
          <FormatSelector media={media} onStartDownload={handleStartDownload} submitting={submitting} />
          {queuedMessage && (
            <p className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-2 text-sm text-emerald-300">
              {queuedMessage}
            </p>
          )}
        </div>
      )}

      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Active &amp; Recent Downloads</h2>
          <span className="flex items-center gap-1.5 text-xs text-slate-500">
            <span className={`h-1.5 w-1.5 rounded-full ${connected ? "bg-emerald-400" : "bg-amber-400"}`} />
            {connected ? "Live" : "Reconnecting…"}
          </span>
        </div>
        <DownloadQueue jobs={jobs} onCancel={handleCancel} />
      </div>
    </div>
  );
}
