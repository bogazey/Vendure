import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  api,
  catalogApi,
  paymentsApi,
  subscriptionsApi,
  ApiError,
  type CapabilityDefOut,
  type CatalogPlanOut,
  type OAuthClientOut,
  type PlanStatsOut,
  type PlanVersionOut,
  type PriceOut,
} from "../services/api";
import ErrorState from "../components/ErrorState";

type Tab = "plans" | "capabilities" | "subscribers" | "billing" | "configuration";

export default function ProductDetail() {
  const { productId = "" } = useParams();
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>("plans");
  const [plans, setPlans] = useState<CatalogPlanOut[]>([]);
  const [capabilities, setCapabilities] = useState<CapabilityDefOut[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(null);

  const reloadPlans = () => catalogApi.listPlans(productId).then(setPlans).catch(setError);
  const reloadCapabilities = () => catalogApi.listCapabilities(productId).then(setCapabilities).catch(setError);

  useEffect(() => {
    reloadPlans();
    reloadCapabilities();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productId]);

  if (error) return <ErrorState error={error} />;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <p className="font-mono text-xs text-slate-500">{t("productDetail.product")}</p>
        <h1 className="font-display text-2xl font-bold text-slate-50">{productId}</h1>
      </div>

      <div className="flex gap-1 border-b border-surface-border/60">
        {(["plans", "capabilities", "subscribers", "billing", "configuration"] as Tab[]).map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={`rounded-t-lg px-4 py-2 text-sm font-medium ${tab === key ? "bg-white/10 text-slate-50" : "text-slate-400 hover:text-slate-200"}`}
          >
            {t(`productDetail.tabs.${key}`)}
          </button>
        ))}
      </div>

      {tab === "plans" && (
        <PlansTab
          productId={productId}
          plans={plans}
          selectedPlanId={selectedPlanId}
          onSelectPlan={setSelectedPlanId}
          onPlansChanged={reloadPlans}
          capabilities={capabilities}
        />
      )}
      {tab === "capabilities" && (
        <CapabilitiesTab productId={productId} capabilities={capabilities} onChanged={reloadCapabilities} />
      )}
      {tab === "subscribers" && <SubscribersTab productId={productId} />}
      {tab === "billing" && <BillingTab productId={productId} />}
      {tab === "configuration" && <ConfigurationTab productId={productId} />}
    </div>
  );
}

// --- Plans tab: the production-quality plan editor --------------------------

