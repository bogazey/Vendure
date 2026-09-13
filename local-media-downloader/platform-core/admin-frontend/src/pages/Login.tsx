import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function Login() {
  const { t } = useTranslation();
  const { user, loading, login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!loading && user) return <Navigate to="/" replace />;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(email, password);
      navigate("/", { replace: true });
    } catch {
      setError(t("login.error"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="bg-aurora flex min-h-screen items-center justify-center px-4">
      <form onSubmit={handleSubmit} className="glass-panel w-full max-w-sm p-8">
        <h1 className="font-display text-xl font-bold text-slate-50">
          <span className="bg-brand-gradient bg-clip-text text-transparent">{t("login.heading")}</span>
        </h1>
        <p className="mt-1 text-sm text-slate-400">{t("login.subheading")}</p>

        <label className="mt-6 block text-xs font-medium text-slate-400" htmlFor="email">
          {t("common.email")}
        </label>
        <input
          id="email"
          type="email"
          required
          autoComplete="username"
          className="input-glass mt-1"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />

        <label className="mt-4 block text-xs font-medium text-slate-400" htmlFor="password">
          {t("common.password")}
        </label>
        <input
          id="password"
          type="password"
          required
          autoComplete="current-password"
          className="input-glass mt-1"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        {error && <p className="mt-3 text-sm text-red-400">{error}</p>}

        <button type="submit" disabled={busy} className="btn-gradient mt-6 w-full">
          {t("login.submit")}
        </button>
      </form>
    </div>
  );
}
