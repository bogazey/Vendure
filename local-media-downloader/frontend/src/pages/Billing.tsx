import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import BillingManagement from "../components/BillingManagement";
import { useAuth } from "../context/AuthContext";
import { appPageShell } from "../styles/ui";

export default function Billing() {
  const { t } = useTranslation();
  const { account } = useAuth();
  if (!account) return null;
  const { subscription, usage } = account;
  const isFree = subscription.plan === "free";
  // A gifted subscription was granted by an admin, never purchased through
  // Paddle - see docs/ANALYTICS.md. No Paddle actions (change plan, cancel,
  // update payment method) apply, so <BillingManagement /> is skipped
  // entirely here rather than showing controls that would just 404.
  const isGifted = subscription.provider === "gifted";

  const usageUsed = usage.plan === "free" ? usage.daily_free_downloads_used ?? 0 : usage.credits_used ?? 0;
  const usageTotal =
    usage.plan === "free"
      ? (usage.daily_free_downloads_used ?? 0) + (usage.daily_free_downloads_remaining ?? 0)
      : usage.credits_included ?? 0;
  const usagePct = usageTotal > 0 ? Math.min(100, Math.round((usageUsed / usageTotal) * 100)) : 0;

  return (
    <div className={appPageShell}>
      <h1 className="font-display text-xl font-bold text-slate-50">{t("app.billingTitle")}</h1>



      <section className="glass-panel flex flex-col gap-4 p-6">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t("app.currentPlan")}</h2>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="rounded-full bg-brand-gradient px-3 py-1 text-sm font-semibold text-white shadow-glow">
              {t(`pricing.plans.${subscription.plan}.name`)}
            </span>
            {isGifted ? (
              <span className="rounded-full bg-brand-aqua/15 px-3 py-1 text-sm font-medium text-brand-aqua">
                {t("billingPage.giftedBadge")}
              </span>
            ) : (
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
            )}
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
        {isGifted && (
          <p className="rounded-xl border border-brand-aqua/25 bg-brand-aqua/10 px-3 py-2 text-xs text-brand-aqua">
            {t("billingPage.giftedNotice")}
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
        ) : !isGifted ? (
          <a href="#billing-management" className="btn-gradient">{t("app.manageBilling")}</a>
        ) : null}
      </div>
      {!isGifted && <BillingManagement />}
      <p className="text-xs text-slate-600">
        {t("billingPage.notice")}
      </p>
    </div>
  );
}
