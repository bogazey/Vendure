import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import ErrorBanner from "../../components/ErrorBanner";
import { ApiError, api } from "../../services/api";
import { statTile } from "../../styles/ui";
import type { AdminAdPlacementOut } from "../../types/commercial";
import AdminLayout from "./AdminLayout";
import { adPlacementDescriptionKey, adPlacementLabelKey } from "./adminShared";

export default function AdminAds() {
  const { t } = useTranslation();
  const [placements, setPlacements] = useState<AdminAdPlacementOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [editTarget, setEditTarget] = useState<AdminAdPlacementOut | null>(null);
  const [provider, setProvider] = useState("");
  const [slotId, setSlotId] = useState("");
  const [saving, setSaving] = useState(false);

  const load = () => {
    setLoading(true);
    api
      .adminListAdPlacements()
      .then(setPlacements)
      .catch((err) => setError(err instanceof ApiError ? err.message : t("admin.ads.loadError")))
      .finally(() => setLoading(false));
  };

  useEffect(load, [t]);

  const applyUpdate = (updated: AdminAdPlacementOut) => {
    setPlacements((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
  };

  const handleToggleEnabled = async (placement: AdminAdPlacementOut) => {
    try {
      const updated = await api.adminUpdateAdPlacement(placement.id, { enabled: !placement.enabled });
      applyUpdate(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("admin.ads.updateError"));
    }
  };

  const openEdit = (placement: AdminAdPlacementOut) => {
    setEditTarget(placement);
    setProvider(placement.provider ?? "");
    setSlotId(placement.public_slot_id ?? "");
  };

  const handleSaveConfig = async () => {
    if (!editTarget) return;
    setSaving(true);
    try {
      const updated = await api.adminUpdateAdPlacement(editTarget.id, {
        provider: provider.trim() || null,
        public_slot_id: slotId.trim() || null,
      });
      applyUpdate(updated);
      setEditTarget(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("admin.ads.updateError"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <AdminLayout>
      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
      <p className="text-sm text-slate-500">{t("admin.ads.subtitle")}</p>

      {loading ? (
        <p className="text-sm text-slate-500">{t("app.loading")}</p>
      ) : (
        <div className="flex flex-col gap-3">
          {placements.map((placement) => (
            <div key={placement.id} className={`${statTile} sm:flex-row sm:items-center sm:justify-between`}>
              <div className="flex min-w-0 flex-col gap-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-display text-sm font-semibold text-slate-50">{t(adPlacementLabelKey(placement.id))}</span>
                  <span className="rounded-full bg-white/[0.06] px-2 py-0.5 text-[10px] uppercase tracking-wide text-slate-500" dir="ltr">
                    {placement.id}
                  </span>
                  <span className={placement.enabled ? "text-xs font-medium text-emerald-400" : "text-xs font-medium text-slate-500"}>
                    {placement.enabled ? t("admin.ads.enabled") : t("admin.ads.disabled")}
                  </span>
                </div>
                <p className="text-sm text-slate-400">{t(adPlacementDescriptionKey(placement.id))}</p>
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500" dir="ltr">
                  <span>{t("admin.ads.provider")}: {placement.provider || t("admin.ads.notConfigured")}</span>
                  <span>{t("admin.ads.slotId")}: {placement.public_slot_id || t("admin.ads.notConfigured")}</span>
                </div>
              </div>
              <div className="flex shrink-0 gap-2">
                <button type="button" onClick={() => openEdit(placement)} className="btn-glass px-3 py-1.5 text-xs">
                  {t("admin.ads.configure")}
                </button>
                <button
                  type="button"
                  onClick={() => handleToggleEnabled(placement)}
                  className={`px-3 py-1.5 text-xs ${placement.enabled ? "btn-glass" : "btn-gradient"}`}
                >
                  {placement.enabled ? t("admin.ads.disable") : t("admin.ads.enable")}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {editTarget && (
        <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/60 px-4 backdrop-blur-sm">
          <div className="glass-panel-raised flex w-full max-w-sm flex-col gap-4 p-5">
            <h2 className="font-display text-sm font-semibold text-slate-50">
              {t("admin.ads.configureTitle", { placement: t(adPlacementLabelKey(editTarget.id)) })}
            </h2>
            <label className="flex flex-col gap-1.5 text-sm">
              <span className="text-slate-400">{t("admin.ads.provider")}</span>
              <input
                type="text"
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
                placeholder={t("admin.ads.providerPlaceholder")}
                className="input-glass py-2"
                dir="ltr"
              />
            </label>
            <label className="flex flex-col gap-1.5 text-sm">
              <span className="text-slate-400">{t("admin.ads.slotId")}</span>
              <input
                type="text"
                value={slotId}
                onChange={(e) => setSlotId(e.target.value)}
                placeholder={t("admin.ads.slotIdPlaceholder")}
                className="input-glass py-2"
                dir="ltr"
              />
            </label>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setEditTarget(null)} className="btn-glass px-3 py-1.5">
                {t("common.cancel")}
              </button>
              <button type="button" onClick={handleSaveConfig} disabled={saving} className="btn-gradient px-3 py-1.5 disabled:opacity-50">
                {t("admin.ads.save")}
              </button>
            </div>
          </div>
        </div>
      )}
    </AdminLayout>
  );
}
