import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import ErrorBanner from "../components/ErrorBanner";
import { useAuth } from "../context/AuthContext";
import { track } from "../lib/analytics";
import { openPaddleCheckout } from "../lib/paddle";
import { ApiError, api } from "../services/api";
import type { BillingPeriod, Plan } from "../types/commercial";
import { PLAN_PRICES } from "../types/commercial";

const ASSETS = "/assets/design";

const PLAN_ROWS: Plan[] = ["free", "pro", "creator"];

export default function Pricing() {
  const { t } = useTranslation();
  const { account, refresh } = useAuth();
  const navigate = useNavigate();
  const [period, setPeriod] = useState<BillingPeriod>("monthly");
  const [error, setError] = useState<string | null>(null);
  const [checkingOut, setCheckingOut] = useState<Plan | null>(null);
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    track("pricing_view");
  }, []);

  const handleSelect = async (plan: Plan) => {
    setError(null);
    if (plan === "free") {
      if (!account) navigate("/signup");
      else navigate("/dashboard");
      return;
    }
    if (!account) {
      navigate("/signup", { state: { intendedPlan: plan, intendedPeriod: period } });
      return;
    }
    if (["active", "trialing", "past_due"].includes(account.subscription.status)) {
      navigate("/billing");
      return;
    }
    setCheckingOut(plan);
    track("checkout_started", { plan });
    try {
      const checkout = await api.createCheckout(plan, period);
      await openPaddleCheckout(checkout, (event) => {
        if (event.name === "checkout.completed") {
          // The account's plan itself only actually changes once Paddle's
          // webhook lands (never trust the checkout UI alone - see
          // COMMERCIAL_ARCHITECTURE.md §5), which is usually seconds away -
          // a short poll covers that gap instead of leaving the page stale.
          setConfirming(true);
          refresh();
          setTimeout(refresh, 3000);
          setTimeout(() => {
            refresh();
            setConfirming(false);
          }, 8000);
        }
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("pricing.checkoutError"));
    } finally {
      setCheckingOut(null);
    }
  };

  const currentPlan = account?.subscription.plan;

  return (
    <div className="pricing-page relative overflow-hidden">
      {/* Section-transition glows from the supplied design asset pack,
          per docs/ASSET_PLACEMENT.md ("section transitions / pricing / CTA
          backgrounds") - a soft blue sweep from the lower-left and a
          fainter violet one from the right, echoing the master reference. */}
      <img
        src={`${ASSETS}/backgrounds/section-wave-left.svg`}
        alt=""
        aria-hidden="true"
        className="pointer-events-none absolute -bottom-24 -left-32 -z-10 h-[44rem] w-[44rem] opacity-35"
      />
      <img
        src={`${ASSETS}/backgrounds/section-wave-right.svg`}
        alt=""
        aria-hidden="true"
        className="pointer-events-none absolute -right-32 top-0 -z-10 h-[44rem] w-[44rem] opacity-30"
      />

      <div className="relative z-10 mx-auto flex max-w-6xl flex-col gap-8 px-5 py-14 sm:px-8 sm:py-16 lg:py-20">
      <div className="flex flex-col items-center gap-3 text-center">
        <span className="section-kicker">{t("pricing.kicker")}</span>
        <h1 className="font-display text-4xl font-bold tracking-[-0.045em] text-slate-50 sm:text-6xl">
          {t("pricing.title")}
        </h1>
        <p className="max-w-xl text-base leading-7 text-slate-400">
          {t("pricing.body")}
        </p>

        <div className="mt-4 flex items-center gap-1 rounded-2xl border border-white/10 bg-white/[0.035] p-1.5 shadow-[inset_0_1px_rgba(255,255,255,.06)] backdrop-blur-xl">
          <button
            type="button"
            onClick={() => setPeriod("monthly")}
            className={`rounded-xl px-4 py-2 text-sm font-medium transition-colors ${
              period === "monthly" ? "bg-brand-gradient text-white shadow-glow" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            {t("pricing.monthly")}
          </button>
          <button
            type="button"
            onClick={() => setPeriod("annual")}
            className={`rounded-xl px-4 py-2 text-sm font-medium transition-colors ${
              period === "annual" ? "bg-brand-gradient text-white shadow-glow" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            {t("pricing.annual")} <span className="text-emerald-400">{t("pricing.save")}</span>
          </button>
        </div>
      </div>

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
      {confirming && (
        <p className="rounded-2xl border border-brand-aqua/30 bg-brand-aqua/10 px-4 py-2 text-center text-sm text-brand-aqua backdrop-blur-xl">
          {t("pricing.payment")}
        </p>
      )}

      <div className="grid items-stretch gap-5 md:grid-cols-3 md:gap-4 lg:gap-6">
        {PLAN_ROWS.map((plan) => {
          const price = plan === "free" ? 0 : PLAN_PRICES[plan][period];
          const isCurrent = currentPlan === plan;
          const isRecommended = plan === "pro";
          const features = t(`pricing.plans.${plan}.features`, { returnObjects: true }) as string[];
          return (
            <div
              key={plan}
              className={`pricing-card relative flex flex-col gap-4 overflow-hidden rounded-3xl p-5 transition-all duration-200 sm:p-6 ${
                isRecommended
                  ? "border border-brand-purple/40 bg-[linear-gradient(145deg,rgba(60,70,145,.16),rgba(255,255,255,.025))] shadow-[inset_0_1px_rgba(255,255,255,.1),0_28px_80px_rgba(35,32,95,.25)] md:-translate-y-3"
                  : "border border-white/[0.08] bg-[linear-gradient(145deg,rgba(255,255,255,.035),rgba(255,255,255,.012))] shadow-[inset_0_1px_rgba(255,255,255,.06),0_20px_55px_rgba(0,0,0,.18)] hover:-translate-y-1 hover:border-white/[0.14]"
              }`}
            >
              {isRecommended && (
                // CSS background-image + background-size:100% 100% (not an
                // <img>) - an <img>'s own SVG content still scales by its
                // internal preserveAspectRatio regardless of the box CSS
                // gives it, which was stretching this non-uniformly into a
                // shape that no longer traced the card. A background-image
                // has no such intrinsic-aspect step: 100% 100% reliably
                // fills exactly the div's box, sized by -inset-4.
                <div
                  aria-hidden="true"
                  className="pointer-events-none absolute -inset-4 -z-10 opacity-80 blur-xl"
                  style={{
                    backgroundImage: `url(${ASSETS}/pricing/pro-glow.svg)`,
                    backgroundSize: "100% 100%",
                    backgroundRepeat: "no-repeat",
                  }}
                />
              )}
              {isRecommended && (
                // The badge SVG's visible pill occupies only the vertical
                // middle ~43% of its square viewBox - object-contain at a
                // generous square size (rather than a short, wide box)
                // keeps it legible instead of shrinking to the constrained
                // dimension.
                <img
                  src={`${ASSETS}/pricing/most-popular-badge.svg`}
                  alt={t("pricing.popular")}
                  className="absolute -top-10 right-2 h-[100px] w-[100px] object-contain"
                />
              )}
              <div>
                <h2 className="font-display text-xl font-semibold text-slate-50">{t(`pricing.plans.${plan}.name`)}</h2>
                <p className="text-sm text-slate-400">{t(`pricing.plans.${plan}.tagline`)}</p>
              </div>
              <div>
                <span className="font-display text-4xl font-bold tracking-tight text-slate-50">${price}</span>
                {plan !== "free" && (
                  <span className="text-sm text-slate-500">/{period === "monthly" ? t("pricing.month") : t("pricing.year")}</span>
                )}
              </div>
              <div className="border-t border-white/[0.08]" />
              <ul className="flex flex-1 flex-col gap-2.5 text-sm leading-5 text-slate-300">
                {features.map((f) => (
                  <li key={f} className="flex items-start gap-2">
                    <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-brand-aqua/10 text-[10px] text-brand-aqua">✓</span>
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
              <button
                type="button"
                disabled={isCurrent || checkingOut === plan}
                onClick={() => handleSelect(plan)}
                className={isRecommended ? "btn-gradient w-full" : "btn-glass w-full"}
              >
                {isCurrent
                  ? t("pricing.current")
                  : checkingOut === plan
                    ? t("pricing.starting")
                    : plan === "free"
                      ? t("pricing.startFree")
                      : t("pricing.upgrade")}
              </button>
            </div>
          );
        })}
      </div>

      <p className="text-center text-xs text-slate-600">
        {t("pricing.sandbox")}
      </p>
      </div>
    </div>
  );
}
