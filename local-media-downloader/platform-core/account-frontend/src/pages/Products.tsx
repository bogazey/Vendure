import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, type EntitlementView, type Membership, type ProductOut } from "../services/api";
import ErrorState from "../components/ErrorState";

export default function Products() {
  const { t } = useTranslation();
  const [products, setProducts] = useState<ProductOut[]>([]);
  const [memberships, setMemberships] = useState<Membership[]>([]);
  const [entitlements, setEntitlements] = useState<EntitlementView[]>([]);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    Promise.all([api.listProducts(), api.myMemberships(), api.myEntitlements()])
      .then(([p, m, e]) => {
        setProducts(p);
        setMemberships(m);
        setEntitlements(e);
      })
      .catch(setError);
  }, []);

  if (error) return <ErrorState error={error} />;

  // A product the user has actual CURRENT product access to - either
  // they've signed into it via SSO (membership) or they hold an ACTIVE
  // entitlement for it (gifted/paid/promo/trial) without having visited
  // it yet. /me/entitlements returns full history including
  // revoked/expired rows, so those must be excluded here or a revoked
  // gift would keep showing as if still granted. Must stay consistent
  // with Overview.tsx's touchedProductIds.
  const activeEntitlements = entitlements.filter((e) => e.status === "active");
  const touchedProductIds = new Set([...memberships.map((m) => m.product_id), ...activeEntitlements.map((e) => e.product_id)]);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="mb-3 font-display text-lg font-semibold text-slate-50">{t("products.yourProducts")}</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {products.filter((p) => touchedProductIds.has(p.id)).map((product) => {
            const ent = activeEntitlements.find((e) => e.product_id === product.id);
            return (
              <div key={product.id} className="glass-panel flex flex-col gap-2 p-4">
                <p className="font-display font-semibold text-slate-50">{product.name}</p>
                <p className="text-sm text-slate-300">{ent ? (ent.plan_name ?? ent.plan_slug) : t("products.free")}</p>
                <a href={`https://${product.domain}`} target="_blank" rel="noreferrer" className="btn-glass mt-2 self-start !px-3 !py-1.5 text-xs">
                  {t("products.open")}
                </a>
              </div>
            );
          })}
          {products.filter((p) => touchedProductIds.has(p.id)).length === 0 && (
            <p className="text-sm text-slate-500">{t("products.noneYet")}</p>
          )}
        </div>
      </div>

      <div>
        <h2 className="mb-3 font-display text-lg font-semibold text-slate-50">{t("products.discoverHeading")}</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {products.filter((p) => !touchedProductIds.has(p.id) && p.status === "live").map((product) => (
            <div key={product.id} className="glass-panel flex flex-col gap-2 p-4 opacity-80">
              <p className="font-display font-semibold text-slate-50">{product.name}</p>
              <a href={`https://${product.domain}`} target="_blank" rel="noreferrer" className="btn-glass mt-2 self-start !px-3 !py-1.5 text-xs">
                {t("products.discover")}
              </a>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
