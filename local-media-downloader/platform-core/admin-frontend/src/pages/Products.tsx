import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, ApiError, type ProductOut } from "../services/api";
import ErrorState from "../components/ErrorState";

export default function Products() {
  const { t } = useTranslation();
  const [products, setProducts] = useState<ProductOut[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [id, setId] = useState("");
  const [name, setName] = useState("");
  const [domain, setDomain] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const load = () => {
    api.listProducts().then(setProducts).catch(setError);
  };
  useEffect(load, []);

  const handleCreate = async () => {
    setFormError(null);
    try {
      await api.createProduct({ id, name, domain, status: "planned" });
      setId("");
      setName("");
      setDomain("");
      load();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : t("common.error"));
    }
  };

  if (error) return <ErrorState error={error} />;

  return (
    <div className="flex flex-col gap-6">
      <div className="glass-panel overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-surface-border text-xs uppercase text-slate-500">
              <th className="px-4 py-3">{t("products.id")}</th>
              <th className="px-4 py-3">{t("products.name")}</th>
              <th className="px-4 py-3">{t("products.domain")}</th>
              <th className="px-4 py-3">{t("products.status")}</th>
            </tr>
          </thead>
          <tbody>
            {products.map((p) => (
              <tr key={p.id} className="border-b border-surface-border/60 text-slate-300">
                <td className="px-4 py-3 font-mono text-xs">{p.id}</td>
                <td className="px-4 py-3">{p.name}</td>
                <td className="px-4 py-3">{p.domain}</td>
                <td className="px-4 py-3">
                  <span className="rounded-full bg-white/5 px-2 py-0.5 text-xs">{t(`products.${p.status}`, { defaultValue: p.status })}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="glass-panel flex flex-wrap items-end gap-2 p-4">
        <div>
          <label className="block text-xs text-slate-500">{t("products.id")}</label>
          <input className="input-glass !w-auto" value={id} onChange={(e) => setId(e.target.value)} placeholder="gamey" />
        </div>
        <div>
          <label className="block text-xs text-slate-500">{t("products.name")}</label>
          <input className="input-glass !w-auto" value={name} onChange={(e) => setName(e.target.value)} placeholder="Gamey" />
        </div>
        <div>
          <label className="block text-xs text-slate-500">{t("products.domain")}</label>
          <input className="input-glass !w-auto" value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="gamey.cc" />
        </div>
        <button type="button" className="btn-gradient" onClick={handleCreate} disabled={!id || !name || !domain}>
          {t("products.createProduct")}
        </button>
      </div>
      {formError && <p className="text-sm text-red-400">{formError}</p>}
    </div>
  );
}
