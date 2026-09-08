import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import ErrorBanner from "../../components/ErrorBanner";
import LoadyLogo from "../../components/LoadyLogo";
import { useAuth } from "../../context/AuthContext";
import { ApiError, api } from "../../services/api";
import { track } from "../../lib/analytics";
import { useNoindex } from "../../seo/useNoindex";
import { brandLink } from "../../styles/ui";
import { authCardClass } from "./formStyles";

export default function VerifyEmail() {
  const { t } = useTranslation();
  useNoindex();
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
        track("verification_completed");
        refresh();
      })
      .catch((err) => {
        setStatus("error");
        setError(err instanceof ApiError ? err.message : t("auth.verifyError"));
      });
  }, [token, refresh, t]);

  return (
    <div className="auth-page relative z-10 mx-auto flex max-w-md flex-col gap-6 px-6 py-14 sm:py-16">
      <div className="flex flex-col items-center gap-4 text-center">
        <LoadyLogo size={36} withWordmark={false} />
        <h1 className="font-display text-2xl font-bold text-slate-50">{t("auth.verifyTitle")}</h1>
      </div>
      <div className={authCardClass}>
        {status === "verifying" && <p className="text-sm text-slate-400">{t("auth.verifyChecking")}</p>}
        {status === "done" && <p className="text-sm text-emerald-300">{t("auth.verifySuccess")}</p>}
        {status === "error" && <ErrorBanner message={error || t("auth.verifyError")} />}
        <Link to="/account" className={`text-center text-sm ${brandLink}`}>
          {t("auth.goAccount")}
        </Link>
      </div>
    </div>
  );
}
