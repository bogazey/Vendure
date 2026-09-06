import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../context/AuthContext";
import { api } from "../services/api";
import { openPaymentUpdate } from "../lib/paddle";
import type { BillingPeriod, PaymentHistory, Plan } from "../types/commercial";
import { PLAN_PRICES } from "../types/commercial";

export default function BillingManagement() {
  const { t, i18n } = useTranslation();
  const { account, refresh } = useAuth();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState(false);
  const [pending, setPending] = useState(false);
  const [confirmation, setConfirmation] = useState<"cancel" | "resume" | "change-plan" | null>(null);
  const [plan, setPlan] = useState<Plan>("pro");
  const [period, setPeriod] = useState<BillingPeriod>("monthly");
  const [history, setHistory] = useState<PaymentHistory | null>(null);
  const [invoiceUrl, setInvoiceUrl] = useState<string | null>(null);
  const subscription = account?.subscription;
  const signature = JSON.stringify(subscription);
  useEffect(() => { setPending(false); }, [signature]);
  useEffect(() => {
    if (!pending) return;
    const timer = window.setInterval(() => { void refresh(); }, 3000);
    const stop = window.setTimeout(() => window.clearInterval(timer), 30000);
    return () => { window.clearInterval(timer); window.clearTimeout(stop); };
  }, [pending, refresh]);
  if (!subscription || subscription.status === "none") return null;
  const manageable = ["active", "trialing"].includes(subscription.status);
  const run = async (action: () => Promise<void>) => {
    setBusy(true); setError(false); setMessage(""); setInvoiceUrl(null);
    try { await action(); } catch { setError(true); } finally { setBusy(false); }
  };
  const submit = () => run(async () => {
    if (!confirmation) return;
    await api.manageSubscription(confirmation, plan, period);
    setConfirmation(null); setPending(true); setMessage(t("billingManage.pending"));
    void refresh();
  });
  return <section id="billing-management" className="glass-panel flex flex-col gap-4 p-6" aria-busy={busy}>
    <h2 className="font-display text-lg text-slate-50">{t("app.manageBilling")}</h2>
    {busy && <p role="status">{t("billingManage.loading")}</p>}
    {error && <p role="alert" className="text-red-300">{t("billingManage.error")}</p>}
    {message && <p role="status" className="text-brand-aqua">{message}</p>}
    <fieldset disabled={busy || pending} className="flex flex-col gap-3 disabled:opacity-60">
      {manageable && <>
        <label>{t("app.plan")}<select className="input-glass mx-2" value={plan} onChange={e => setPlan(e.target.value as Plan)}>
          <option value="pro">{t("pricing.plans.pro.name")}</option><option value="creator">{t("pricing.plans.creator.name")}</option>
        </select></label>
        <label>{t("billingPage.cadence")}<select className="input-glass mx-2" value={period} onChange={e => setPeriod(e.target.value as BillingPeriod)}>
          <option value="monthly">{t("pricing.monthly")}</option><option value="annual">{t("pricing.annual")}</option>
        </select></label>
        <p className="text-sm text-slate-400">{plan !== "free" && `$${PLAN_PRICES[plan][period]}`} / {t(`billingPage.${period}`)}</p>
        <div className="flex flex-wrap gap-3">
          <button className="btn-glass" disabled={subscription.cancel_at_period_end || (subscription.plan === plan && subscription.billing_period === period)} onClick={() => setConfirmation("change-plan")}>{t("billingPage.change")}</button>
          <button className="btn-glass" onClick={() => setConfirmation(subscription.cancel_at_period_end ? "resume" : "cancel")}>{t(subscription.cancel_at_period_end ? "billingManage.resume" : "billingManage.cancel")}</button>
        </div>
      </>}
      {confirmation && <div className="rounded-2xl border border-brand-purple/40 p-4" role="group" aria-label={t("billingManage.confirm")}>
        <p>{t(`billingManage.${confirmation}Confirm`)}</p>
        <button className="btn-gradient mt-3" onClick={submit}>{t("billingManage.confirm")}</button>
        <button className="btn-glass mx-2" onClick={() => setConfirmation(null)}>{t("billingManage.back")}</button>
      </div>}
    </fieldset>
    <div className="flex flex-wrap gap-3">
      {["active", "past_due"].includes(subscription.status) && <button className="btn-glass" disabled={busy} onClick={() => run(async () => {
        await openPaymentUpdate(await api.updatePaymentMethod(), event => {
          if (event.name === "checkout.completed") { setMessage(t("billingManage.paymentDone")); void refresh(); }
        });
      })}>{t("billingManage.payment")}</button>}
      <button className="btn-glass" disabled={busy} onClick={() => run(async () => { setHistory(await api.paymentHistory()); })}>{t("billingManage.history")}</button>
      <button className="btn-glass" disabled={busy} onClick={() => run(async () => { await refresh(); })}>{t("accountPage.refresh")}</button>
    </div>
    <p className="text-xs text-slate-400">{t("billingManage.hosted")}</p>
    {subscription.status === "past_due" && <p className="text-amber-300">{t("billingManage.overdue")}</p>}
    {history && <div className="flex flex-col gap-3">
      {!history.items.length && <p>{t("billingManage.empty")}</p>}
      {history.items.map(row => <div key={row.id} className="flex flex-wrap items-center gap-3 border-t border-white/10 py-3">
        <span>{new Date(row.date).toLocaleDateString(i18n.language)}</span>
        <span>{new Intl.NumberFormat(i18n.language, { style: "currency", currency: row.currency }).format(Number(row.total) / (10 ** (new Intl.NumberFormat("en", { style: "currency", currency: row.currency }).resolvedOptions().maximumFractionDigits ?? 2)))}</span>
        <span>{t(`billingManage.status.${row.status}`, { defaultValue: row.status })}</span>
        {row.invoice_available && <button className="btn-glass" disabled={busy} onClick={() => run(async () => { setInvoiceUrl((await api.invoice(row.id)).url); })}>{t("billingManage.invoice")}</button>}
      </div>)}
      {history.next && <button className="btn-glass" disabled={busy} onClick={() => run(async () => {
        const next = await api.paymentHistory(history.next!); setHistory({ items: [...history.items, ...next.items], next: next.next });
      })}>{t("billingManage.more")}</button>}
    </div>}
    {invoiceUrl && <a className="text-brand-aqua underline" href={invoiceUrl} target="_blank" rel="noopener noreferrer">{t("billingManage.openInvoice")}</a>}
  </section>;
}
