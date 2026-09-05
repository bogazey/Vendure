import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import ErrorBanner from "../components/ErrorBanner";
import { useAuth } from "../context/AuthContext";
import { ApiError, api } from "../services/api";
import { appPageShell } from "../styles/ui";

export default function Billing() {
  const { t } = useTranslation();
  const { account } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [openingPortal, setOpeningPortal] = useState(false);

  if (!account) return null;
  const { subscription, usage } = account;
  const isFree = subscription.plan === "free";

  const handleManageBilling = async () => {
    setOpeningPortal(true);
    setError(null);
    try {
      const { url } = await api.createBillingPortalSession();
      if (url) {
        window.open(url, "_blank", "noopener,noreferrer");
      } else {
        setError(
          t("billingPage.portalUnavailable")
        );
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("billingPage.portalError"));
    } finally {
      setOpeningPortal(false);
    }
  };

  const usageUsed = usage.plan === "free" ? usage.daily_free_downloads_used ?? 0 : usage.credits_used ?? 0;
  const usageTotal =
    usage.plan === "free"
      ? (usage.daily_free_downloads_used ?? 0) + (usage.daily_free_downloads_remaining ?? 0)
      : usage.credits_included ?? 0;
  const usagePct = usageTotal > 0 ? Math.min(100, Math.round((usageUsed / usageTotal) * 100)) : 0;

  return (
    <div className={appPageShell}>
      <h1 className="font-display text-xl font-bold text-slate-50">{t("app.billingTitle")}</h1>

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      <section className="glass-panel flex flex-col gap-4 p-6">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t("app.currentPlan")}</h2>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="rounded-full bg-brand-gradient px-3 py-1 text-sm font-semibold text-white shadow-glow">
              {t(`pricing.plans.${subscription.plan}.name`)}
            </span>
            <span
              className={`text-sm font-medium ${
                subscription.status === "active"
                  ? "text-emerald-400"
                  : subscription.status === "past_due"
                    ? "text-red-400"
                    : subscription.status === "trialing"
                      ? "text-brand-aqua"
                      : "text-slate-400"
              }`}
            >
              {t(`status.${subscription.status}`, { defaultValue: subscription.status })}
            </span>
          </div>
          {subscription.current_period_end && (
            <span className="text-sm text-slate-400">
              {subscription.cancel_at_period_end ? `${t("billingPage.accessEnds")} ` : `${t("billingPage.renews")} `}
              {new Date(subscription.current_period_end).toLocaleDateString()}
            </span>
          )}
        </div>
        {subscription.billing_period && (
          <div className="flex items-center justify-between border-t border-white/[0.06] pt-3 text-sm">
            <span className="text-slate-400">{t("billingPage.cadence")}</span>
            <span className="capitalize text-slate-200">{t(`billingPage.${subscription.billing_period}`)}</span>
          </div>
        )}
        {subscription.cancel_at_period_end && (
          <p className="rounded-xl border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
            {t("billingPage.cancelNotice")}
          </p>
        )}
      </section>

      <section className="glass-panel flex flex-col gap-3 p-6">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t("app.usagePeriod")}</h2>
          <span className="text-sm font-medium text-slate-100">
            {usageUsed} / {usageTotal || "—"}
          </span>
        </div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/[0.06]">
          <div
            className="h-full rounded-full bg-brand-gradient transition-[width] duration-300"
            style={{ width: `${usagePct}%` }}
          />
        </div>
        <p className="text-xs text-slate-500">
          {usage.plan === "free" ? t("billingPage.freeUsed") : t("billingPage.creditsUsed")}
        </p>
      </section>

      <div className="flex flex-wrap gap-3">
        {isFree ? (
          <Link to="/pricing" className="btn-gradient">
            {t("billingPage.upgrade")}
          </Link>
        ) : (
          <>
            <Link to="/pricing" className="btn-glass">
              {t("billingPage.change")}
            </Link>
            <button type="button" onClick={handleManageBilling} disabled={openingPortal} className="btn-gradient">
              {openingPortal ? t("app.opening") : t("app.manageBilling")}
            </button>
          </>
        )}
      </div>
      <p className="text-xs text-slate-600">
        {t("billingPage.notice")}
      </p>
    </div>
  );
}
