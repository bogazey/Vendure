import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import ErrorBanner from "../../components/ErrorBanner";
import LoadyLogo from "../../components/LoadyLogo";
import { useAuth } from "../../context/AuthContext";
import { ApiError } from "../../services/api";
import { useNoindex } from "../../seo/useNoindex";
import { authCardClass, inputClass, primaryButtonClass } from "./formStyles";

export default function Signup() {
  const { t } = useTranslation();
  useNoindex();
  const { signup } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Carried from the hero URL input on Landing, if that's how someone
  // arrived here - picked up again by Dashboard to auto-analyze it, so
  // pasting a link before signing up isn't wasted work.
  const initialUrl = (location.state as { initialUrl?: string } | null)?.initialUrl;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await signup(email, password);
      navigate("/dashboard", { replace: true, state: initialUrl ? { initialUrl } : undefined });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("auth.signupError"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="auth-page relative z-10 mx-auto flex max-w-md flex-col gap-6 px-6 py-14 sm:py-16">
      <div className="flex flex-col items-center gap-4 text-center">
        <LoadyLogo size={36} withWordmark={false} />
        <div>
          <h1 className="font-display text-2xl font-bold text-slate-50">{t("auth.signupTitle")}</h1>
          <p className="mt-1 text-sm text-slate-400">{t("auth.signupBody")}</p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className={authCardClass}>
        {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
        {initialUrl && (
          <p className="truncate rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-xs text-slate-400">
            {t("auth.continuing")} <span className="text-slate-200" dir="ltr">{initialUrl}</span>
          </p>
        )}

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
          <span className="text-slate-400">{t("auth.password")}</span>
          <input
            type="password"
            required
            minLength={8}
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={inputClass}
          />
          <span className="text-xs text-slate-500">{t("auth.passwordHelp")}</span>
        </label>

        <button type="submit" disabled={submitting} className={primaryButtonClass}>
          {submitting ? t("auth.creating") : t("auth.create")}
        </button>

        <p className="text-center text-xs text-slate-500">
          {t("auth.hasAccount")}{" "}
          <Link
            to="/login"
            state={initialUrl ? { initialUrl } : undefined}
            className="text-slate-300 hover:text-slate-100"
          >
            {t("auth.loginTitle")}
          </Link>
        </p>
      </form>
    </div>
  );
}
