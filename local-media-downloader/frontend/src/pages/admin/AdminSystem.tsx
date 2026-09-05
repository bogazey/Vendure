import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import ErrorBanner from "../../components/ErrorBanner";
import { api } from "../../services/api";
import { statLabel, statTile, statValue } from "../../styles/ui";
import type { HealthResponse } from "../../types/api";
import AdminLayout from "./AdminLayout";
import { HealthDot } from "./adminShared";

export default function AdminSystem() {
  const { t } = useTranslation();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .health()
      .then(setHealth)
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  return (
    <AdminLayout>
      {error && <ErrorBanner message={t("admin.system.unreachable")} onDismiss={() => setError(false)} />}

      {loading ? (
        <p className="text-sm text-slate-500">{t("app.loading")}</p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <div className={statTile}>
            <span className={statLabel}>{t("admin.system.backend")}</span>
            <span className="flex items-center gap-2">
              <HealthDot ok={!error && health?.status === "ok"} />
              <span className={statValue}>
                {error ? t("admin.system.unreachable") : health?.status === "ok" ? t("admin.system.ready") : t("admin.system.degraded")}
              </span>
            </span>
          </div>

          <div className={statTile}>
            <span className={statLabel}>{t("admin.system.database")}</span>
            <span className="flex items-center gap-2">
              <HealthDot ok={!!health?.database_ok} />
              <span className={statValue}>{health?.database_ok ? t("admin.system.ready") : t("admin.system.degraded")}</span>
            </span>
          </div>

          <div className={statTile}>
            <span className={statLabel}>{t("admin.system.ffmpeg")}</span>
            <span className="flex items-center gap-2">
              <HealthDot ok={!!health?.ffmpeg_available} />
              <span className={statValue}>{health?.ffmpeg_available ? t("admin.system.found") : t("admin.system.missing")}</span>
            </span>
            {health?.ffmpeg_path && (
              <span className="truncate text-xs text-slate-500" dir="ltr" title={health.ffmpeg_path}>
                {health.ffmpeg_path}
              </span>
            )}
          </div>

          <div className={statTile}>
            <span className={statLabel}>{t("admin.system.ytdlp")}</span>
            <span className={statValue} dir="ltr">
              {health?.ytdlp_version || t("admin.system.missing")}
            </span>
          </div>

          <div className={statTile}>
            <span className={statLabel}>{t("admin.system.downloadDir")}</span>
            <span className="flex items-center gap-2">
              <HealthDot ok={!!health?.download_dir_writable} />
              <span className={statValue}>{health?.download_dir_writable ? t("admin.system.writable") : t("admin.system.notWritable")}</span>
            </span>
            {health?.download_dir && (
              <span className="truncate text-xs text-slate-500" dir="ltr" title={health.download_dir}>
                {health.download_dir}
              </span>
            )}
          </div>
        </div>
      )}
    </AdminLayout>
  );
}
