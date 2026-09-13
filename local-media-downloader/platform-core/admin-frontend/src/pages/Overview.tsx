import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, type AdminOverviewOut } from "../services/api";
import ErrorState from "../components/ErrorState";

const TILE_KEYS = [
  ["totalUsers", "total_users"],
  ["activeUsers", "active_users"],
  ["totalProducts", "total_products"],
  ["paidEntitlements", "paid_entitlements"],
  ["giftedEntitlements", "gifted_entitlements"],
] as const;

export default function Overview() {
  const { t } = useTranslation();
  const [data, setData] = useState<AdminOverviewOut | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    api.overview().then(setData).catch(setError);
  }, []);

  if (error) return <ErrorState error={error} />;
  if (!data) return <p className="text-sm text-slate-500">{t("common.loading")}</p>;

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
        {TILE_KEYS.map(([labelKey, field]) => (
          <div key={field} className="glass-panel flex flex-col gap-1.5 p-4" data-testid={`tile-${field}`}>
            <span className="text-xs font-medium uppercase tracking-wide text-slate-500">{t(`overview.${labelKey}`)}</span>
            <span className="font-display text-2xl font-bold tracking-tight text-slate-50">{data[field]}</span>
          </div>
        ))}
      </div>
      {!data.revenue_available && (
        <p className="glass-panel p-4 text-xs text-slate-500">{data.revenue_note || t("overview.revenueNote")}</p>
      )}
    </div>
  );
}
