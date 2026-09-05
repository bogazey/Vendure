import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import ErrorBanner from "../components/ErrorBanner";
import { useAuth } from "../context/AuthContext";
import { ApiError, api } from "../services/api";
import { appPageShell, brandLink } from "../styles/ui";

export default function Account() {
  const { t } = useTranslation();
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
      setMessage(t("accountPage.sent"));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("accountPage.sendError"));
    } finally {
      setSending(false);
    }
  };

  return (
    <div className={appPageShell}>
      <h1 className="font-display text-xl font-bold text-slate-50">{t("app.accountTitle")}</h1>

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
      {message && (
        <p className="rounded-2xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-2 text-sm text-emerald-300 backdrop-blur-xl">
          {message}
        </p>
      )}

      <section className="glass-panel flex flex-col gap-3 p-5">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">{t("app.profile")}</h2>
        <div className="flex items-center justify-between text-sm">
          <span className="text-slate-400">{t("auth.email")}</span>
          <span className="text-slate-100" dir="ltr">{user.email}</span>
        </div>
        <div className="flex items-center justify-between text-sm">
          <span className="text-slate-400">{t("app.plan")}</span>
          <span className="rounded-full bg-brand-gradient px-2.5 py-0.5 text-xs font-semibold text-white shadow-glow">
            {t(`pricing.plans.${subscription.plan}.name`)}
          </span>
        </div>
        <div className="flex items-center justify-between text-sm">
          <span className="text-slate-400">{t("accountPage.verification")}</span>
          {user.email_verified ? (
            <span className="text-emerald-400">{t("accountPage.verified")}</span>
          ) : (
            <button
              type="button"
              onClick={handleResendVerification}
              disabled={sending}
              className={`text-xs ${brandLink} underline decoration-dotted underline-offset-2 disabled:opacity-60`}
            >
              {sending ? t("accountPage.sending") : t("accountPage.resend")}
            </button>
          )}
        </div>
        <div className="flex items-center justify-between text-sm">
          <span className="text-slate-400">{t("accountPage.memberSince")}</span>
          <span className="text-slate-300">{new Date(user.created_at).toLocaleDateString()}</span>
        </div>
      </section>

      <section className="grid gap-3 sm:grid-cols-2">
        <Link
          to="/billing"
          className="glass-panel flex flex-col gap-1 p-5 transition-colors hover:border-white/20"
        >
          <h3 className="text-sm font-semibold text-slate-50">{t("app.billingTitle")}</h3>
          <p className="text-xs text-slate-500">{t("accountPage.billingBody")}</p>
        </Link>
        <Link
          to="/usage"
          className="glass-panel flex flex-col gap-1 p-5 transition-colors hover:border-white/20"
        >
          <h3 className="text-sm font-semibold text-slate-50">{t("app.usage")}</h3>
          <p className="text-xs text-slate-500">{t("accountPage.usageBody")}</p>
        </Link>
      </section>

      <button
        type="button"
        onClick={() => refresh()}
        className="self-start text-xs text-slate-500 underline decoration-dotted underline-offset-2 hover:text-slate-300"
      >
        {t("accountPage.refresh")}
      </button>
    </div>
  );
}
