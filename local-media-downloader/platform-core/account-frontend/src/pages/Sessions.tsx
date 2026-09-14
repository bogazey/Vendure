import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, type SessionOut } from "../services/api";
import ErrorState from "../components/ErrorState";

export default function Sessions() {
  const { t } = useTranslation();
  const [sessions, setSessions] = useState<SessionOut[]>([]);
  const [error, setError] = useState<unknown>(null);

  const load = () => {
    api.sessions().then(setSessions).catch(setError);
  };
  useEffect(load, []);

  const handleRevoke = async (id: string) => {
    await api.revokeSession(id);
    load();
  };

  if (error) return <ErrorState error={error} />;

  return (
    <div className="flex flex-col gap-3">
      {sessions.map((s) => (
        <div key={s.id} className="glass-panel flex items-center justify-between p-4">
          <div>
            <p className="text-sm text-slate-200">
              {s.device_label || t("sessions.unknownDevice")}
              {s.is_current && <span className="ms-2 rounded-full bg-emerald-500/15 px-2 py-0.5 text-xs text-emerald-300">{t("sessions.currentSession")}</span>}
            </p>
            <p className="text-xs text-slate-500">
              {t("sessions.lastUsed")}: {new Date(s.last_used_at).toLocaleString()}
            </p>
          </div>
          {!s.is_current && (
            <button type="button" className="btn-glass !px-3 !py-1.5 text-xs" onClick={() => handleRevoke(s.id)}>
              {t("sessions.signOut")}
            </button>
          )}
        </div>
      ))}
      {sessions.length === 0 && <p className="text-sm text-slate-500">{t("sessions.empty")}</p>}
    </div>
  );
}
