import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../services/api";
import { useAuth } from "../context/AuthContext";

export default function Profile() {
  const { t, i18n } = useTranslation();
  const { user, refresh } = useAuth();
  const [newEmail, setNewEmail] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleRequestChange = async () => {
    setError(null);
    setMessage(null);
    try {
      await api.requestEmailChange(newEmail);
      setMessage(t("profile.emailChangeRequested"));
      setNewEmail("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="glass-panel flex flex-col gap-4 p-6">
        <h2 className="font-display text-lg font-semibold text-slate-50">{t("profile.identityHeading")}</h2>
        <div>
          <p className="text-xs uppercase text-slate-500">{t("profile.globalId")}</p>
          <p className="font-mono text-xs text-slate-400">{user?.id}</p>
        </div>
        <div>
          <p className="text-xs uppercase text-slate-500">{t("common.email")}</p>
          <p className="text-sm text-slate-200">{user?.email}</p>
          {user?.pending_new_email && (
            <p className="mt-1 text-xs text-amber-300">
              {t("profile.pendingEmail", { email: user.pending_new_email })}
            </p>
          )}
        </div>
      </div>

      <div className="glass-panel flex flex-col gap-3 p-6">
        <h2 className="font-display text-lg font-semibold text-slate-50">{t("profile.changeEmailHeading")}</h2>
        <p className="text-xs text-slate-500">{t("profile.changeEmailHint")}</p>
        <div className="flex flex-wrap items-end gap-2">
          <input
            type="email"
            className="input-glass !w-auto"
            value={newEmail}
            onChange={(e) => setNewEmail(e.target.value)}
            placeholder="new@example.com"
          />
          <button type="button" className="btn-gradient !px-4 !py-1.5 text-sm" onClick={handleRequestChange} disabled={!newEmail}>
            {t("profile.requestChange")}
          </button>
        </div>
        {message && <p className="text-sm text-emerald-300">{message}</p>}
        {error && <p className="text-sm text-red-400">{error}</p>}
      </div>

      <div className="glass-panel flex flex-col gap-3 p-6">
        <h2 className="font-display text-lg font-semibold text-slate-50">{t("profile.languageHeading")}</h2>
        <div className="flex gap-2">
          <button
            type="button"
            className={`btn-glass !px-4 !py-1.5 text-sm ${i18n.language === "en" ? "!border-brand-blue" : ""}`}
            onClick={() => i18n.changeLanguage("en")}
          >
            English
          </button>
          <button
            type="button"
            className={`btn-glass !px-4 !py-1.5 text-sm ${i18n.language === "ar" ? "!border-brand-blue" : ""}`}
            onClick={() => i18n.changeLanguage("ar")}
          >
            العربية
          </button>
        </div>
      </div>
    </div>
  );
}
