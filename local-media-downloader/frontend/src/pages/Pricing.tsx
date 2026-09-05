import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import ErrorBanner from "../components/ErrorBanner";
import { useAuth } from "../context/AuthContext";
import { track } from "../lib/analytics";
import { openPaddleCheckout } from "../lib/paddle";
import { ApiError, api } from "../services/api";
import type { BillingPeriod, Plan } from "../types/commercial";
import { PLAN_PRICES } from "../types/commercial";

interface PlanRow {
  plan: Plan;
  name: string;
  tagline: string;
  features: string[];
}

const PLAN_ROWS: PlanRow[] = [
  {
    plan: "free",
    name: "Free",
    tagline: "Try it out",
    features: [
      "5 downloads a day",
      "Up to 720p video",
      "Compatibility MP4 only",
      "Basic MP3 audio",
      "Standard queue priority",
    ],
  },
  {
    plan: "pro",
    name: "Pro",
    tagline: "For frequent use",
    features: [
      "150 credits a month",
      "Up to 4K video",
      "Original container or Compatibility MP4",
      "MP3, M4A, and advanced formats",
      "Clip-range downloads",
      "Browser cookie downloads",
      "No ads · priority queue",
      "Batch downloads",
    ],
  },
  {
    plan: "creator",
    name: "Creator",
    tagline: "For creators",
    features: [
      "500 credits a month",
      "Everything in Pro",
      "Highest queue priority",
      "Early access to creator tools",
    ],
  },
];

export default function Pricing() {
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
      setError(err instanceof ApiError ? err.message : "Could not start checkout.");
    } finally {
      setCheckingOut(null);
    }
  };

  const currentPlan = account?.subscription.plan;

  return (
    <div className="relative z-10 mx-auto flex max-w-5xl flex-col gap-10 px-6 py-14">
      <div className="flex flex-col items-center gap-3 text-center">
        <h1 className="font-display text-4xl font-bold tracking-tight text-slate-50 sm:text-5xl">
          Simple, transparent pricing
        </h1>
        <p className="max-w-xl text-sm text-slate-400">
          Start free. Upgrade when you need higher quality, more downloads, or creator tools.
        </p>

        <div className="mt-2 flex items-center gap-1 rounded-full border border-white/10 bg-white/[0.03] p-1 backdrop-blur-xl">
          <button
            type="button"
            onClick={() => setPeriod("monthly")}
            className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition-colors ${
              period === "monthly" ? "bg-brand-gradient text-white shadow-glow" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Monthly
          </button>
          <button
            type="button"
            onClick={() => setPeriod("annual")}
            className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition-colors ${
              period === "annual" ? "bg-brand-gradient text-white shadow-glow" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Annual <span className="text-emerald-400">save ~18%</span>
          </button>
        </div>
      </div>

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
      {confirming && (
        <p className="rounded-2xl border border-brand-aqua/30 bg-brand-aqua/10 px-4 py-2 text-center text-sm text-brand-aqua backdrop-blur-xl">
          Payment received — confirming your upgrade…
        </p>
      )}

      <div className="grid gap-6 md:grid-cols-3">
        {PLAN_ROWS.map((row) => {
          const price = row.plan === "free" ? 0 : PLAN_PRICES[row.plan][period];
          const isCurrent = currentPlan === row.plan;
          const isRecommended = row.plan === "pro";
          return (
            <div
              key={row.plan}
              className={`relative flex flex-col gap-5 rounded-2xl p-6 transition-transform duration-200 ${
                isRecommended
                  ? "gradient-border border border-transparent bg-white/[0.035] shadow-glow md:-translate-y-2"
                  : "border border-white/[0.08] bg-white/[0.02] shadow-[inset_0_1px_0_0_rgba(255,255,255,0.05)]"
              }`}
            >
              {isRecommended && (
                <span className="absolute -top-3 right-6 rounded-full bg-brand-gradient px-3 py-1 text-[11px] font-semibold uppercase tracking-wide text-white shadow-glow">
                  Most popular
                </span>
              )}
              <div>
                <h2 className="font-display text-lg font-semibold text-slate-50">{row.name}</h2>
                <p className="text-sm text-slate-400">{row.tagline}</p>
              </div>
              <div>
                <span className="font-display text-3xl font-bold text-slate-50">${price}</span>
                {row.plan !== "free" && (
                  <span className="text-sm text-slate-500">/{period === "monthly" ? "mo" : "yr"}</span>
                )}
              </div>
              <div className="border-t border-white/[0.08]" />
              <ul className="flex flex-1 flex-col gap-2 text-sm text-slate-300">
                {row.features.map((f) => (
                  <li key={f} className="flex items-start gap-2">
                    <span className="mt-0.5 text-brand-aqua">✓</span>
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
              <button
                type="button"
                disabled={isCurrent || checkingOut === row.plan}
                onClick={() => handleSelect(row.plan)}
                className={isRecommended ? "btn-gradient w-full" : "btn-glass w-full"}
              >
                {isCurrent
                  ? "Current plan"
                  : checkingOut === row.plan
                    ? "Starting checkout…"
                    : row.plan === "free"
                      ? "Start free"
                      : "Upgrade"}
              </button>
            </div>
          );
        })}
      </div>

      <p className="text-center text-xs text-slate-600">
        Billing runs on Paddle Sandbox in this build - no real payment is ever collected. Prices shown are the
        planned production prices.
      </p>
    </div>
  );
}
