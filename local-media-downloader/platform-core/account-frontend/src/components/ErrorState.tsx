import { useTranslation } from "react-i18next";
import { ApiError } from "../services/api";

export default function ErrorState({ error }: { error: unknown }) {
  const { t } = useTranslation();
  if (error instanceof ApiError && error.status === 401) {
    return (
      <div className="glass-panel flex flex-col items-center gap-2 p-10 text-center">
        <h2 className="font-display text-lg font-semibold text-slate-50">{t("forbidden.heading")}</h2>
        <p className="text-sm text-slate-400">{t("forbidden.body")}</p>
      </div>
    );
  }
  return (
    <div className="glass-panel p-6 text-sm text-red-300">
      {error instanceof Error ? error.message : t("common.error")}
    </div>
  );
}
