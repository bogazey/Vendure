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
