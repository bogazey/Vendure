import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useTranslation } from "react-i18next";

function ProgressBar({ used, total }: { used: number; total: number }) {
  const pct = total > 0 ? Math.min(100, (used / total) * 100) : 0;
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-white/[0.06]">
      <div
        className={`h-full rounded-full ${pct >= 90 ? "bg-amber-400" : "bg-brand-gradient"}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

export default function Usage() {
  const { t } = useTranslation();
  const { account } = useAuth();
  if (!account) return null;
  const { usage, features } = account;

  const isFree = usage.plan === "free";
  const used = isFree ? usage.daily_free_downloads_used ?? 0 : usage.credits_used;
  const total = isFree
    ? (usage.daily_free_downloads_used ?? 0) + (usage.daily_free_downloads_remaining ?? 0)
    : usage.credits_included ?? 0;
  const remaining = isFree ? usage.daily_free_downloads_remaining ?? 0 : usage.credits_remaining ?? 0;

  return (
    <div className="app-page relative z-10 mx-auto flex w-full max-w-5xl flex-col gap-6 px-5 py-8 sm:px-8 lg:px-10 lg:py-10">
      <h1 className="font-display text-xl font-bold text-slate-50">{t("app.usage")}</h1>

      <section className="glass-panel flex flex-col gap-4 p-5">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
            {isFree ? t("usagePage.freeToday") : t("usagePage.creditsPeriod")}
          </h2>
          <span className="text-sm text-slate-300">
            {used} / {total}
          </span>
        </div>
        <ProgressBar used={used} total={total} />
        <p className="text-xs text-slate-500">
          {isFree ? t("usagePage.remainingDownloads", { count: remaining }) : t("usagePage.remainingCredits", { count: remaining, date: new Date(usage.period_end).toLocaleDateString() })}
        </p>
      </section>

      <section className="glass-panel flex flex-col gap-3 p-5">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">{t("usagePage.limits")}</h2>
        <div className="grid grid-cols-2 gap-y-2 text-sm text-slate-400">
          <span>{t("usagePage.resolution")}</span>
          <span className="text-slate-200">{features.max_resolution_height ? `${features.max_resolution_height}p` : t("common.bestAvailable")}</span>
          <span>{t("usagePage.downloads4k")}</span>
          <span className="text-slate-200">{features.can_use_4k ? t("common.included") : t("common.notIncluded")}</span>
          <span>{t("usagePage.batch")}</span>
          <span className="text-slate-200">{features.can_use_batch ? t("common.included") : t("common.notIncluded")}</span>
          <span>{t("usagePage.advanced")}</span>
          <span className="text-slate-200">{features.can_use_advanced_formats ? t("common.included") : t("common.notIncluded")}</span>
          <span>{t("usagePage.clip")}</span>
          <span className="text-slate-200">{features.can_use_clip_range ? t("common.included") : t("common.notIncluded")}</span>
          <span>{t("usagePage.cookies")}</span>
          <span className="text-slate-200">{features.can_use_browser_cookies ? t("common.included") : t("common.notIncluded")}</span>
          <span>{t("usagePage.priority")}</span>
          <span className="text-slate-200">{features.queue_priority}</span>
        </div>
      </section>

      {isFree && (
        <Link to="/pricing" className="btn-gradient self-start">
          {t("usagePage.upgrade")}
        </Link>
      )}
    </div>
  );
}
