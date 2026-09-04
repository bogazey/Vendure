import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import ErrorBanner from "../../components/ErrorBanner";
import { useAuth } from "../../context/AuthContext";
import { ApiError } from "../../services/api";
import { authCardClass, inputClass, primaryButtonClass } from "./formStyles";

export default function Signup() {
  const { signup } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await signup(email, password);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create your account.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto flex max-w-md flex-col gap-6 px-6 py-16">
      <div className="text-center">
        <h1 className="text-2xl font-bold text-slate-50">Create your account</h1>
        <p className="mt-1 text-sm text-slate-500">Free plan · 5 downloads a day · no card required.</p>
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
            minLength={8}
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={inputClass}
          />
          <span className="text-xs text-slate-500">At least 8 characters, with a mix of letters and numbers/symbols.</span>
        </label>

        <button type="submit" disabled={submitting} className={primaryButtonClass}>
          {submitting ? "Creating account…" : "Create account"}
        </button>

        <p className="text-center text-xs text-slate-500">
          Already have an account?{" "}
          <Link to="/login" className="text-slate-300 hover:text-slate-100">
            Sign in
          </Link>
        </p>
      </form>
    </div>
  );
}
