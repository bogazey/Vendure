import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, type ClosureRequest, type SecurityEvent } from "../services/api";
import { useNavigate } from "react-router-dom";

export default function Security() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [revokeOthers, setRevokeOthers] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [events, setEvents] = useState<SecurityEvent[]>([]);
  const [closure, setClosure] = useState<ClosureRequest | null>(null);
  const [closureReason, setClosureReason] = useState("");

  const loadEvents = () => api.mySecurityEvents().then(setEvents);
  const loadClosure = () => api.closureStatus().then(setClosure).catch(() => setClosure(null));

  useEffect(() => {
    loadEvents();
    loadClosure();
  }, []);

  const handleChangePassword = async () => {
    setError(null);
    setMessage(null);
    try {
      await api.changePassword(currentPassword, newPassword, revokeOthers);
      setMessage(t("security.passwordChanged"));
      setCurrentPassword("");
      setNewPassword("");
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    }
  };

  const handleSignOutAll = async () => {
    await api.logoutAll();
    navigate("/login", { replace: true });
  };

  const handleRequestClosure = async () => {
    const req = await api.requestClosure(closureReason || undefined);
    setClosure(req);
  };

  const handleConfirmClosure = async () => {
    if (!closure) return;
    await api.confirmClosure(closure.id);
    navigate("/login", { replace: true });
  };

  const handleCancelClosure = async () => {
    if (!closure) return;
    await api.cancelClosure(closure.id);
    setClosure(null);
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="glass-panel flex flex-col gap-3 p-6">
        <h2 className="font-display text-lg font-semibold text-slate-50">{t("security.changePasswordHeading")}</h2>
        <label className="block text-xs text-slate-500">{t("security.currentPassword")}</label>
        <input type="password" className="input-glass" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} />
        <label className="block text-xs text-slate-500">{t("security.newPassword")}</label>
        <input type="password" className="input-glass" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
        <label className="flex items-center gap-2 text-xs text-slate-300">
          <input type="checkbox" checked={revokeOthers} onChange={(e) => setRevokeOthers(e.target.checked)} />
          {t("security.revokeOthersOnChange")}
        </label>
        <button type="button" className="btn-gradient self-start !px-4 !py-1.5 text-sm" onClick={handleChangePassword} disabled={!currentPassword || !newPassword}>
          {t("security.changePassword")}
        </button>
        {message && <p className="text-sm text-emerald-300">{message}</p>}
        {error && <p className="text-sm text-red-400">{error}</p>}
      </div>

      <div className="glass-panel flex flex-col gap-3 p-6">
        <h2 className="font-display text-lg font-semibold text-slate-50">{t("security.signOutEverywhereHeading")}</h2>
        <p className="text-xs text-slate-500">{t("security.signOutEverywhereHint")}</p>
        <button type="button" className="btn-glass self-start !px-4 !py-1.5 text-sm" onClick={handleSignOutAll}>
          {t("security.signOutEverywhere")}
        </button>
      </div>

      <div>
        <h2 className="mb-3 font-display text-lg font-semibold text-slate-50">{t("security.recentActivity")}</h2>
        <div className="glass-panel divide-y divide-surface-border/60">
          {events.map((e, i) => (
            <div key={i} className="flex items-center justify-between px-4 py-3 text-sm text-slate-300">
              <span>{t(`securityEvents.${e.action}`, { defaultValue: e.action })}</span>
              <span className="text-xs text-slate-500">{new Date(e.created_at).toLocaleString()}</span>
            </div>
          ))}
          {events.length === 0 && <p className="px-4 py-6 text-center text-sm text-slate-500">{t("overview.noEvents")}</p>}
        </div>
      </div>

      <div className="glass-panel flex flex-col gap-3 border border-red-500/20 p-6">
        <h2 className="font-display text-lg font-semibold text-red-300">{t("security.closureHeading")}</h2>
        <p className="text-xs text-slate-500">{t("security.closureHint")}</p>
        {!closure || closure.status === "canceled" ? (
          <>
            <input className="input-glass" placeholder={t("security.closureReasonPlaceholder") as string} value={closureReason} onChange={(e) => setClosureReason(e.target.value)} />
            <button type="button" className="btn-glass self-start !border-red-500/40 !px-4 !py-1.5 text-sm text-red-300" onClick={handleRequestClosure}>
              {t("security.requestClosure")}
            </button>
          </>
        ) : closure.status === "requested" ? (
          <div className="flex flex-col gap-2">
            <p className="text-sm text-amber-300">{t("security.closurePendingConfirmation")}</p>
            <div className="flex gap-2">
              <button type="button" className="btn-glass !border-red-500/40 !px-4 !py-1.5 text-sm text-red-300" onClick={handleConfirmClosure}>
                {t("security.confirmClosure")}
              </button>
              <button type="button" className="btn-glass !px-4 !py-1.5 text-sm" onClick={handleCancelClosure}>
                {t("common.cancel")}
              </button>
            </div>
          </div>
        ) : (
          <p className="text-sm text-slate-400">{t("security.closureInProgress", { status: closure.status })}</p>
        )}
      </div>
    </div>
  );
}
