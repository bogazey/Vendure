import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import ErrorBanner from "../../components/ErrorBanner";
import LoadyLogo from "../../components/LoadyLogo";
import { useAuth } from "../../context/AuthContext";
import { ApiError } from "../../services/api";
import { inputClass, authCardClass, primaryButtonClass } from "./formStyles";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
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
      await login(email, password);
      const destination = from ? `${from.pathname}${from.search}` : "/dashboard";
      navigate(destination, { replace: true, state: initialUrl ? { initialUrl } : undefined });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not sign in.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="relative z-10 mx-auto flex max-w-md flex-col gap-6 px-6 py-16">
      <div className="flex flex-col items-center gap-4 text-center">
        <LoadyLogo size={36} withWordmark={false} />
        <div>
          <h1 className="font-display text-2xl font-bold text-slate-50">Sign in</h1>
          <p className="mt-1 text-sm text-slate-400">Welcome back.</p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className={authCardClass}>
        {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

        <label className="flex flex-col gap-1.5 text-sm">
          <span className="text-slate-400">Email</span>
          <input
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={inputClass}
          />
        </label>

        <label className="flex flex-col gap-1.5 text-sm">
          <span className="text-slate-400">Password</span>
          <input
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={inputClass}
          />
        </label>

        <button type="submit" disabled={submitting} className={primaryButtonClass}>
          {submitting ? "Signing in…" : "Sign in"}
        </button>

        <div className="flex items-center justify-between text-xs text-slate-500">
          <Link to="/forgot-password" className="hover:text-slate-300">
            Forgot password?
          </Link>
          <Link to="/signup" state={initialUrl ? { initialUrl } : undefined} className="hover:text-slate-300">
            Create an account
          </Link>
        </div>
      </form>
    </div>
  );
}
