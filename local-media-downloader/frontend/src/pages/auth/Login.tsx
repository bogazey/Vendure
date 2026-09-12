import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import ErrorBanner from "../../components/ErrorBanner";
import LoadyLogo from "../../components/LoadyLogo";
import { useAuth } from "../../context/AuthContext";
import { ApiError } from "../../services/api";
import { useNoindex } from "../../seo/useNoindex";
import { inputClass, authCardClass, primaryButtonClass } from "./formStyles";

export default function Login() {
  const { t } = useTranslation();
  useNoindex();
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const state = location.state as { from?: { pathname: string; search: string }; initialUrl?: string } | null;
  const from = state?.from;
  const initialUrl = state?.initialUrl;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(email, password, rememberMe);
      const destination = from ? `${from.pathname}${from.search}` : "/dashboard";
      navigate(destination, { replace: true, state: initialUrl ? { initialUrl } : undefined });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("auth.loginError"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="auth-page relative z-10 mx-auto flex max-w-md flex-col gap-6 px-6 py-14 sm:py-16">
      <div className="flex flex-col items-center gap-4 text-center">
        <LoadyLogo size={36} withWordmark={false} />
        <div>
          <h1 className="font-display text-2xl font-bold text-slate-50">{t("auth.loginTitle")}</h1>
          <p className="mt-1 text-sm text-slate-400">{t("auth.welcome")}</p>
        </div>
      </div>

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

        <label className="flex flex-col gap-1.5 text-sm">
          <div className="flex items-center justify-between">
            <span className="text-slate-400">{t("auth.password")}</span>
            <Link to="/forgot-password" className="text-xs text-brand-aqua transition-colors hover:text-brand-blue">
              {t("auth.forgot")}
            </Link>
          </div>
          <input
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={inputClass}
          />
        </label>

        <label className="flex items-center gap-2 text-sm text-slate-400">
          <input
            type="checkbox"
            checked={rememberMe}
            onChange={(e) => setRememberMe(e.target.checked)}
            className="h-4 w-4 shrink-0 rounded border-white/20 bg-transparent accent-brand-aqua"
          />
          <span>{t("auth.rememberMe")}</span>
        </label>

        <button type="submit" disabled={submitting} className={primaryButtonClass}>
          {submitting ? t("auth.signingIn") : t("auth.loginTitle")}
        </button>

        <p className="text-center text-xs text-slate-500">
          {t("auth.noAccount")}{" "}
          <Link
            to="/signup"
            state={initialUrl ? { initialUrl } : undefined}
            className="text-brand-aqua transition-colors hover:text-brand-blue"
          >
            {t("auth.createOne")}
          </Link>
        </p>
      </form>
    </div>
  );
}
