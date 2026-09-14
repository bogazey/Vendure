import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { revenueApi, type RevenueMetricsOut } from "../services/api";
import ErrorState from "../components/ErrorState";

function money(cents: number | null): string {
  if (cents === null) return "—";
  return `$${(cents / 100).toFixed(2)}`;
}

export default function Revenue() {
  const { t } = useTranslation();
  const [productId, setProductId] = useState("");
  const [metrics, setMetrics] = useState<RevenueMetricsOut | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = (pid: string) => {
    revenueApi.metrics(pid ? { product_id: pid } : {}).then(setMetrics).catch(setError);
  };
  useEffect(() => {
    // A global (no product_id) query is global-admin only - a
    // product-scoped admin must supply their own product to see anything.
  }, []);

  if (error) return <ErrorState error={error} />;

  return (
    <div className="flex flex-col gap-6">
      <div className="glass-panel flex flex-wrap items-end gap-2 p-4">
        <div>
          <label className="block text-xs text-slate-500">{t("revenue.productId")}</label>
          <input className="input-glass !w-auto" value={productId} onChange={(e) => setProductId(e.target.value)} placeholder={t("revenue.productPlaceholder") as string} />
        </div>
        <button type="button" className="btn-gradient" onClick={() => load(productId)}>
          {t("revenue.load")}
        </button>
      </div>

      {metrics && (
        <>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <MetricCard label={t("revenue.revenue")} value={money(metrics.net_revenue_cents)} />
            <MetricCard label={t("revenue.mrr")} value={money(metrics.mrr_cents)} />
            <MetricCard label={t("revenue.arr")} value={money(metrics.arr_cents)} />
            <MetricCard label={t("revenue.arpu")} value={money(metrics.arpu_cents !== null ? Math.round(metrics.arpu_cents) : null)} />
            <MetricCard label={t("revenue.paidSubscribers")} value={String(metrics.paid_subscribers)} />
            <MetricCard label={t("revenue.refunded")} value={money(metrics.refunded_cents)} />
            <MetricCard label={t("revenue.churn")} value={metrics.churn_rate !== null ? `${(metrics.churn_rate * 100).toFixed(1)}%` : "—"} />
          </div>
          {metrics.notes.length > 0 && (
            <div className="glass-panel p-4">
              <p className="mb-2 text-xs font-semibold uppercase text-slate-500">{t("revenue.notesHeading")}</p>
              <ul className="list-disc space-y-1 ps-5 text-xs text-slate-400">
                {metrics.notes.map((note, i) => (
                  <li key={i}>{note}</li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
      {!metrics && <p className="text-sm text-slate-500">{t("revenue.prompt")}</p>}
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="glass-panel p-4">
      <p className="font-display text-2xl font-bold text-slate-50">{value}</p>
      <p className="text-xs text-slate-500">{label}</p>
    </div>
  );
}
