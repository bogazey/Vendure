import { useState } from "react";
import { Link } from "react-router-dom";
import ErrorBanner from "../components/ErrorBanner";
import { useAuth } from "../context/AuthContext";
import { ApiError, api } from "../services/api";
import { appPageShell } from "../styles/ui";
import { PLAN_LABELS } from "../types/commercial";

const STATUS_LABEL: Record<string, string> = {
  none: "No active subscription",
  trialing: "Trialing",
  active: "Active",
  past_due: "Payment past due",
  paused: "Paused",
  canceled: "Canceled",
};

export default function Billing() {
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
          "Billing management isn't available yet - either this account has no billing history, or Paddle isn't configured on this server. See PADDLE_SANDBOX_TESTING.md."
        );
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not open billing management.");
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
      <h1 className="font-display text-xl font-bold text-slate-50">Billing</h1>

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      <section className="glass-panel flex flex-col gap-4 p-6">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Current plan</h2>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="rounded-full bg-brand-gradient px-3 py-1 text-sm font-semibold text-white shadow-glow">
              {PLAN_LABELS[subscription.plan]}
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
              {STATUS_LABEL[subscription.status] ?? subscription.status}
            </span>
          </div>
          {subscription.current_period_end && (
            <span className="text-sm text-slate-400">
              {subscription.cancel_at_period_end ? "Access ends " : "Renews "}
              {new Date(subscription.current_period_end).toLocaleDateString()}
            </span>
          )}
        </div>
        {subscription.billing_period && (
          <div className="flex items-center justify-between border-t border-white/[0.06] pt-3 text-sm">
            <span className="text-slate-400">Billing cadence</span>
            <span className="capitalize text-slate-200">{subscription.billing_period}</span>
          </div>
        )}
        {subscription.cancel_at_period_end && (
          <p className="rounded-xl border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
            This subscription is set to cancel at the end of the current billing period.
          </p>
        )}
      </section>

      <section className="glass-panel flex flex-col gap-3 p-6">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Usage this period</h2>
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
          {usage.plan === "free" ? "Free downloads used today" : "Credits used this billing period"}
        </p>
      </section>

      <div className="flex flex-wrap gap-3">
        {isFree ? (
          <Link to="/pricing" className="btn-gradient">
            Upgrade plan
          </Link>
        ) : (
          <>
            <Link to="/pricing" className="btn-glass">
              Change plan
            </Link>
            <button type="button" onClick={handleManageBilling} disabled={openingPortal} className="btn-gradient">
              {openingPortal ? "Opening…" : "Manage billing"}
            </button>
          </>
        )}
      </div>
      <p className="text-xs text-slate-600">
        Billing is managed entirely through Paddle's hosted checkout and customer portal - we never see or store your
        card details, and a successful upgrade only takes effect once Paddle's webhook confirms it (this can take a
        few seconds after checkout).
      </p>
    </div>
  );
}
