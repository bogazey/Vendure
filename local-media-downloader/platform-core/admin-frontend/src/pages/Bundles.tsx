import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { bundlesApi, type BundleOut } from "../services/api";
import ErrorState from "../components/ErrorState";

export default function Bundles() {
  const { t } = useTranslation();
  const [bundles, setBundles] = useState<BundleOut[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");

  const load = () => {
    bundlesApi.list().then(setBundles).catch(setError);
  };
  useEffect(load, []);

  const handleCreate = async () => {
    await bundlesApi.create(slug, name);
    setSlug("");
    setName("");
    load();
  };

  if (error) return <ErrorState error={error} />;

  return (
    <div className="flex flex-col gap-6">
      <div className="glass-panel overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-surface-border text-xs uppercase text-slate-500">
              <th className="px-4 py-3">{t("bundles.name")}</th>
              <th className="px-4 py-3">{t("common.status")}</th>
            </tr>
          </thead>
          <tbody>
            {bundles.map((b) => (
              <tr key={b.id} className="border-b border-surface-border/60 text-slate-300">
                <td className="px-4 py-3">
                  <div className="font-medium text-slate-100">{b.name}</div>
                  <div className="font-mono text-xs text-slate-500">{b.slug}</div>
                </td>
                <td className="px-4 py-3">{b.status}</td>
              </tr>
            ))}
            {bundles.length === 0 && (
              <tr><td colSpan={2} className="px-4 py-6 text-center text-slate-500">{t("bundles.empty")}</td></tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="glass-panel flex flex-wrap items-end gap-2 p-4">
        <div>
          <label className="block text-xs text-slate-500">{t("bundles.slug")}</label>
          <input className="input-glass !w-auto" value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="creator-suite" />
        </div>
        <div>
          <label className="block text-xs text-slate-500">{t("bundles.name")}</label>
          <input className="input-glass !w-auto" value={name} onChange={(e) => setName(e.target.value)} placeholder="Creator Suite" />
        </div>
        <button type="button" className="btn-gradient" onClick={handleCreate} disabled={!slug || !name}>
          {t("bundles.create")}
        </button>
      </div>
      <p className="text-xs text-slate-500">{t("bundles.hint")}</p>
    </div>
  );
}
