import { useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import ErrorBanner from "../../components/ErrorBanner";
import LoadyLogo from "../../components/LoadyLogo";
import { ApiError, api } from "../../services/api";
import { brandLink } from "../../styles/ui";
import { authCardClass, inputClass, primaryButtonClass } from "./formStyles";

export default function ForgotPassword() {
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
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="relative z-10 mx-auto flex max-w-md flex-col gap-6 px-6 py-16">
      <div className="flex flex-col items-center gap-4 text-center">
        <LoadyLogo size={36} withWordmark={false} />
        <div>
          <h1 className="font-display text-2xl font-bold text-slate-50">Reset your password</h1>
          <p className="mt-1 text-sm text-slate-400">We'll email you a link to choose a new one.</p>
        </div>
      </div>

      {sent ? (
        <div className={authCardClass}>
          <p className="text-sm text-slate-300">
            If an account exists for <strong className="text-slate-100">{email}</strong>, a reset link is on its way.
            In local development, check the backend log for the link.
          </p>
          <Link to="/login" className={`text-sm ${brandLink}`}>
            Back to sign in
          </Link>
        </div>
      ) : (
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
          <button type="submit" disabled={submitting} className={primaryButtonClass}>
            {submitting ? "Sending…" : "Send reset link"}
          </button>
          <p className="text-center text-xs text-slate-500">
            <Link to="/login" className="hover:text-slate-300">
              Back to sign in
            </Link>
          </p>
        </form>
      )}
    </div>
  );
}
