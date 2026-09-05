import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import ErrorBanner from "../../components/ErrorBanner";
import { ApiError, api } from "../../services/api";
import type { AdminBillingEventOut } from "../../types/commercial";
import { formatDate } from "../../utils/format";
import AdminLayout from "./AdminLayout";
import { billingOutcome, billingOutcomeClass } from "./adminShared";

export default function AdminBilling() {
  const { t } = useTranslation();
  const [events, setEvents] = useState<AdminBillingEventOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .adminListBillingEvents(100)
      .then(setEvents)
      .catch((err) => setError(err instanceof ApiError ? err.message : t("admin.billing.loadError")))
      .finally(() => setLoading(false));
  }, [t]);

  return (
    <AdminLayout>
      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
      <p className="text-sm text-slate-500">{t("admin.billing.subtitle")}</p>

      <div className="glass-panel min-w-0 overflow-x-auto">
        <table className="w-full text-start text-sm">
          <thead className="bg-white/[0.03] text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2 text-start">{t("admin.billing.columnEvent")}</th>
              <th className="px-4 py-2 text-start">{t("admin.billing.columnUser")}</th>
              <th className="px-4 py-2 text-start">{t("admin.billing.columnOutcome")}</th>
              <th className="px-4 py-2 text-start">{t("admin.billing.columnWebhook")}</th>
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
            {!loading && events.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-slate-500">
                  {t("admin.billing.empty")}
                </td>
              </tr>
            )}
            {events.map((event) => {
              const outcome = billingOutcome(event.event_type);
              return (
                <tr key={event.provider_event_id} className="border-t border-white/[0.06]">
                  <td className="px-4 py-2 text-slate-200" dir="ltr">
                    {event.event_type}
                  </td>
                  <td className="px-4 py-2 text-slate-400" dir="ltr">
                    {event.user_email || event.user_id || t("admin.billing.unknownUser")}
                  </td>
                  <td className="px-4 py-2">
                    <span className={billingOutcomeClass(outcome.tone)}>{t(outcome.key)}</span>
                  </td>
                  <td className="px-4 py-2 text-slate-500">
                    {t(`admin.billing.webhookStatus.${event.status}`, { defaultValue: event.status })}
                  </td>
                  <td className="px-4 py-2 text-slate-500" dir="ltr">
                    {formatDate(event.processed_at)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </AdminLayout>
  );
}
