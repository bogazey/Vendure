import type { ReactElement } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useTranslation } from "react-i18next";

export default function ProtectedRoute({ children }: { children: ReactElement }) {
  const { t } = useTranslation();
  const { account, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return <div className="mx-auto max-w-3xl px-6 py-10 text-sm text-slate-500">{t("app.loading")}</div>;
  }
  if (!account) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  return children;
}

/** Loading-gate only, no auth requirement - the downloader itself
 * (Dashboard) is open to anonymous guests with their own small allowance,
 * see guest_service.py on the backend. Keeps the same "wait for /api/
 * account before rendering" behavior as ProtectedRoute so ad-eligibility/
 * account-dependent UI doesn't flash between guest and signed-in states. */
export function GuestAllowedRoute({ children }: { children: ReactElement }) {
  const { t } = useTranslation();
  const { loading } = useAuth();

  if (loading) {
    return <div className="mx-auto max-w-3xl px-6 py-10 text-sm text-slate-500">{t("app.loading")}</div>;
  }
  return children;
}

export function AdminRoute({ children }: { children: ReactElement }) {
  const { t } = useTranslation();
  const { account, loading } = useAuth();

  if (loading) {
    return <div className="mx-auto max-w-3xl px-6 py-10 text-sm text-slate-500">{t("app.loading")}</div>;
  }
  if (!account || account.user.role !== "admin") {
    return <Navigate to="/dashboard" replace />;
  }
  return children;
}
