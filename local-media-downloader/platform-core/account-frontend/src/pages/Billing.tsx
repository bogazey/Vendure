import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, type EntitlementView, type ProductOut, type SubscriptionOut } from "../services/api";
import ErrorState from "../components/ErrorState";

const GIFT_LIKE_SOURCES = new Set(["gifted", "internal", "promotion", "trial", "bundle"]);

export default function Billing() {
  const { t } = useTranslation();
  const [products, setProducts] = useState<ProductOut[]>([]);
  const [entitlements, setEntitlements] = useState<EntitlementView[]>([]);
  const [subscriptions, setSubscriptions] = useState<SubscriptionOut[]>([]);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    Promise.all([api.listProducts(), api.myEntitlements(), api.mySubscriptions()])
      .then(([p, e, s]) => {
        setProducts(p);
        setEntitlements(e);
        setSubscriptions(s);
      })
      .catch(setError);
  }, []);

  if (error) return <ErrorState error={error} />;

  const productName = (id: string) => products.find((p) => p.id === id)?.name ?? id;
  const activeEntitlements = entitlements.filter((e) => e.status === "active");

  if (activeEntitlements.length === 0) {
    return <p className="text-sm text-slate-500">{t("billing.empty")}</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      {activeEntitlements.map((ent) => {
        const isGifted = GIFT_LIKE_SOURCES.has(ent.source);
        const subscription = subscriptions.find((s) => s.product_id === ent.product_id);
        return (
          <div key={ent.product_id} className="glass-panel flex flex-col gap-2 p-5 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-xs uppercase text-slate-500">{productName(ent.product_id)}</p>
              <p className="font-display text-lg font-semibold text-slate-50">{ent.plan_name ?? ent.plan_slug}</p>
              {subscription?.current_period_end && (
                <p className="text-xs text-slate-500">
                  {t("billing.renews")}: {new Date(subscription.current_period_end).toLocaleDateString()}
                </p>
              )}
            </div>
            <div>
              {isGifted ? (
                <span className="rounded-full bg-brand-purple/15 px-3 py-1 text-xs text-brand-purple">{t("billing.giftedAccess")}</span>
              ) : subscription ? (
                <span className="rounded-full bg-emerald-500/15 px-3 py-1 text-xs text-emerald-300">
                  {subscription.cancel_at_period_end ? t("billing.cancelingSoon") : t("billing.active")}
                </span>
              ) : (
                <span className="rounded-full bg-white/5 px-3 py-1 text-xs text-slate-400">{ent.source}</span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
