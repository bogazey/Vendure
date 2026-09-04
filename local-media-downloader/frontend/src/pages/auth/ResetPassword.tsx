import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import ErrorBanner from "../../components/ErrorBanner";
import LoadyLogo from "../../components/LoadyLogo";
import { ApiError, api } from "../../services/api";
import { brandLink } from "../../styles/ui";
import { authCardClass, inputClass, primaryButtonClass } from "./formStyles";

export default function ResetPassword() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get("token") || "";
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await api.resetPassword(token, password);
      setDone(true);
      setTimeout(() => navigate("/login", { replace: true }), 2000);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "This reset link is invalid or has expired.");
    } finally {
      setSubmitting(false);
    }
  };

  if (!token) {
    return (
      <div className="relative z-10 mx-auto flex max-w-md flex-col gap-6 px-6 py-16">
        <ErrorBanner message="This reset link is missing its token." />
        <Link to="/forgot-password" className={`text-center text-sm ${brandLink}`}>
          Request a new reset link
        </Link>
      </div>
    );
  }

  return (
    <div className="relative z-10 mx-auto flex max-w-md flex-col gap-6 px-6 py-16">
      <div className="flex flex-col items-center gap-4 text-center">
        <LoadyLogo size={36} withWordmark={false} />
        <h1 className="font-display text-2xl font-bold text-slate-50">Choose a new password</h1>
      </div>

      {done ? (
        <div className={authCardClass}>
          <p className="text-sm text-emerald-300">Password updated. Redirecting to sign in…</p>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className={authCardClass}>
          {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="text-slate-400">New password</span>
            <input
              type="password"
              required
              minLength={8}
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={inputClass}
            />
          </label>
          <button type="submit" disabled={submitting} className={primaryButtonClass}>
            {submitting ? "Saving…" : "Save new password"}
          </button>
        </form>
      )}
    </div>
  );
}
