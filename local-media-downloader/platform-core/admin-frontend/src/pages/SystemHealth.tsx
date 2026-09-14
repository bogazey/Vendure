import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { systemHealthApi, type SystemHealthOut } from "../services/api";
import ErrorState from "../components/ErrorState";

function Badge({ ok }: { ok: boolean }) {
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs ${ok ? "bg-emerald-500/15 text-emerald-300" : "bg-red-500/15 text-red-300"}`}>
      {ok ? "OK" : "!"}
    </span>
  );
}

export default function SystemHealth() {
  const { t } = useTranslation();
  const [health, setHealth] = useState<SystemHealthOut | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    systemHealthApi.get().then(setHealth).catch(setError);
  }, []);

  if (error) return <ErrorState error={error} />;
  if (!health) return <p className="text-sm text-slate-500">{t("common.loading")}</p>;

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <div className="glass-panel flex items-center justify-between p-5">
        <span className="text-sm text-slate-300">{t("systemHealth.database")}</span>
        <Badge ok={health.database} />
      </div>
      <div className="glass-panel flex items-center justify-between p-5">
        <span className="text-sm text-slate-300">{t("systemHealth.signingKey")}</span>
        <Badge ok={health.signing_key_configured} />
      </div>
      <div className="glass-panel p-5">
        <p className="mb-2 text-sm text-slate-300">{t("systemHealth.outbox")}</p>
        <div className="flex gap-4 text-xs text-slate-400">
          <span>{t("systemHealth.pending")}: {health.outbox.pending}</span>
          <span className={health.outbox.failed > 0 ? "text-red-300" : ""}>{t("systemHealth.failed")}: {health.outbox.failed}</span>
        </div>
      </div>
      <div className="glass-panel p-5">
        <p className="mb-2 text-sm text-slate-300">{t("systemHealth.billingWebhooks")}</p>
        <div className="flex gap-4 text-xs text-slate-400">
          <span>{t("systemHealth.pending")}: {health.billing_webhooks.pending}</span>
          <span className={health.billing_webhooks.failed > 0 ? "text-red-300" : ""}>{t("systemHealth.failed")}: {health.billing_webhooks.failed}</span>
        </div>
      </div>
    </div>
  );
}
