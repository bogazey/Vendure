import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import AdSlot from "../components/AdSlot";
import DownloadQueue from "../components/DownloadQueue";
import ErrorBanner from "../components/ErrorBanner";
import FormatSelector from "../components/FormatSelector";
import MediaCard from "../components/MediaCard";
import UrlInput from "../components/UrlInput";
import { useAuth } from "../context/AuthContext";
import { useDownloadProgress } from "../hooks/useDownloadProgress";
import { track } from "../lib/analytics";
import { ApiError, api, triggerFileDownload } from "../services/api";
import { appPageShell } from "../styles/ui";
import type { AnalyzeResponse, CreateDownloadRequest, DownloadStage, GuestQuotaOut } from "../types/api";

const UPGRADE_ERROR_CODES = new Set(["PLAN_LIMIT_REACHED", "DAILY_LIMIT_REACHED", "FEATURE_NOT_INCLUDED", "UPGRADE_REQUIRED"]);

// Signed-out visitors get exactly the Free plan's resolution ceiling (see
// guest_service.py, which reuses Plan.FREE's policy) - this mirrors that
// same, already publicly-advertised number (see the pricing/FAQ copy) only
// for display purposes; the backend is the actual enforcement point either way.
const GUEST_MAX_RESOLUTION_HEIGHT = 720;

export default function Dashboard() {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const { account, loading: authLoading } = useAuth();
  const [media, setMedia] = useState<AnalyzeResponse | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<{ message: string; technical?: string | null } | null>(null);
  const [queuedMessage, setQueuedMessage] = useState<string | null>(null);
  // Anonymous visitors get a small guest download allowance (see
  // guest_service.py) so they can try the product before creating an
  // account - null while unknown or once signed in (an authenticated
  // account never has a guest quota, it has real plan credits instead).
  const [guestQuota, setGuestQuota] = useState<GuestQuotaOut | null>(null);
  const { jobs, connected } = useDownloadProgress();
  const previousStages = useRef<Map<string, DownloadStage>>(new Map());
  // Job ids created from THIS page instance (via handleStartDownload) -
  // never populated from the initial history fetch/SSE snapshot, so an old
  // completed job loaded on mount (or restored after a refresh) is never a
  // candidate for auto-download, only one the user just started here.
  const sessionJobIdsRef = useRef<Set<string>>(new Set());
  // Job ids whose automatic download has already fired - separate from
  // sessionJobIdsRef so "started here" and "already auto-downloaded" are
  // each their own concern; guards against firing twice from repeated SSE
  // frames, polling, re-renders, or React StrictMode's double effect-invoke
  // (refs persist across that, so this Set is never silently recreated).
  const autoDownloadedRef = useRef<Set<string>>(new Set());

  const refreshGuestQuota = useCallback(() => {
    if (account) return;
    api
      .getGuestQuota()
      .then(setGuestQuota)
      .catch(() => {
        // Not fatal - the banner just stays hidden until the next success.
      });
  }, [account]);

  useEffect(() => {
    if (authLoading) return;
    if (account) {
      setGuestQuota(null);
      return;
    }
    refreshGuestQuota();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, account]);

  const guestQuotaExhausted = !account && guestQuota !== null && guestQuota.remaining <= 0;

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
        if (job.stage === "completed") {
          track("download_completed");
          // Only a job this page instance actually started, that hasn't
          // already been auto-downloaded, and that really has a finished
          // file to hand over (never failed/cancelled/analysis-only - those
          // can't reach "completed" with a filepath at all) gets the
          // browser download kicked off automatically - see
          // triggerFileDownload's own comment for why a hidden <a> rather
          // than window.open()/a fetch-to-Blob.
          if (job.filepath && sessionJobIdsRef.current.has(job.id) && !autoDownloadedRef.current.has(job.id)) {
            autoDownloadedRef.current.add(job.id);
            try {
              triggerFileDownload(job.id);
            } catch {
              // Never let a client-side download hiccup touch the job's own
              // state - it stays "completed" and visible, and the manual
              // "Download again" button is still right there as a fallback.
            }
          }
        } else if (job.stage === "failed") {
          track("download_failed");
        }
        // A completed job consumes one guest download; a failed or
        // cancelled job refunds its reservation (see guest_service.py) -
        // either way the remaining count on screen needs to catch up.
        if (!account && ["completed", "failed", "cancelled"].includes(job.stage)) {
          refreshGuestQuota();
        }
        previousStages.current.set(job.id, job.stage);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobs, account]);

  const handleAnalyze = async (url: string) => {
    track("analyze_started");
    setAnalyzing(true);
    setError(null);
    setMedia(null);
    try {
      const result = await api.analyze(url);
      setMedia(result);
      track("analyze_succeeded");
    } catch (err) {
      track("analyze_failed");
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
      const job = await api.createDownload(request);
      // Registers this job as eligible for auto-download once it completes -
      // an old job loaded from history (or restored after a refresh) is
      // never added here, so it never auto-downloads (see sessionJobIdsRef).
      sessionJobIdsRef.current.add(job.id);
      track("download_started");
      setQueuedMessage(t("app.queued"));
      setTimeout(() => setQueuedMessage(null), 4000);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.code === "GUEST_QUOTA_EXCEEDED") {
          setError({ message: t("guest.quotaError") });
          track("upgrade_prompt_shown", { code: err.code });
          // Client-side count can drift (multiple tabs, a stale fetch) -
          // resync from the server so the CTA panel below replaces the
          // format selector immediately instead of on next reload.
          refreshGuestQuota();
        } else {
          setError({ message: err.message, technical: err.technical });
          if (err.code && UPGRADE_ERROR_CODES.has(err.code)) {
            track("upgrade_prompt_shown", { code: err.code });
          }
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

      {!account && guestQuota && (
        <p
          className={`text-center text-sm font-medium ${
            guestQuotaExhausted ? "text-amber-300" : "text-brand-aqua"
          }`}
        >
          {guestQuotaExhausted
            ? t("guest.quotaTitle")
            : guestQuota.remaining === 1
              ? t("guest.oneRemaining")
              : t("guest.available", { count: guestQuota.remaining })}
        </p>
      )}

      <UrlInput onAnalyze={handleAnalyze} loading={analyzing} />
      <AdSlot placement="LANDING_DOWNLOADER" />

      {error && <ErrorBanner message={error.message} technical={error.technical} onDismiss={() => setError(null)} />}

      {media && (
        <div className="flex flex-col gap-4">
          <MediaCard media={media} />
          {guestQuotaExhausted ? (
            <div className="glass-panel-raised flex flex-col items-center gap-3 p-6 text-center">
              <h2 className="font-display text-lg font-semibold text-slate-50">{t("guest.quotaTitle")}</h2>
              <p className="max-w-md text-sm text-slate-400">{t("guest.quotaBody")}</p>
              <Link
                to="/signup"
                state={{ initialUrl: media.url }}
                className="btn-gradient !px-7 !py-3"
                onClick={() => track("upgrade_prompt_shown", { code: "GUEST_QUOTA_EXCEEDED", source: "cta" })}
              >
                {t("guest.createAccount")}
              </Link>
            </div>
          ) : (
            <FormatSelector
              media={media}
              onStartDownload={handleStartDownload}
              submitting={submitting}
              maxResolutionHeight={account ? account.features.max_resolution_height : GUEST_MAX_RESOLUTION_HEIGHT}
            />
          )}
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
