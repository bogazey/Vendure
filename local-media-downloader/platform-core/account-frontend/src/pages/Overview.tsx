import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, type EntitlementView, type Membership, type ProductOut, type SecurityEvent } from "../services/api";
import { useAuth } from "../context/AuthContext";
import ErrorState from "../components/ErrorState";

export default function Overview() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [memberships, setMemberships] = useState<Membership[]>([]);
  const [entitlements, setEntitlements] = useState<EntitlementView[]>([]);
  const [products, setProducts] = useState<ProductOut[]>([]);
  const [events, setEvents] = useState<SecurityEvent[]>([]);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    Promise.all([api.myMemberships(), api.myEntitlements(), api.listProducts(), api.mySecurityEvents()])
      .then(([m, e, p, ev]) => {
        setMemberships(m);
        setEntitlements(e);
        setProducts(p);
        setEvents(ev);
      })
      .catch(setError);
  }, []);

  if (error) return <ErrorState error={error} />;

  // Only ever show a product the user actually has a membership OR an
  // ACTIVE entitlement in - /me/entitlements returns full history
  // (revoked/expired included, since admin views need it), so a revoked
  // gift or expired trial must not keep showing as if still granted
  // (mission brief: "never show fake active memberships").
  const activeEntitlements = entitlements.filter((e) => e.status === "active");
  const touchedProductIds = new Set([...memberships.map((m) => m.product_id), ...activeEntitlements.map((e) => e.product_id)]);
  const cards = products.filter((p) => touchedProductIds.has(p.id));

  return (
    <div className="flex flex-col gap-6">
      <div className="glass-panel p-6">
        <p className="text-xs uppercase text-slate-500">{t("overview.memberSince")}</p>
        <p className="text-sm text-slate-200">{user ? new Date(user.created_at).toLocaleDateString() : ""}</p>
        <p className="mt-2 text-xs text-slate-500">
          {t("overview.emailVerified")}: {user?.email_verified ? t("common.yes") : t("common.no")}
        </p>
      </div>

      <div>
        <h2 className="mb-3 font-display text-lg font-semibold text-slate-50">{t("overview.productsHeading")}</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {cards.map((product) => {
            const ent = activeEntitlements.find((e) => e.product_id === product.id);
            return (
              <div key={product.id} className="glass-panel p-4">
                <p className="font-display font-semibold text-slate-50">{product.name}</p>
                <p className="mt-1 text-sm text-slate-300">
                  {ent ? (ent.plan_name ?? ent.plan_slug ?? "—") : t("overview.notActivated")}
                </p>
                {ent && ent.source !== "paddle" && (
                  <span className="mt-2 inline-block rounded-full bg-brand-purple/15 px-2 py-0.5 text-xs text-brand-purple">
                    {t("overview.giftedAccess")}
                  </span>
                )}
              </div>
            );
          })}
          {cards.length === 0 && <p className="text-sm text-slate-500">{t("overview.noProducts")}</p>}
        </div>
      </div>

      <div>
        <h2 className="mb-3 font-display text-lg font-semibold text-slate-50">{t("overview.recentSecurity")}</h2>
        <div className="glass-panel divide-y divide-surface-border/60">
          {events.slice(0, 5).map((e, i) => (
            <div key={i} className="flex items-center justify-between px-4 py-3 text-sm text-slate-300">
              <span>{t(`securityEvents.${e.action}`, { defaultValue: e.action })}</span>
              <span className="text-xs text-slate-500">{new Date(e.created_at).toLocaleString()}</span>
            </div>
          ))}
          {events.length === 0 && <p className="px-4 py-6 text-center text-sm text-slate-500">{t("overview.noEvents")}</p>}
        </div>
      </div>
    </div>
  );
}
