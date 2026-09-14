import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, type Membership, type ProductOut } from "../services/api";
import ErrorState from "../components/ErrorState";

export default function ConnectedApps() {
  const { t } = useTranslation();
  const [memberships, setMemberships] = useState<Membership[]>([]);
  const [products, setProducts] = useState<ProductOut[]>([]);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    Promise.all([api.myMemberships(), api.listProducts()])
      .then(([m, p]) => {
        setMemberships(m);
        setProducts(p);
      })
      .catch(setError);
  }, []);

  if (error) return <ErrorState error={error} />;

  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-slate-500">{t("connectedApps.hint")}</p>
      {memberships.map((m) => {
        const product = products.find((p) => p.id === m.product_id);
        return (
          <div key={m.product_id} className="glass-panel flex items-center justify-between p-4">
            <div>
              <p className="text-sm font-medium text-slate-100">{product?.name ?? m.product_id}</p>
              <p className="text-xs text-slate-500">
                {t("connectedApps.firstAuthorized")}: {new Date(m.first_seen_at).toLocaleDateString()} · {t("connectedApps.lastUsed")}: {new Date(m.last_seen_at).toLocaleDateString()}
              </p>
            </div>
          </div>
        );
      })}
      {memberships.length === 0 && <p className="text-sm text-slate-500">{t("connectedApps.empty")}</p>}
    </div>
  );
}
