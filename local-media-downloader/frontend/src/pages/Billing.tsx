import { useState } from "react";
import { Link } from "react-router-dom";
import ErrorBanner from "../components/ErrorBanner";
import { useAuth } from "../context/AuthContext";
import { ApiError, api } from "../services/api";
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

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6 px-6 py-10">
      <h1 className="text-xl font-bold text-slate-50">Billing</h1>

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      <section className="flex flex-col gap-3 rounded-xl border border-surface-border bg-surface-raised p-5">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">Current plan</h2>
        <div className="flex items-center justify-between text-sm">
          <span className="text-slate-400">Plan</span>
          <span className="text-slate-100">{PLAN_LABELS[subscription.plan]}</span>
        </div>
        <div className="flex items-center justify-between text-sm">
          <span className="text-slate-400">Status</span>
          <span className="text-slate-100">{STATUS_LABEL[subscription.status] ?? subscription.status}</span>
        </div>
        {subscription.billing_period && (
          <div className="flex items-center justify-between text-sm">
            <span className="text-slate-400">Billing cadence</span>
            <span className="text-slate-100 capitalize">{subscription.billing_period}</span>
          </div>
        )}
        {subscription.current_period_end && (
          <div className="flex items-center justify-between text-sm">
            <span className="text-slate-400">{subscription.cancel_at_period_end ? "Access ends" : "Next renewal"}</span>
            <span className="text-slate-100">{new Date(subscription.current_period_end).toLocaleDateString()}</span>
          </div>
        )}
        {subscription.cancel_at_period_end && (
          <p className="text-xs text-amber-400">
            This subscription is set to cancel at the end of the current billing period.
          </p>
        )}
      </section>

      <section className="flex flex-col gap-3 rounded-xl border border-surface-border bg-surface-raised p-5">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">Usage this period</h2>
        {usage.plan === "free" ? (
          <div className="flex items-center justify-between text-sm">
            <span className="text-slate-400">Free downloads today</span>
            <span className="text-slate-100">
              {usage.daily_free_downloads_used} / {(usage.daily_free_downloads_used ?? 0) + (usage.daily_free_downloads_remaining ?? 0)}
            </span>
          </div>
        ) : (
          <div className="flex items-center justify-between text-sm">
            <span className="text-slate-400">Credits used</span>
            <span className="text-slate-100">
              {usage.credits_used} / {usage.credits_included}
            </span>
          </div>
        )}
      </section>

      <div className="flex flex-wrap gap-3">
        {isFree ? (
          <Link
            to="/pricing"
            className="rounded-md bg-indigo-500 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-400"
          >
            Upgrade plan
          </Link>
        ) : (
          <>
            <Link
              to="/pricing"
              className="rounded-md border border-surface-border px-4 py-2 text-sm font-semibold text-slate-200 hover:border-slate-500"
            >
              Change plan
            </Link>
            <button
              type="button"
              onClick={handleManageBilling}
              disabled={openingPortal}
              className="rounded-md bg-indigo-500 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-400 disabled:opacity-60"
            >
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
