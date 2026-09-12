import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import ErrorBanner from "../../components/ErrorBanner";
import { ApiError, api } from "../../services/api";
import { statLabel, statTile, statValue } from "../../styles/ui";
import type { AnalyticsOverviewOut } from "../../types/analytics";
import type { AdminHealthOut, AdminOverviewOut } from "../../types/commercial";
import { formatDate } from "../../utils/format";
import AdminLayout from "./AdminLayout";
import { actionLabelKey, HealthDot } from "./adminShared";

export default function AdminOverview() {
  const { t } = useTranslation();
  const [overview, setOverview] = useState<AdminOverviewOut | null>(null);
  const [analytics, setAnalytics] = useState<AnalyticsOverviewOut | null>(null);
  const [health, setHealth] = useState<AdminHealthOut | null>(null);
  const [healthError, setHealthError] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.adminGetOverview().catch((err) => {
        setError(err instanceof ApiError ? err.message : t("admin.overview.loadError"));
        return null;
      }),
      api.adminGetHealth().then(setHealth).catch(() => setHealthError(true)),
      // Best-effort - the Overview page must stay useful even if the
      // analytics summary alone fails to load (see docs/ANALYTICS.md).
      api.adminAnalyticsOverview("today").then(setAnalytics).catch(() => undefined),
    ])
      .then(([overviewResult]) => {
        if (overviewResult) setOverview(overviewResult);
      })
      .finally(() => setLoading(false));
  }, [t]);

  return (
    <AdminLayout>
      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      {loading && !overview ? (
        <p className="text-sm text-slate-500">{t("app.loading")}</p>
      ) : overview ? (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <div className={statTile}>
              <span className={statLabel}>{t("admin.overview.totalUsers")}</span>
              <span className={statValue}>{overview.total_users}</span>
            </div>
            <div className={statTile}>
              <span className={statLabel}>{t("admin.overview.activeUsers")}</span>
              <span className={statValue}>{overview.active_users}</span>
            </div>
            <div className={statTile}>
              <span className={statLabel}>{t("admin.overview.paidSubscribers")}</span>
              <span className={statValue}>{overview.paid_subscribers}</span>
            </div>
            <div className={statTile}>
              <span className={statLabel}>{t("admin.overview.freeCount")}</span>
              <span className={statValue}>{overview.free_count}</span>
            </div>
            <div className={statTile}>
              <span className={statLabel}>{t("admin.overview.proCount")}</span>
              <span className={statValue}>{overview.pro_count}</span>
            </div>
            <div className={statTile}>
              <span className={statLabel}>{t("admin.overview.creatorCount")}</span>
              <span className={statValue}>{overview.creator_count}</span>
            </div>
            <div className={statTile}>
              <span className={statLabel}>{t("admin.overview.giftedSubscribers")}</span>
              <span className={statValue}>{overview.gifted_subscribers}</span>
            </div>
          </div>

          {analytics && (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
              <div className={statTile}>
                <span className={statLabel}>{t("admin.overview.visitorsToday")}</span>
                <span className={statValue}>{analytics.visitors}</span>
              </div>
              <div className={statTile}>
                <span className={statLabel}>{t("admin.overview.downloadsToday")}</span>
                <span className={statValue}>{analytics.downloads_completed}</span>
              </div>
              <div className={statTile}>
                <span className={statLabel}>{t("admin.overview.newUsersToday")}</span>
                <span className={statValue}>{analytics.new_users}</span>
              </div>
              <div className={statTile}>
                <span className={statLabel}>{t("admin.overview.downloadSuccessRate")}</span>
                <span className={statValue}>
                  {analytics.download_success_rate !== null ? `${analytics.download_success_rate.toFixed(1)}%` : "—"}
                </span>
              </div>
              <div className={statTile}>
                <span className={statLabel}>{t("admin.overview.activeNow")}</span>
                <span className={statValue}>{analytics.active_now}</span>
              </div>
            </div>
          )}

          <div className="grid gap-3 sm:grid-cols-2">
            <div className={statTile}>
              <span className={statLabel}>{t("admin.overview.creditsConsumed")}</span>
              <span className={statValue}>{overview.credits_consumed_current_period}</span>
            </div>
            <div className="glass-panel flex flex-col gap-2 p-4">
              <span className={statLabel}>{t("admin.system.title")}</span>
              <div className="flex flex-wrap items-center gap-4 text-sm text-slate-300">
                <span className="flex items-center gap-1.5">
                  <HealthDot ok={!healthError && !!health && health.status === "ok"} />
                  {t("admin.system.backend")}
                </span>
                <span className="flex items-center gap-1.5">
                  <HealthDot ok={!healthError && !!health?.ffmpeg_available} />
                  {t("admin.system.ffmpeg")}
                </span>
                <span className="flex items-center gap-1.5">
                  <HealthDot ok={!healthError && !!health?.ytdlp_version} />
                  {t("admin.system.ytdlp")}
                </span>
              </div>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-2">
            <section className="glass-panel flex flex-col gap-3 p-4">
              <h2 className="text-sm font-semibold text-slate-100">{t("admin.overview.recentFailures")}</h2>
              {overview.recent_billing_failures.length === 0 ? (
                <p className="text-sm text-slate-500">{t("admin.overview.noFailures")}</p>
              ) : (
                <ul className="flex flex-col gap-2 text-sm">
                  {overview.recent_billing_failures.map((event) => (
                    <li key={event.provider_event_id} className="flex items-center justify-between gap-3 border-t border-white/[0.06] pt-2 first:border-0 first:pt-0">
                      <span className="min-w-0 truncate text-slate-300" dir="ltr">
                        {event.user_email || event.user_id || t("admin.billing.unknownUser")}
                      </span>
                      <span className="shrink-0 text-xs text-slate-500" dir="ltr">
                        {formatDate(event.processed_at)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="glass-panel flex flex-col gap-3 p-4">
              <h2 className="text-sm font-semibold text-slate-100">{t("admin.overview.recentActions")}</h2>
              {overview.recent_admin_actions.length === 0 ? (
                <p className="text-sm text-slate-500">{t("admin.activity.empty")}</p>
              ) : (
                <ul className="flex flex-col gap-2 text-sm">
                  {overview.recent_admin_actions.map((entry) => (
                    <li key={entry.id} className="flex items-center justify-between gap-3 border-t border-white/[0.06] pt-2 first:border-0 first:pt-0">
                      <span className="min-w-0 truncate text-slate-300">
                        {t(actionLabelKey(entry.action))}
                        {entry.target_email ? (
                          <span className="text-slate-500">
                            {" "}
                            · <span dir="ltr">{entry.target_email}</span>
                          </span>
                        ) : null}
                      </span>
                      <span className="shrink-0 text-xs text-slate-500" dir="ltr">
                        {formatDate(entry.created_at)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        </>
      ) : null}
    </AdminLayout>
  );
}
