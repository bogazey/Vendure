import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { billingEventsApi } from "../services/api";
import ErrorState from "../components/ErrorState";

export default function BillingEvents() {
  const { t } = useTranslation();
  const [events, setEvents] = useState<Awaited<ReturnType<typeof billingEventsApi.list>>>([]);
  const [error, setError] = useState<unknown>(null);

  const load = () => {
    billingEventsApi.list().then(setEvents).catch(setError);
  };
  useEffect(load, []);

  if (error) return <ErrorState error={error} />;

  return (
    <div className="glass-panel overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-surface-border text-xs uppercase text-slate-500">
            <th className="px-4 py-3">{t("billingEvents.provider")}</th>
            <th className="px-4 py-3">{t("billingEvents.eventType")}</th>
            <th className="px-4 py-3">{t("common.status")}</th>
            <th className="px-4 py-3">{t("billingEvents.received")}</th>
            <th className="px-4 py-3" />
          </tr>
        </thead>
        <tbody>
          {events.map((e) => (
            <tr key={e.id} className="border-b border-surface-border/60 text-slate-300">
              <td className="px-4 py-3">{e.provider}</td>
              <td className="px-4 py-3 font-mono text-xs">{e.event_type}</td>
              <td className="px-4 py-3">
                <span className={`rounded-full px-2 py-0.5 text-xs ${e.status === "failed" ? "bg-red-500/15 text-red-300" : e.status === "processed" ? "bg-emerald-500/15 text-emerald-300" : "bg-white/5 text-slate-400"}`}>
                  {e.status}
                </span>
              </td>
              <td className="px-4 py-3 text-xs">{new Date(e.received_at).toLocaleString()}</td>
              <td className="px-4 py-3">
                {e.status === "failed" && (
                  <button type="button" className="btn-glass !px-2 !py-1 text-xs" onClick={() => billingEventsApi.replay(e.id).then(load)}>
                    {t("billingEvents.replay")}
                  </button>
                )}
              </td>
            </tr>
          ))}
          {events.length === 0 && <tr><td colSpan={5} className="px-4 py-6 text-center text-slate-500">{t("billingEvents.empty")}</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
