import { useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import ErrorBanner from "../../components/ErrorBanner";
import LoadyLogo from "../../components/LoadyLogo";
import { ApiError, api } from "../../services/api";
import { useNoindex } from "../../seo/useNoindex";
import { brandLink } from "../../styles/ui";
import { authCardClass, inputClass, primaryButtonClass } from "./formStyles";

export default function ForgotPassword() {
  const { t } = useTranslation();
  useNoindex();
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await api.forgotPassword(email);
      // Always show success, whether or not the email exists - never reveal
      // account existence via this endpoint's response.
      setSent(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("auth.resetGenericError"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="auth-page relative z-10 mx-auto flex max-w-md flex-col gap-6 px-6 py-14 sm:py-16">
      <div className="flex flex-col items-center gap-4 text-center">
        <LoadyLogo size={36} withWordmark={false} />
        <div>
          <h1 className="font-display text-2xl font-bold text-slate-50">{t("auth.resetTitle")}</h1>
          <p className="mt-1 text-sm text-slate-400">{t("auth.resetBody")}</p>
        </div>
      </div>

      {sent ? (
        <div className={authCardClass}>
          <p className="text-sm text-slate-300">
            {t("auth.sent", { email })}
          </p>
          <Link to="/login" className={`text-sm ${brandLink}`}>
            {t("auth.backLogin")}
          </Link>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className={authCardClass}>
          {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="text-slate-400">{t("auth.email")}</span>
            <input
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={inputClass}
              dir="ltr"
            />
          </label>
          <button type="submit" disabled={submitting} className={primaryButtonClass}>
            {submitting ? t("auth.sending") : t("auth.send")}
          </button>
          <p className="text-center text-xs text-slate-500">
            <Link to="/login" className="hover:text-slate-300">
              {t("auth.backLogin")}
            </Link>
          </p>
        </form>
      )}
    </div>
  );
}
