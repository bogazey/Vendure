import { useState } from "react";
import { Link } from "react-router-dom";
import ErrorBanner from "../components/ErrorBanner";
import { useAuth } from "../context/AuthContext";
import { ApiError, api } from "../services/api";
import { brandLink } from "../styles/ui";
import { PLAN_LABELS } from "../types/commercial";

export default function Account() {
  const { account, refresh } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  if (!account) return null;
  const { user, subscription } = account;

  const handleResendVerification = async () => {
    setSending(true);
    setError(null);
    try {
      await api.resendVerification();
      setMessage("Verification email sent. In local development, check the backend log for the link.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not send verification email.");
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="relative z-10 mx-auto flex max-w-2xl flex-col gap-6 px-6 py-10">
      <h1 className="font-display text-xl font-bold text-slate-50">Account</h1>

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
      {message && (
        <p className="rounded-2xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-2 text-sm text-emerald-300 backdrop-blur-xl">
          {message}
        </p>
      )}

      <section className="glass-panel flex flex-col gap-3 p-5">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">Profile</h2>
        <div className="flex items-center justify-between text-sm">
          <span className="text-slate-400">Email</span>
          <span className="text-slate-100">{user.email}</span>
        </div>
        <div className="flex items-center justify-between text-sm">
          <span className="text-slate-400">Plan</span>
          <span className="rounded-full bg-brand-gradient px-2.5 py-0.5 text-xs font-semibold text-white shadow-glow">
            {PLAN_LABELS[subscription.plan]}
          </span>
        </div>
        <div className="flex items-center justify-between text-sm">
          <span className="text-slate-400">Email verification</span>
          {user.email_verified ? (
            <span className="text-emerald-400">Verified</span>
          ) : (
            <button
              type="button"
              onClick={handleResendVerification}
              disabled={sending}
              className={`text-xs ${brandLink} underline decoration-dotted underline-offset-2 disabled:opacity-60`}
            >
              {sending ? "Sending…" : "Not verified · resend email"}
            </button>
          )}
        </div>
        <div className="flex items-center justify-between text-sm">
          <span className="text-slate-400">Member since</span>
          <span className="text-slate-300">{new Date(user.created_at).toLocaleDateString()}</span>
        </div>
      </section>

      <section className="grid gap-3 sm:grid-cols-2">
        <Link
          to="/billing"
          className="glass-panel flex flex-col gap-1 p-5 transition-colors hover:border-white/20"
        >
          <h3 className="text-sm font-semibold text-slate-50">Billing</h3>
          <p className="text-xs text-slate-500">Plan, renewal date, and payment management.</p>
        </Link>
        <Link
          to="/usage"
          className="glass-panel flex flex-col gap-1 p-5 transition-colors hover:border-white/20"
        >
          <h3 className="text-sm font-semibold text-slate-50">Usage</h3>
          <p className="text-xs text-slate-500">Credits and downloads remaining this period.</p>
        </Link>
      </section>

      <button
        type="button"
        onClick={() => refresh()}
        className="self-start text-xs text-slate-500 underline decoration-dotted underline-offset-2 hover:text-slate-300"
      >
        Refresh account data
      </button>
    </div>
  );
}
