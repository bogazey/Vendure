import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import ErrorBanner from "../../components/ErrorBanner";
import { useAuth } from "../../context/AuthContext";
import { ApiError, api } from "../../services/api";
import { authCardClass } from "./formStyles";

export default function VerifyEmail() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") || "";
  const { refresh } = useAuth();
  const [status, setStatus] = useState<"verifying" | "done" | "error">(token ? "verifying" : "error");
  const [error, setError] = useState<string | null>(null);
  const ran = useRef(false);

  useEffect(() => {
    if (!token || ran.current) return;
    ran.current = true;
    api
      .verifyEmail(token)
      .then(() => {
        setStatus("done");
        refresh();
      })
      .catch((err) => {
        setStatus("error");
        setError(err instanceof ApiError ? err.message : "This verification link is invalid or has expired.");
      });
  }, [token, refresh]);

  return (
    <div className="mx-auto flex max-w-md flex-col gap-6 px-6 py-16">
      <div className="text-center">
        <h1 className="text-2xl font-bold text-slate-50">Verify your email</h1>
      </div>
      <div className={authCardClass}>
        {status === "verifying" && <p className="text-sm text-slate-400">Verifying…</p>}
        {status === "done" && <p className="text-sm text-emerald-300">Your email is verified.</p>}
        {status === "error" && <ErrorBanner message={error || "This verification link is invalid or has expired."} />}
        <Link to="/account" className="text-center text-sm text-indigo-400 hover:text-indigo-300">
          Go to Account
        </Link>
      </div>
    </div>
  );
}
