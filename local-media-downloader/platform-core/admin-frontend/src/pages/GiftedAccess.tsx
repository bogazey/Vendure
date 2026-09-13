import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, type GiftedAccessRow } from "../services/api";
import ErrorState from "../components/ErrorState";

export default function GiftedAccess() {
  const { t } = useTranslation();
  const [rows, setRows] = useState<GiftedAccessRow[]>([]);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    api.listGiftedAccess().then(setRows).catch(setError);
  }, []);

  if (error) return <ErrorState error={error} />;

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h2 className="font-display text-lg font-semibold text-slate-50">{t("giftedAccess.heading")}</h2>
        <p className="text-sm text-slate-500">{t("giftedAccess.subheading")}</p>
      </div>
      <div className="glass-panel overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-surface-border text-xs uppercase text-slate-500">
              <th className="px-4 py-3">{t("giftedAccess.user")}</th>
              <th className="px-4 py-3">{t("giftedAccess.product")}</th>
              <th className="px-4 py-3">{t("giftedAccess.plan")}</th>
              <th className="px-4 py-3">{t("entitlements.source")}</th>
              <th className="px-4 py-3">{t("giftedAccess.grantedBy")}</th>
              <th className="px-4 py-3">{t("giftedAccess.reason")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-surface-border/60 text-slate-300">
                <td className="px-4 py-3">{r.user_email}</td>
                <td className="px-4 py-3 font-mono text-xs">{r.product_id}</td>
                <td className="px-4 py-3">{r.plan_slug}</td>
                <td className="px-4 py-3">
                  <span className="rounded-full bg-brand-aqua/15 px-2 py-0.5 text-xs text-brand-aqua">{r.source}</span>
                </td>
                <td className="px-4 py-3">{r.granted_by_email ?? "—"}</td>
                <td className="px-4 py-3 text-slate-500">{r.reason ?? "—"}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-slate-600">
                  {t("giftedAccess.empty")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
