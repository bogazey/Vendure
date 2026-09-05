import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import ErrorBanner from "../../components/ErrorBanner";
import { ApiError, api } from "../../services/api";
import type { AdminActionLogOut } from "../../types/commercial";
import { formatDate } from "../../utils/format";
import AdminLayout from "./AdminLayout";
import { actionLabelKey } from "./adminShared";

export default function AdminActivity() {
  const { t } = useTranslation();
  const [entries, setEntries] = useState<AdminActionLogOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .adminListAuditLog({ limit: 100 })
      .then(setEntries)
      .catch((err) => setError(err instanceof ApiError ? err.message : t("admin.activity.loadError")))
      .finally(() => setLoading(false));
  }, [t]);

  return (
    <AdminLayout>
      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
      <p className="text-sm text-slate-500">{t("admin.activity.subtitle")}</p>

      <div className="glass-panel min-w-0 overflow-x-auto">
        <table className="w-full text-start text-sm">
          <thead className="bg-white/[0.03] text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2 text-start">{t("admin.activity.columnAction")}</th>
              <th className="px-4 py-2 text-start">{t("admin.activity.columnAdmin")}</th>
              <th className="px-4 py-2 text-start">{t("admin.activity.columnTarget")}</th>
              <th className="px-4 py-2 text-start">{t("admin.activity.columnDetails")}</th>
              <th className="px-4 py-2 text-start">{t("admin.billing.columnTime")}</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-slate-500">
                  {t("app.loading")}
                </td>
              </tr>
            )}
            {!loading && entries.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-slate-500">
                  {t("admin.activity.empty")}
                </td>
              </tr>
            )}
            {entries.map((entry) => (
              <tr key={entry.id} className="border-t border-white/[0.06]">
                <td className="px-4 py-2 text-slate-200">{t(actionLabelKey(entry.action))}</td>
                <td className="px-4 py-2 text-slate-400" dir="ltr">
                  {entry.admin_email || entry.admin_id}
                </td>
                <td className="px-4 py-2 text-slate-400" dir="ltr">
                  {entry.target_email || entry.target_user_id || "—"}
                </td>
                <td className="px-4 py-2 text-slate-500" dir="ltr">
                  {entry.action === "grant_credits"
                    ? `+${entry.details.credits} · ${entry.details.reason}`
                    : entry.action === "disable_account" || entry.action === "reactivate_account"
                      ? `${entry.details.previous_status} → ${entry.details.new_status}`
                      : ""}
                </td>
                <td className="px-4 py-2 text-slate-500" dir="ltr">
                  {formatDate(entry.created_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </AdminLayout>
  );
}
