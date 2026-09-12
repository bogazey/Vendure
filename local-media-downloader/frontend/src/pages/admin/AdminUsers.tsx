import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import ConfirmDialog from "../../components/ConfirmDialog";
import ErrorBanner from "../../components/ErrorBanner";
import { ApiError, api } from "../../services/api";
import { brandLink } from "../../styles/ui";
import type { AdminActionLogOut, AdminUserOut, Plan } from "../../types/commercial";
import { PLAN_LABELS } from "../../types/commercial";
import { formatDate } from "../../utils/format";
import AdminLayout from "./AdminLayout";
import { actionLabelKey } from "./adminShared";

const PAGE_SIZE = 20;

function subscriptionSourceLabelKey(user: AdminUserOut): string {
  if (user.subscription_provider === "paddle") return "admin.users.sourcePaddle";
  if (user.subscription_provider === "gifted") return "admin.users.sourceGifted";
  return "admin.users.sourceFree";
}

export default function AdminUsers() {
  const { t } = useTranslation();
  const [users, setUsers] = useState<AdminUserOut[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [grantTarget, setGrantTarget] = useState<AdminUserOut | null>(null);
  const [grantCredits, setGrantCredits] = useState(10);
  const [grantReason, setGrantReason] = useState("");
  const [confirmDisable, setConfirmDisable] = useState<AdminUserOut | null>(null);
  const [detailUser, setDetailUser] = useState<AdminUserOut | null>(null);
  const [detailActions, setDetailActions] = useState<AdminActionLogOut[]>([]);
  const [subscriptionTarget, setSubscriptionTarget] = useState<AdminUserOut | null>(null);
  const [subscriptionPlan, setSubscriptionPlan] = useState<Plan>("pro");
  const [subscriptionReason, setSubscriptionReason] = useState("");
  const [confirmingSubscription, setConfirmingSubscription] = useState(false);
  const [subscriptionBusy, setSubscriptionBusy] = useState(false);

  const load = async (q: string, pageIndex: number) => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.adminListUsers({ search: q || undefined, limit: PAGE_SIZE, offset: pageIndex * PAGE_SIZE });
      setUsers(result.users);
      setTotal(result.total);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("admin.users.loadError"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load(search, page);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(0);
    load(search, 0);
  };

  const applyUpdate = (updated: AdminUserOut) => {
    setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)));
    setDetailUser((prev) => (prev && prev.id === updated.id ? updated : prev));
  };

  const handleGrant = async () => {
    if (!grantTarget || !grantReason.trim()) return;
    try {
      const updated = await api.adminGrantCredits(grantTarget.id, grantCredits, grantReason.trim());
      applyUpdate(updated);
      setGrantTarget(null);
      setGrantReason("");
      setGrantCredits(10);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("admin.users.grantError"));
    }
  };

  const handleConfirmDisable = async () => {
    if (!confirmDisable) return;
    try {
      const updated = await api.adminSetAccountStatus(confirmDisable.id, "disabled");
      applyUpdate(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("admin.users.statusError"));
    } finally {
      setConfirmDisable(null);
    }
  };

  const handleReactivate = async (user: AdminUserOut) => {
    try {
      const updated = await api.adminSetAccountStatus(user.id, "active");
      applyUpdate(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("admin.users.statusError"));
    }
  };

  const openSubscriptionManager = (user: AdminUserOut) => {
    setSubscriptionTarget(user);
    setSubscriptionPlan(user.plan !== "free" ? user.plan : "pro");
    setSubscriptionReason("");
    setConfirmingSubscription(false);
  };

  const closeSubscriptionManager = () => {
    setSubscriptionTarget(null);
    setConfirmingSubscription(false);
  };

  const handleSubscriptionSubmit = async () => {
    if (!subscriptionTarget) return;
    setSubscriptionBusy(true);
    try {
      const updated = await api.adminUpdateSubscription(subscriptionTarget.id, subscriptionPlan, subscriptionReason.trim() || undefined);
      applyUpdate(updated);
      closeSubscriptionManager();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("admin.users.subscriptionError"));
    } finally {
      setSubscriptionBusy(false);
    }
  };

  const openDetail = async (user: AdminUserOut) => {
    setDetailUser(user);
    try {
      const actions = await api.adminListAuditLog({ targetUserId: user.id, limit: 20 });
      setDetailActions(actions);
    } catch {
      setDetailActions([]);
    }
  };

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <AdminLayout>
      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      <form onSubmit={handleSearchSubmit} className="flex gap-2">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t("admin.users.searchPlaceholder")}
          className="input-glass min-w-0 flex-1 py-2"
        />
        <button type="submit" className="btn-glass px-3 py-2">
          {t("admin.users.searchButton")}
        </button>
      </form>

      <div className="glass-panel min-w-0 overflow-x-auto">
        <table className="w-full text-start text-sm">
          <thead className="bg-white/[0.03] text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2 text-start">{t("admin.users.columnEmail")}</th>
              <th className="px-4 py-2 text-start">{t("admin.users.columnPlan")}</th>
              <th className="px-4 py-2 text-start">{t("admin.users.columnSubscription")}</th>
              <th className="px-4 py-2 text-start">{t("admin.users.columnCredits")}</th>
              <th className="px-4 py-2 text-start">{t("admin.users.columnStatus")}</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-slate-500">
                  {t("app.loading")}
                </td>
              </tr>
            )}
            {!loading && users.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-slate-500">
                  {t("admin.users.empty")}
                </td>
              </tr>
            )}
            {users.map((u) => (
              <tr key={u.id} className="border-t border-white/[0.06]">
                <td className="px-4 py-2 text-slate-200">
                  <button type="button" onClick={() => openDetail(u)} className={`${brandLink} text-start`} dir="ltr">
                    {u.email}
                  </button>
                </td>
                <td className="px-4 py-2 text-slate-400">{PLAN_LABELS[u.plan]}</td>
                <td className="px-4 py-2 text-slate-400">
                  {t(`status.${u.subscription_status}`)}
                  {u.subscription_provider === "gifted" && (
                    <span className="ms-1.5 rounded-full bg-brand-aqua/15 px-1.5 py-0.5 text-[10px] font-semibold text-brand-aqua">
                      {t("admin.users.sourceGiftedBadge")}
                    </span>
                  )}
                </td>
                <td className="px-4 py-2 text-slate-400" dir="ltr">
                  {u.credits_used}
                  {u.credits_included !== null ? ` / ${u.credits_included}` : ""}
                  {u.credits_bonus ? (
                    <span className="ms-1.5 rounded-full bg-brand-purple/15 px-1.5 py-0.5 text-[10px] font-semibold text-brand-purple">
                      +{u.credits_bonus} {t("admin.users.bonus")}
                    </span>
                  ) : null}
                </td>
                <td className="px-4 py-2">
                  <span className={u.status === "disabled" ? "text-red-400" : "text-emerald-400"}>
                    {u.status === "disabled" ? t("admin.users.status.disabled") : t("admin.users.status.active")}
                  </span>
                </td>
                <td className="px-4 py-2">
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => setGrantTarget(u)}
                      className={`text-xs ${brandLink} underline decoration-dotted underline-offset-2`}
                    >
                      {t("admin.users.grantCredits")}
                    </button>
                    <button
                      type="button"
                      onClick={() => openSubscriptionManager(u)}
                      className={`text-xs ${brandLink} underline decoration-dotted underline-offset-2`}
                    >
                      {t("admin.users.manageSubscription")}
                    </button>
                    {u.status === "disabled" ? (
                      <button
                        type="button"
                        onClick={() => handleReactivate(u)}
                        className="text-xs text-slate-400 underline decoration-dotted underline-offset-2 hover:text-slate-200"
                      >
                        {t("admin.users.reactivate")}
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => setConfirmDisable(u)}
                        className="text-xs text-red-400/90 underline decoration-dotted underline-offset-2 hover:text-red-300"
                      >
                        {t("admin.users.disable")}
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {total > PAGE_SIZE && (
        <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-slate-400">
          <span>{t("admin.users.pageSummary", { start: page * PAGE_SIZE + 1, end: Math.min(total, (page + 1) * PAGE_SIZE), total })}</span>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={page === 0}
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              className="btn-glass px-3 py-1.5 text-xs disabled:cursor-not-allowed disabled:opacity-50"
            >
              {t("admin.users.previous")}
            </button>
            <button
              type="button"
              disabled={page >= pageCount - 1}
              onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
              className="btn-glass px-3 py-1.5 text-xs disabled:cursor-not-allowed disabled:opacity-50"
            >
              {t("admin.users.next")}
            </button>
          </div>
        </div>
      )}

      {grantTarget && (
        <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/60 px-4 backdrop-blur-sm">
          <div className="glass-panel-raised flex w-full max-w-sm flex-col gap-4 p-5">
            <h2 className="font-display text-sm font-semibold text-slate-50" dir="ltr">
              {t("admin.users.grantTitle", { email: grantTarget.email })}
            </h2>
            <label className="flex flex-col gap-1.5 text-sm">
              <span className="text-slate-400">{t("admin.users.credits")}</span>
              <input
                type="number"
                min={1}
                max={100000}
                value={grantCredits}
                onChange={(e) => setGrantCredits(Number(e.target.value))}
                className="input-glass py-2"
                dir="ltr"
              />
            </label>
            <label className="flex flex-col gap-1.5 text-sm">
              <span className="text-slate-400">{t("admin.users.reason")}</span>
              <input
                type="text"
                value={grantReason}
                onChange={(e) => setGrantReason(e.target.value)}
                placeholder={t("admin.users.reasonPlaceholder")}
                className="input-glass py-2"
              />
            </label>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setGrantTarget(null)} className="btn-glass px-3 py-1.5">
                {t("common.cancel")}
              </button>
              <button type="button" onClick={handleGrant} disabled={!grantReason.trim()} className="btn-gradient px-3 py-1.5">
                {t("admin.users.grant")}
              </button>
            </div>
          </div>
        </div>
      )}

      {subscriptionTarget && (
        <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/60 px-4 backdrop-blur-sm">
          <div className="glass-panel-raised flex w-full max-w-sm flex-col gap-4 p-5">
            <h2 className="font-display text-sm font-semibold text-slate-50" dir="ltr">
              {t("admin.users.manageSubscriptionTitle", { email: subscriptionTarget.email })}
            </h2>

            {subscriptionTarget.subscription_provider === "paddle" ? (
              <>
                <p className="text-sm text-slate-400">{t("admin.users.paidManagedNotice")}</p>
                <div className="flex justify-end">
                  <button type="button" onClick={closeSubscriptionManager} className="btn-glass px-3 py-1.5">
                    {t("common.close")}
                  </button>
                </div>
              </>
            ) : !confirmingSubscription ? (
              <>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
                  <dt className="text-slate-500">{t("admin.users.columnPlan")}</dt>
                  <dd className="text-slate-300">{PLAN_LABELS[subscriptionTarget.plan]}</dd>
                  <dt className="text-slate-500">{t("admin.users.detailSource")}</dt>
                  <dd className="text-slate-300">{t(subscriptionSourceLabelKey(subscriptionTarget))}</dd>
                </dl>
                <label className="flex flex-col gap-1.5 text-sm">
                  <span className="text-slate-400">{t("admin.users.newPlan")}</span>
                  <select
                    className="input-glass py-2"
                    value={subscriptionPlan}
                    onChange={(e) => setSubscriptionPlan(e.target.value as Plan)}
                  >
                    <option value="free">{PLAN_LABELS.free}</option>
                    <option value="pro">{PLAN_LABELS.pro}</option>
                    <option value="creator">{PLAN_LABELS.creator}</option>
                  </select>
                </label>
                <label className="flex flex-col gap-1.5 text-sm">
                  <span className="text-slate-400">{t("admin.users.giftReasonOptional")}</span>
                  <input
                    type="text"
                    value={subscriptionReason}
                    onChange={(e) => setSubscriptionReason(e.target.value)}
                    placeholder={t("admin.users.reasonPlaceholder")}
                    className="input-glass py-2"
                  />
                </label>
                <p className="rounded-xl border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
                  {t("admin.users.giftWarning")}
                </p>
                <div className="flex justify-end gap-2">
                  <button type="button" onClick={closeSubscriptionManager} className="btn-glass px-3 py-1.5">
                    {t("common.cancel")}
                  </button>
                  <button
                    type="button"
                    onClick={() => setConfirmingSubscription(true)}
                    disabled={subscriptionPlan === subscriptionTarget.plan}
                    className="btn-gradient px-3 py-1.5"
                  >
                    {t(
                      subscriptionPlan === "free"
                        ? "admin.users.revokeGift"
                        : subscriptionTarget.subscription_provider === "gifted"
                          ? "admin.users.updateGift"
                          : "admin.users.grantGift"
                    )}
                  </button>
                </div>
              </>
            ) : (
              <>
                <p className="text-sm text-slate-300">
                  {t(
                    subscriptionPlan === "free"
                      ? "admin.users.revokeConfirmBody"
                      : "admin.users.giftConfirmBody",
                    { plan: PLAN_LABELS[subscriptionPlan] }
                  )}
                </p>
                <div className="flex justify-end gap-2">
                  <button type="button" onClick={() => setConfirmingSubscription(false)} disabled={subscriptionBusy} className="btn-glass px-3 py-1.5">
                    {t("billingManage.back")}
                  </button>
                  <button type="button" onClick={handleSubscriptionSubmit} disabled={subscriptionBusy} className="btn-gradient px-3 py-1.5">
                    {t(
                      subscriptionPlan === "free"
                        ? "admin.users.revokeGift"
                        : subscriptionTarget.subscription_provider === "gifted"
                          ? "admin.users.updateGift"
                          : "admin.users.grantGift"
                    )}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {confirmDisable && (
        <ConfirmDialog
          title={t("admin.users.confirmDisableTitle")}
          body={t("admin.users.confirmDisableBody", { email: confirmDisable.email })}
          confirmLabel={t("admin.users.disable")}
          danger
          onConfirm={handleConfirmDisable}
          onCancel={() => setConfirmDisable(null)}
        />
      )}

      {detailUser && (
        <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/60 px-4 backdrop-blur-sm" onClick={() => setDetailUser(null)}>
          <div className="glass-panel-raised flex w-full max-w-md flex-col gap-4 p-5" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between">
              <h2 className="font-display text-sm font-semibold text-slate-50" dir="ltr">
                {detailUser.email}
              </h2>
              <button type="button" onClick={() => setDetailUser(null)} className="text-slate-500 hover:text-slate-300" aria-label={t("common.cancel")}>
                ✕
              </button>
            </div>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
              <dt className="text-slate-500">{t("admin.users.detailId")}</dt>
              <dd className="truncate text-slate-300" dir="ltr">{detailUser.id}</dd>
              <dt className="text-slate-500">{t("admin.users.detailRole")}</dt>
              <dd className="text-slate-300">{detailUser.role}</dd>
              <dt className="text-slate-500">{t("admin.users.columnPlan")}</dt>
              <dd className="text-slate-300">{PLAN_LABELS[detailUser.plan]}</dd>
              <dt className="text-slate-500">{t("admin.users.columnSubscription")}</dt>
              <dd className="text-slate-300">{t(`status.${detailUser.subscription_status}`)}</dd>
              <dt className="text-slate-500">{t("admin.users.detailSource")}</dt>
              <dd className="text-slate-300">{t(subscriptionSourceLabelKey(detailUser))}</dd>
              {detailUser.subscription_provider === "gifted" && (
                <>
                  <dt className="text-slate-500">{t("admin.users.detailGranted")}</dt>
                  <dd className="text-slate-300" dir="ltr">{detailUser.gifted_granted_at ? formatDate(detailUser.gifted_granted_at) : "—"}</dd>
                  <dt className="text-slate-500">{t("admin.users.detailGrantedBy")}</dt>
                  <dd className="truncate text-slate-300" dir="ltr">{detailUser.gifted_granted_by_email ?? "—"}</dd>
                  {detailUser.gifted_reason && (
                    <>
                      <dt className="text-slate-500">{t("admin.users.detailReason")}</dt>
                      <dd className="text-slate-300">{detailUser.gifted_reason}</dd>
                    </>
                  )}
                </>
              )}
              <dt className="text-slate-500">{t("admin.users.detailIncluded")}</dt>
              <dd className="text-slate-300" dir="ltr">{detailUser.credits_included ?? "—"}</dd>
              <dt className="text-slate-500">{t("admin.users.detailBonus")}</dt>
              <dd className="text-slate-300" dir="ltr">{detailUser.credits_bonus ?? "—"}</dd>
              <dt className="text-slate-500">{t("admin.users.detailCreated")}</dt>
              <dd className="text-slate-300" dir="ltr">{formatDate(detailUser.created_at)}</dd>
            </dl>
            <div className="border-t border-white/[0.08] pt-3">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{t("admin.overview.recentActions")}</h3>
              {detailActions.length === 0 ? (
                <p className="text-sm text-slate-500">{t("admin.activity.empty")}</p>
              ) : (
                <ul className="flex flex-col gap-1.5 text-sm text-slate-300">
                  {detailActions.map((entry) => (
                    <li key={entry.id} className="flex items-center justify-between gap-2">
                      <span>{t(actionLabelKey(entry.action))}</span>
                      <span className="text-xs text-slate-500" dir="ltr">{formatDate(entry.created_at)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      )}
    </AdminLayout>
  );
}
