import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, ApiError, type AdminUserOut, type EntitlementView } from "../services/api";
import ErrorState from "../components/ErrorState";
import { useAuth } from "../context/AuthContext";

const SOURCES = ["free", "paddle", "gifted", "promotion", "trial", "internal", "lifetime", "bundle"] as const;

function UserDetail({ user, onChanged }: { user: AdminUserOut; onChanged: () => void }) {
  const { t } = useTranslation();
  const { user: me } = useAuth();
  const [memberships, setMemberships] = useState<Array<{ product_id: string; status: string }>>([]);
  const [entitlements, setEntitlements] = useState<EntitlementView[]>([]);
  const [roleSlug, setRoleSlug] = useState("support");
  const [scope, setScope] = useState("global");
  const [productId, setProductId] = useState("");
  const [planSlug, setPlanSlug] = useState("");
  const [source, setSource] = useState<(typeof SOURCES)[number]>("gifted");
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [busyMsg, setBusyMsg] = useState<string | null>(null);

  const load = () => {
    api.getUserMemberships(user.id).then(setMemberships).catch(() => setMemberships([]));
    api.getUserEntitlements(user.id).then(setEntitlements).catch(() => setEntitlements([]));
  };

  useEffect(load, [user.id]);

  const handleAssignRole = async () => {
    setMessage(null);
    try {
      await api.assignRole(user.id, roleSlug, scope);
      setMessage(t("users.roleAssigned"));
      onChanged();
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : t("common.error"));
    }
  };

  const handleRevokeRole = async (role: string, roleScope: string) => {
    await api.revokeRole(user.id, role, roleScope);
    setMessage(t("users.roleRevoked"));
    onChanged();
  };

  const handleToggleStatus = async () => {
    try {
      await api.setUserStatus(user.id, user.status === "active" ? "disabled" : "active");
      onChanged();
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : t("common.error"));
    }
  };

  const handleGrant = async () => {
    setMessage(null);
    try {
      await api.grantEntitlement(user.id, { product_id: productId, plan_slug: planSlug, source, reason: reason || undefined });
      setMessage(null);
      setBusyMsg(null);
      load();
    } catch (err) {
      if (err instanceof ApiError && err.code === "FORBIDDEN") {
        setBusyMsg(t("entitlements.paidBlocked"));
      } else {
        setBusyMsg(err instanceof Error ? err.message : t("common.error"));
      }
    }
  };

  const handleRevokeEntitlement = async (productIdToRevoke: string) => {
    try {
      await api.revokeEntitlement(user.id, productIdToRevoke, reason || undefined);
      load();
    } catch (err) {
      setBusyMsg(err instanceof ApiError ? err.message : t("common.error"));
    }
  };

  return (
    <div className="glass-panel flex flex-col gap-5 p-6">
      <div>
        <h3 className="font-display text-base font-semibold text-slate-50">{user.email}</h3>
        <p className="text-xs text-slate-500">
          {t("users.globalId")}: <span className="font-mono">{user.id}</span>
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${user.status === "active" ? "bg-emerald-500/15 text-emerald-300" : "bg-red-500/15 text-red-300"}`}>
          {t(user.status === "active" ? "common.active" : "common.disabled")}
        </span>
        <button
          type="button"
          className="btn-glass !px-3 !py-1 text-xs"
          onClick={handleToggleStatus}
          disabled={me?.id === user.id && user.status === "active"}
          title={me?.id === user.id ? t("users.cannotDisableSelf") : undefined}
        >
          {t(user.status === "active" ? "users.disableAccount" : "users.enableAccount")}
        </button>
      </div>

      <section>
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t("users.roles")}</h4>
        <ul className="mt-2 flex flex-wrap gap-2">
          {user.roles.map((r) => (
            <li key={`${r.role_slug}-${r.scope}`} className="flex items-center gap-1.5 rounded-full border border-surface-border bg-white/5 px-2.5 py-1 text-xs text-slate-300">
              {r.role_slug} · {r.scope}
              <button type="button" onClick={() => handleRevokeRole(r.role_slug, r.scope)} className="text-slate-500 hover:text-red-300" aria-label={t("users.revokeRole")}>
                ×
              </button>
            </li>
          ))}
          {user.roles.length === 0 && <li className="text-xs text-slate-600">{t("common.none")}</li>}
        </ul>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <select className="input-glass !w-auto" value={roleSlug} onChange={(e) => setRoleSlug(e.target.value)}>
            <option value="support">support</option>
            <option value="finance">finance</option>
            <option value="admin">admin</option>
            <option value="super_admin">super_admin</option>
          </select>
          <input className="input-glass !w-auto" value={scope} onChange={(e) => setScope(e.target.value)} placeholder="global" />
          <button type="button" className="btn-glass !px-3 !py-1.5 text-xs" onClick={handleAssignRole}>
            {t("users.assignRole")}
          </button>
        </div>
        {message && <p className="mt-1 text-xs text-slate-400">{message}</p>}
      </section>

      <section>
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t("users.memberships")}</h4>
        {memberships.length === 0 ? (
          <p className="mt-1 text-xs text-slate-600">{t("users.noMemberships")}</p>
        ) : (
          <ul className="mt-2 flex flex-wrap gap-2">
            {memberships.map((m) => (
              <li key={m.product_id} className="rounded-full border border-surface-border bg-white/5 px-2.5 py-1 text-xs text-slate-300">
                {m.product_id}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t("users.entitlements")}</h4>
        <ul className="mt-2 flex flex-col gap-1.5">
          {entitlements.map((e) => (
            <li key={e.id} className="flex items-center justify-between rounded-lg border border-surface-border bg-white/[0.03] px-3 py-2 text-xs text-slate-300">
              <span>
                {e.product_id} · {e.plan_slug} · <span className={e.source === "paddle" ? "text-brand-aqua" : "text-slate-400"}>{e.source}</span> · {e.status}
              </span>
              {e.status === "active" && (
                <button type="button" className="text-slate-500 hover:text-red-300" onClick={() => handleRevokeEntitlement(e.product_id)}>
                  {t("common.revoke")}
                </button>
              )}
            </li>
          ))}
          {entitlements.length === 0 && <li className="text-xs text-slate-600">{t("common.none")}</li>}
        </ul>

        <div className="mt-3 flex flex-col gap-2 rounded-xl border border-surface-border bg-white/[0.02] p-3">
          <p className="text-xs font-semibold text-slate-300">{t("entitlements.grantTitle")}</p>
          <div className="flex flex-wrap gap-2">
            <input className="input-glass !w-auto" placeholder={t("entitlements.product")} value={productId} onChange={(e) => setProductId(e.target.value)} />
            <input className="input-glass !w-auto" placeholder={t("entitlements.plan")} value={planSlug} onChange={(e) => setPlanSlug(e.target.value)} />
            <select className="input-glass !w-auto" value={source} onChange={(e) => setSource(e.target.value as (typeof SOURCES)[number])}>
              {SOURCES.map((s) => (
                <option key={s} value={s}>
                  {t(`entitlements.source${s.charAt(0).toUpperCase()}${s.slice(1)}`)}
                </option>
              ))}
            </select>
          </div>
          <input className="input-glass" placeholder={t("common.reason")} value={reason} onChange={(e) => setReason(e.target.value)} />
          {source === "gifted" && <p className="text-xs text-brand-aqua">{t("entitlements.warning")}</p>}
          {busyMsg && <p className="text-xs text-red-400">{busyMsg}</p>}
          <button type="button" className="btn-gradient !w-auto self-start" onClick={handleGrant} disabled={!productId || !planSlug}>
            {t("common.grant")}
          </button>
        </div>
      </section>
    </div>
  );
}

export default function Users() {
  const { t } = useTranslation();
  const [users, setUsers] = useState<AdminUserOut[]>([]);
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<AdminUserOut | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = () => {
    api
      .listUsers(q || undefined)
      .then((rows) => {
        setUsers(rows);
        if (selected) {
          const updated = rows.find((r) => r.id === selected.id);
          if (updated) setSelected(updated);
        }
      })
      .catch(setError);
  };

  useEffect(load, [q]);

  if (error) return <ErrorState error={error} />;

  return (
    <div className="flex flex-col gap-6">
      <input
        className="input-glass max-w-sm"
        placeholder={t("users.searchPlaceholder")}
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      <div className="glass-panel overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-surface-border text-xs uppercase text-slate-500">
              <th className="px-4 py-3">{t("users.email")}</th>
              <th className="px-4 py-3">{t("users.status")}</th>
              <th className="px-4 py-3">{t("users.entitlements")}</th>
              <th className="px-4 py-3">{t("users.gifted")}</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className="border-b border-surface-border/60 text-slate-300">
                <td className="px-4 py-3">{u.email}</td>
                <td className="px-4 py-3">{t(u.status === "active" ? "common.active" : "common.disabled")}</td>
                <td className="px-4 py-3">{u.entitlement_count}</td>
                <td className="px-4 py-3">{u.gifted_entitlement_count}</td>
                <td className="px-4 py-3 text-right">
                  <button type="button" className="btn-glass !px-3 !py-1 text-xs" onClick={() => setSelected(u)}>
                    {t("users.viewDetail")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {selected && <UserDetail user={selected} onChanged={load} />}
    </div>
  );
}