function PlansTab({
  productId,
  plans,
  selectedPlanId,
  onSelectPlan,
  onPlansChanged,
  capabilities,
}: {
  productId: string;
  plans: CatalogPlanOut[];
  selectedPlanId: string | null;
  onSelectPlan: (id: string | null) => void;
  onPlansChanged: () => void;
  capabilities: CapabilityDefOut[];
}) {
  const { t } = useTranslation();
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const selectedPlan = plans.find((p) => p.id === selectedPlanId) ?? null;

  const handleCreate = async () => {
    setFormError(null);
    try {
      await catalogApi.createPlan(productId, { slug, name });
      setSlug("");
      setName("");
      onPlansChanged();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : t("common.error"));
    }
  };

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
      <div className="flex flex-col gap-4">
        <div className="glass-panel overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-surface-border text-xs uppercase text-slate-500">
                <th className="px-4 py-3">{t("productDetail.plans.name")}</th>
                <th className="px-4 py-3">{t("productDetail.plans.status")}</th>
                <th className="px-4 py-3">{t("productDetail.plans.rank")}</th>
              </tr>
            </thead>
            <tbody>
              {plans.map((p) => (
                <tr
                  key={p.id}
                  onClick={() => onSelectPlan(p.id)}
                  className={`cursor-pointer border-b border-surface-border/60 text-slate-300 hover:bg-white/5 ${selectedPlanId === p.id ? "bg-white/10" : ""}`}
                >
                  <td className="px-4 py-3">
                    <div className="font-medium text-slate-100">{p.name}</div>
                    <div className="font-mono text-xs text-slate-500">{p.slug}</div>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`rounded-full px-2 py-0.5 text-xs ${p.status === "active" ? "bg-emerald-500/15 text-emerald-300" : "bg-white/5 text-slate-400"}`}>
                      {p.status}
                    </span>
                    {!p.is_public && <span className="ms-1 rounded-full bg-white/5 px-2 py-0.5 text-xs text-slate-400">{t("productDetail.plans.private")}</span>}
                  </td>
                  <td className="px-4 py-3 text-xs">{p.upgrade_rank}</td>
                </tr>
              ))}
              {plans.length === 0 && (
                <tr>
                  <td colSpan={3} className="px-4 py-6 text-center text-slate-500">
                    {t("productDetail.plans.empty")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="glass-panel flex flex-wrap items-end gap-2 p-4">
          <div>
            <label className="block text-xs text-slate-500">{t("productDetail.plans.slug")}</label>
            <input className="input-glass !w-auto" value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="creator" />
          </div>
          <div>
            <label className="block text-xs text-slate-500">{t("productDetail.plans.name")}</label>
            <input className="input-glass !w-auto" value={name} onChange={(e) => setName(e.target.value)} placeholder="Creator" />
          </div>
          <button type="button" className="btn-gradient" onClick={handleCreate} disabled={!slug || !name}>
            {t("productDetail.plans.createPlan")}
          </button>
        </div>
        {formError && <p className="text-sm text-red-400">{formError}</p>}
      </div>

      <div>
        {selectedPlan ? (
          <PlanEditor plan={selectedPlan} capabilities={capabilities} onChanged={onPlansChanged} />
        ) : (
          <div className="glass-panel p-6 text-sm text-slate-500">{t("productDetail.plans.selectPrompt")}</div>
        )}
      </div>
    </div>
  );
}

function PlanEditor({ plan, capabilities, onChanged }: { plan: CatalogPlanOut; capabilities: CapabilityDefOut[]; onChanged: () => void }) {
  const { t } = useTranslation();
  const [description, setDescription] = useState(plan.description ?? "");
  const [sortOrder, setSortOrder] = useState(plan.sort_order);
  const [upgradeRank, setUpgradeRank] = useState(plan.upgrade_rank);
  const [giftedEligible, setGiftedEligible] = useState(plan.gifted_eligible);
  const [trialEligible, setTrialEligible] = useState(plan.trial_eligible);
  const [isPublic, setIsPublic] = useState(plan.is_public);
  const [capValues, setCapValues] = useState<Record<string, string>>({});
  const [versions, setVersions] = useState<PlanVersionOut[]>([]);
  const [prices, setPrices] = useState<PriceOut[]>([]);
  const [stats, setStats] = useState<PlanStatsOut | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [priceForm, setPriceForm] = useState({ provider: "paddle", currency: "usd", amount: "", interval: "month", provider_price_id: "" });

  const load = () => {
    setDescription(plan.description ?? "");
    setSortOrder(plan.sort_order);
    setUpgradeRank(plan.upgrade_rank);
    setGiftedEligible(plan.gifted_eligible);
    setTrialEligible(plan.trial_eligible);
    setIsPublic(plan.is_public);
    catalogApi.getPlanCapabilities(plan.id).then((values) => {
      const asStrings: Record<string, string> = {};
      Object.entries(values).forEach(([k, v]) => (asStrings[k] = String(v)));
      setCapValues(asStrings);
    });
    catalogApi.listVersions(plan.id).then(setVersions);
    catalogApi.listPrices(plan.id).then(setPrices);
    catalogApi.planStats(plan.id).then(setStats);
  };

  useEffect(load, [plan.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const saveFields = async () => {
    await catalogApi.updatePlan(plan.id, {
      description, sort_order: sortOrder, upgrade_rank: upgradeRank,
      gifted_eligible: giftedEligible, trial_eligible: trialEligible, is_public: isPublic,
    });
    setMessage(t("productDetail.plans.saved"));
    onChanged();
  };

  const toggleArchive = async () => {
    if (plan.status === "active") await catalogApi.archivePlan(plan.id);
    else await catalogApi.activatePlan(plan.id);
    onChanged();
  };

  const saveCapability = async (def: CapabilityDefOut, raw: string) => {
    let value: boolean | number | string = raw;
    if (def.value_type === "boolean") value = raw === "true";
    else if (def.value_type === "integer") value = parseInt(raw, 10);
    await catalogApi.setPlanCapability(plan.id, def.key, value);
    load();
  };

  const publishVersion = async () => {
    await catalogApi.publishVersion(plan.id);
    load();
    setMessage(t("productDetail.plans.versionPublished"));
  };

  const addPrice = async () => {
    await catalogApi.createPrice(plan.id, {
      provider: priceForm.provider, currency: priceForm.currency,
      amount_cents: Math.round(parseFloat(priceForm.amount || "0") * 100),
      interval: priceForm.interval, provider_price_id: priceForm.provider_price_id || undefined,
    });
    setPriceForm({ ...priceForm, amount: "", provider_price_id: "" });
    load();
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="glass-panel flex flex-col gap-3 p-4">
        <div className="flex items-center justify-between">
          <h2 className="font-display text-lg font-semibold text-slate-50">{plan.name}</h2>
          <button type="button" className="btn-glass !px-3 !py-1.5 text-xs" onClick={toggleArchive}>
            {plan.status === "active" ? t("productDetail.plans.archive") : t("productDetail.plans.activate")}
          </button>
        </div>
        {stats && (
          <div className="grid grid-cols-2 gap-2 text-xs text-slate-400 sm:grid-cols-5">
            <Stat label={t("productDetail.plans.statPaid")} value={stats.paid_subscriptions} />
            <Stat label={t("productDetail.plans.statGifted")} value={stats.gifted} />
            <Stat label={t("productDetail.plans.statPromotions")} value={stats.promotions} />
            <Stat label={t("productDetail.plans.statTrials")} value={stats.trials} />
            <Stat label={t("productDetail.plans.statLegacy")} value={stats.legacy_entitlements} />
          </div>
        )}
        <label className="block text-xs text-slate-500">{t("productDetail.plans.description")}</label>
        <textarea className="input-glass" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div>
            <label className="block text-xs text-slate-500">{t("productDetail.plans.sortOrder")}</label>
            <input type="number" className="input-glass" value={sortOrder} onChange={(e) => setSortOrder(Number(e.target.value))} />
          </div>
          <div>
            <label className="block text-xs text-slate-500">{t("productDetail.plans.rank")}</label>
            <input type="number" className="input-glass" value={upgradeRank} onChange={(e) => setUpgradeRank(Number(e.target.value))} />
          </div>
          <label className="flex items-center gap-2 text-xs text-slate-300">
            <input type="checkbox" checked={isPublic} onChange={(e) => setIsPublic(e.target.checked)} />
            {t("productDetail.plans.public")}
          </label>
          <label className="flex items-center gap-2 text-xs text-slate-300">
            <input type="checkbox" checked={giftedEligible} onChange={(e) => setGiftedEligible(e.target.checked)} />
            {t("productDetail.plans.giftedEligible")}
          </label>
          <label className="flex items-center gap-2 text-xs text-slate-300">
            <input type="checkbox" checked={trialEligible} onChange={(e) => setTrialEligible(e.target.checked)} />
            {t("productDetail.plans.trialEligible")}
          </label>
        </div>
        <div className="flex items-center gap-3">
          <button type="button" className="btn-gradient !px-4 !py-1.5 text-xs" onClick={saveFields}>
            {t("common.save")}
          </button>
          {message && <span className="text-xs text-emerald-300">{message}</span>}
        </div>
      </div>

      <div className="glass-panel flex flex-col gap-2 p-4">
        <h3 className="text-sm font-semibold text-slate-100">{t("productDetail.plans.capabilitiesHeading")}</h3>
        {capabilities.length === 0 && <p className="text-xs text-slate-500">{t("productDetail.capabilities.empty")}</p>}
        {capabilities.map((def) => (
          <div key={def.id} className="flex items-center justify-between gap-3 text-sm">
            <span className="font-mono text-xs text-slate-400">{def.key}</span>
            {def.value_type === "boolean" ? (
              <select className="input-glass !w-32" value={capValues[def.key] ?? "false"} onChange={(e) => saveCapability(def, e.target.value)}>
                <option value="true">true</option>
                <option value="false">false</option>
              </select>
            ) : def.value_type === "enum" ? (
              <select className="input-glass !w-32" value={capValues[def.key] ?? ""} onChange={(e) => saveCapability(def, e.target.value)}>
                {(def.allowed_values ?? []).map((v) => (
                  <option key={v} value={v}>{v}</option>
                ))}
              </select>
            ) : (
              <input
                className="input-glass !w-32"
                defaultValue={capValues[def.key] ?? ""}
                onBlur={(e) => saveCapability(def, e.target.value)}
              />
            )}
          </div>
        ))}
      </div>

      <div className="glass-panel flex flex-col gap-2 p-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-100">{t("productDetail.plans.versionsHeading")}</h3>
          <button type="button" className="btn-glass !px-3 !py-1.5 text-xs" onClick={publishVersion}>
            {t("productDetail.plans.publishVersion")}
          </button>
        </div>
        <p className="text-xs text-slate-500">{t("productDetail.plans.versionsHint")}</p>
        {versions.map((v) => (
          <div key={v.id} className="flex items-center justify-between text-xs text-slate-400">
            <span>v{v.version_number}</span>
            <span>{v.published_at ? new Date(v.published_at).toLocaleString() : ""}</span>
          </div>
        ))}
      </div>

      <div className="glass-panel flex flex-col gap-3 p-4">
        <h3 className="text-sm font-semibold text-slate-100">{t("productDetail.plans.pricesHeading")}</h3>
        {prices.map((price) => (
          <div key={price.id} className="flex items-center justify-between text-xs text-slate-300">
            <span>
              {(price.amount_cents / 100).toFixed(2)} {price.currency} / {price.interval}
              {!price.is_active && <span className="ms-2 text-slate-500">({t("productDetail.plans.retired")})</span>}
            </span>
            {price.is_active && (
              <button type="button" className="btn-glass !px-2 !py-1 text-xs" onClick={() => catalogApi.retirePrice(price.id).then(load)}>
                {t("productDetail.plans.retirePrice")}
              </button>
            )}
          </div>
        ))}
        <div className="flex flex-wrap items-end gap-2 border-t border-surface-border/60 pt-3">
          <input className="input-glass !w-24" placeholder="9.99" value={priceForm.amount} onChange={(e) => setPriceForm({ ...priceForm, amount: e.target.value })} />
          <select className="input-glass !w-24" value={priceForm.currency} onChange={(e) => setPriceForm({ ...priceForm, currency: e.target.value })}>
            <option value="usd">USD</option>
            <option value="eur">EUR</option>
            <option value="gbp">GBP</option>
          </select>
          <select className="input-glass !w-28" value={priceForm.interval} onChange={(e) => setPriceForm({ ...priceForm, interval: e.target.value })}>
            <option value="month">{t("productDetail.plans.monthly")}</option>
            <option value="year">{t("productDetail.plans.yearly")}</option>
          </select>
          <input className="input-glass !w-40" placeholder="pri_xxx (Paddle)" value={priceForm.provider_price_id} onChange={(e) => setPriceForm({ ...priceForm, provider_price_id: e.target.value })} />
          <button type="button" className="btn-gradient !px-3 !py-1.5 text-xs" onClick={addPrice} disabled={!priceForm.amount}>
            {t("productDetail.plans.addPrice")}
          </button>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="glass-panel p-2 text-center">
      <div className="font-display text-lg font-bold text-slate-50">{value}</div>
      <div>{label}</div>
    </div>
  );
}

// --- Capabilities tab ---------------------------------------------------------

function CapabilitiesTab({ productId, capabilities, onChanged }: { productId: string; capabilities: CapabilityDefOut[]; onChanged: () => void }) {
  const { t } = useTranslation();
  const [key, setKey] = useState("");
  const [valueType, setValueType] = useState("integer");
  const [allowedValues, setAllowedValues] = useState("");

  const handleCreate = async () => {
    await catalogApi.defineCapability(productId, {
      key, value_type: valueType,
      allowed_values: valueType === "enum" ? allowedValues.split(",").map((s) => s.trim()).filter(Boolean) : undefined,
    });
    setKey("");
    setAllowedValues("");
    onChanged();
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="glass-panel overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-surface-border text-xs uppercase text-slate-500">
              <th className="px-4 py-3">{t("productDetail.capabilities.key")}</th>
              <th className="px-4 py-3">{t("productDetail.capabilities.type")}</th>
            </tr>
          </thead>
          <tbody>
            {capabilities.map((c) => (
              <tr key={c.id} className="border-b border-surface-border/60 text-slate-300">
                <td className="px-4 py-3 font-mono text-xs">{c.key}</td>
                <td className="px-4 py-3">{c.value_type}</td>
              </tr>
            ))}
            {capabilities.length === 0 && (
              <tr><td colSpan={2} className="px-4 py-6 text-center text-slate-500">{t("productDetail.capabilities.empty")}</td></tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="glass-panel flex flex-wrap items-end gap-2 p-4">
        <div>
          <label className="block text-xs text-slate-500">{t("productDetail.capabilities.key")}</label>
          <input className="input-glass !w-auto" value={key} onChange={(e) => setKey(e.target.value)} placeholder="daily_download_limit" />
        </div>
        <div>
          <label className="block text-xs text-slate-500">{t("productDetail.capabilities.type")}</label>
          <select className="input-glass !w-auto" value={valueType} onChange={(e) => setValueType(e.target.value)}>
            <option value="boolean">boolean</option>
            <option value="integer">integer</option>
            <option value="string">string</option>
            <option value="enum">enum</option>
          </select>
        </div>
        {valueType === "enum" && (
          <div>
            <label className="block text-xs text-slate-500">{t("productDetail.capabilities.allowedValues")}</label>
            <input className="input-glass !w-auto" value={allowedValues} onChange={(e) => setAllowedValues(e.target.value)} placeholder="480p,720p,4k" />
          </div>
        )}
        <button type="button" className="btn-gradient" onClick={handleCreate} disabled={!key}>
          {t("productDetail.capabilities.define")}
        </button>
      </div>
    </div>
  );
}

// --- Subscribers / Billing tabs -----------------------------------------------

function SubscribersTab({ productId }: { productId: string }) {
  const { t } = useTranslation();
  const [rows, setRows] = useState<Awaited<ReturnType<typeof subscriptionsApi.list>>>([]);
  useEffect(() => {
    subscriptionsApi.list().then((all) => setRows(all.filter((r) => r.product_id === productId)));
  }, [productId]);
  return (
    <div className="glass-panel overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-surface-border text-xs uppercase text-slate-500">
            <th className="px-4 py-3">{t("productDetail.subscribers.user")}</th>
            <th className="px-4 py-3">{t("common.status")}</th>
            <th className="px-4 py-3">{t("productDetail.subscribers.renews")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-b border-surface-border/60 text-slate-300">
              <td className="px-4 py-3 font-mono text-xs">{r.user_id}</td>
              <td className="px-4 py-3">{r.status}</td>
              <td className="px-4 py-3 text-xs">{r.current_period_end ? new Date(r.current_period_end).toLocaleDateString() : "—"}</td>
            </tr>
          ))}
          {rows.length === 0 && <tr><td colSpan={3} className="px-4 py-6 text-center text-slate-500">{t("productDetail.subscribers.empty")}</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function BillingTab({ productId }: { productId: string }) {
  const { t } = useTranslation();
  const [rows, setRows] = useState<Awaited<ReturnType<typeof paymentsApi.list>>>([]);
  useEffect(() => {
    paymentsApi.list().then((all) => setRows(all.filter((r) => r.product_id === productId)));
  }, [productId]);
  return (
    <div className="glass-panel overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-surface-border text-xs uppercase text-slate-500">
            <th className="px-4 py-3">{t("productDetail.billing.amount")}</th>
            <th className="px-4 py-3">{t("common.status")}</th>
            <th className="px-4 py-3">{t("productDetail.billing.date")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-b border-surface-border/60 text-slate-300">
              <td className="px-4 py-3">{(r.amount_cents / 100).toFixed(2)} {r.currency}</td>
              <td className="px-4 py-3">{r.status}</td>
              <td className="px-4 py-3 text-xs">{new Date(r.created_at).toLocaleDateString()}</td>
            </tr>
          ))}
          {rows.length === 0 && <tr><td colSpan={3} className="px-4 py-6 text-center text-slate-500">{t("productDetail.billing.empty")}</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

// --- Configuration tab: OAuth client(s) + secret rotation ---------------------
//
// `GET /api/v1/admin/clients` is deliberately super_admin-only and
// unfiltered (mission 6 continuation: "product-scoped admins must NOT
// create global products or OAuth clients" - this tab is where they'd see
// one if listing were scoped, so it stays global-admin-only rather than
// widening that route). A product-scoped admin visiting their own
// product's page gets a plain "super admins only" message here instead of
// the whole page 403'ing - the Plans/Capabilities tabs above remain fully
// usable for them regardless.

function ConfigurationTab({ productId }: { productId: string }) {
  const { t } = useTranslation();
  const [clients, setClients] = useState<OAuthClientOut[] | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [rotated, setRotated] = useState<{ client_id: string; client_secret: string } | null>(null);

  const load = () => {
    api
      .listClients()
      .then((all) => setClients(all.filter((c) => c.product_id === productId)))
      .catch((err) => {
        if (err instanceof ApiError && err.status === 403) setForbidden(true);
        else setError(err);
      });
  };
  useEffect(load, [productId]);

  const rotate = async (clientId: string) => {
    if (!window.confirm(t("products.rotateSecretConfirm"))) return;
    try {
      const result = await api.rotateClientSecret(clientId);
      setRotated(result);
    } catch (err) {
      setError(err);
    }
  };

  if (error) return <ErrorState error={error} />;
  if (forbidden) {
    return <div className="glass-panel p-6 text-sm text-slate-400">{t("products.configurationSuperAdminOnly")}</div>;
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="glass-panel overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-surface-border text-xs uppercase text-slate-500">
              <th className="px-4 py-3">{t("products.clientId")}</th>
              <th className="px-4 py-3">{t("products.clientName")}</th>
              <th className="px-4 py-3">{t("products.redirectUris")}</th>
              <th className="px-4 py-3">{t("common.status")}</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {(clients ?? []).map((c) => (
              <tr key={c.client_id} className="border-b border-surface-border/60 text-slate-300">
                <td className="px-4 py-3 font-mono text-xs">{c.client_id}</td>
                <td className="px-4 py-3">{c.name}</td>
                <td className="px-4 py-3 font-mono text-xs">{c.redirect_uris.join(", ") || "—"}</td>
                <td className="px-4 py-3">{c.is_active ? t("productDetail.configuration.active") : t("productDetail.configuration.inactive")}</td>
                <td className="px-4 py-3">
                  <button type="button" className="btn-glass !px-3 !py-1 text-xs" onClick={() => rotate(c.client_id)}>
                    {t("products.rotateSecret")}
                  </button>
                </td>
              </tr>
            ))}
            {clients !== null && clients.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-6 text-center text-slate-500">{t("products.noOauthClients")}</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {rotated && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="glass-panel w-full max-w-lg p-6">
            <h2 className="font-display text-lg font-semibold text-slate-50">{t("products.secretRotated")}</h2>
            <p className="mt-1 text-sm text-slate-300">{t("products.secretRotatedHint", { clientId: rotated.client_id })}</p>
            <div className="mt-4 rounded-lg border border-amber-400/40 bg-amber-400/10 p-3 text-sm font-semibold text-amber-300">
              {t("products.secretShownOnce")}
            </div>
            <label className="mb-1 mt-4 block text-xs text-slate-500">{t("products.clientSecret")}</label>
            <input readOnly className="input-glass w-full font-mono text-xs" value={rotated.client_secret} onFocus={(e) => e.target.select()} />
            <div className="mt-6 flex justify-end">
              <button type="button" className="btn-gradient" onClick={() => setRotated(null)}>
                {t("products.doneSecretSaved")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
