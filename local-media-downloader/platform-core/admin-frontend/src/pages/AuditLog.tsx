import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, type AuditLogOut } from "../services/api";
import ErrorState from "../components/ErrorState";

export default function AuditLog() {
  const { t } = useTranslation();
  const [rows, setRows] = useState<AuditLogOut[]>([]);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    api.auditLog().then(setRows).catch(setError);
  }, []);

  if (error) return <ErrorState error={error} />;

  return (
    <div className="flex flex-col gap-4">
      <h2 className="font-display text-lg font-semibold text-slate-50">{t("audit.heading")}</h2>
      <div className="glass-panel overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-surface-border text-xs uppercase text-slate-500">
              <th className="px-4 py-3">{t("audit.when")}</th>
              <th className="px-4 py-3">{t("audit.actor")}</th>
              <th className="px-4 py-3">{t("audit.action")}</th>
              <th className="px-4 py-3">{t("audit.target")}</th>
              <th className="px-4 py-3">{t("audit.product")}</th>
              <th className="px-4 py-3">{t("audit.reason")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-surface-border/60 text-slate-300">
                <td className="whitespace-nowrap px-4 py-3 text-xs text-slate-500">{new Date(r.created_at).toLocaleString()}</td>
                <td className="px-4 py-3">{r.actor_email ?? "—"}</td>
                <td className="px-4 py-3">
                  <span className="rounded-full bg-white/5 px-2 py-0.5 text-xs">{r.action}</span>
                </td>
                <td className="px-4 py-3 font-mono text-xs">{r.target_id ?? "—"}</td>
                <td className="px-4 py-3 font-mono text-xs">{r.product_id ?? "—"}</td>
                <td className="px-4 py-3 text-slate-500">{r.reason ?? "—"}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-slate-600">
                  {t("audit.empty")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
