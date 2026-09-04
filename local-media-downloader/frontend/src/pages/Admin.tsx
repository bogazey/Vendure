import { useEffect, useState } from "react";
import ErrorBanner from "../components/ErrorBanner";
import { ApiError, api } from "../services/api";
import type { AdminUserOut } from "../types/commercial";
import { PLAN_LABELS } from "../types/commercial";

export default function Admin() {
  const [users, setUsers] = useState<AdminUserOut[]>([]);
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [grantTarget, setGrantTarget] = useState<AdminUserOut | null>(null);
  const [grantCredits, setGrantCredits] = useState(10);
  const [grantReason, setGrantReason] = useState("");

  const load = async (q?: string) => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.adminListUsers({ search: q || undefined, limit: 50 });
      setUsers(result.users);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load users.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleToggleStatus = async (user: AdminUserOut) => {
    const nextStatus = user.status === "disabled" ? "active" : "disabled";
    try {
      const updated = await api.adminSetAccountStatus(user.id, nextStatus);
      setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update account status.");
    }
  };

  const handleGrant = async () => {
    if (!grantTarget || !grantReason.trim()) return;
    try {
      const updated = await api.adminGrantCredits(grantTarget.id, grantCredits, grantReason.trim());
      setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)));
      setGrantTarget(null);
      setGrantReason("");
      setGrantCredits(10);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not grant credits.");
    }
  };

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6 px-6 py-10">
      <h1 className="text-xl font-bold text-slate-50">Admin · Users</h1>

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          load(search);
        }}
        className="flex gap-2"
      >
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by email or user id"
          className="flex-1 rounded-md border border-surface-border bg-surface px-3 py-2 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
        />
        <button type="submit" className="rounded-md border border-surface-border px-3 py-2 text-sm text-slate-300 hover:border-slate-500">
          Search
        </button>
      </form>

      <div className="overflow-x-auto rounded-xl border border-surface-border">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface-raised text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2">Email</th>
              <th className="px-4 py-2">Plan</th>
              <th className="px-4 py-2">Subscription</th>
              <th className="px-4 py-2">Credits</th>
              <th className="px-4 py-2">Status</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-slate-500">
                  Loading…
                </td>
              </tr>
            )}
            {!loading && users.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-slate-500">
                  No users found.
                </td>
              </tr>
            )}
            {users.map((u) => (
              <tr key={u.id} className="border-t border-surface-border">
                <td className="px-4 py-2 text-slate-200">{u.email}</td>
                <td className="px-4 py-2 text-slate-400">{PLAN_LABELS[u.plan]}</td>
                <td className="px-4 py-2 text-slate-400">{u.subscription_status}</td>
                <td className="px-4 py-2 text-slate-400">
                  {u.credits_used}
                  {u.credits_included !== null ? ` / ${u.credits_included}` : ""}
                </td>
                <td className="px-4 py-2">
                  <span className={u.status === "disabled" ? "text-red-400" : "text-emerald-400"}>{u.status}</span>
                </td>
                <td className="flex gap-2 px-4 py-2">
                  <button
                    type="button"
                    onClick={() => setGrantTarget(u)}
                    className="text-xs text-indigo-400 underline decoration-dotted underline-offset-2 hover:text-indigo-300"
                  >
                    Grant credits
                  </button>
                  <button
                    type="button"
                    onClick={() => handleToggleStatus(u)}
                    className="text-xs text-slate-400 underline decoration-dotted underline-offset-2 hover:text-slate-200"
                  >
                    {u.status === "disabled" ? "Reactivate" : "Disable"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {grantTarget && (
        <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/50 px-4">
          <div className="flex w-full max-w-sm flex-col gap-4 rounded-xl border border-surface-border bg-surface-raised p-5">
            <h2 className="text-sm font-semibold text-slate-50">Grant credits to {grantTarget.email}</h2>
            <label className="flex flex-col gap-1.5 text-sm">
              <span className="text-slate-400">Credits</span>
              <input
                type="number"
                min={1}
                max={100000}
                value={grantCredits}
                onChange={(e) => setGrantCredits(Number(e.target.value))}
                className="rounded-md border border-surface-border bg-surface px-3 py-2 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
              />
            </label>
            <label className="flex flex-col gap-1.5 text-sm">
              <span className="text-slate-400">Reason</span>
              <input
                type="text"
                value={grantReason}
                onChange={(e) => setGrantReason(e.target.value)}
                placeholder="e.g. support case #123"
                className="rounded-md border border-surface-border bg-surface px-3 py-2 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
              />
            </label>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setGrantTarget(null)}
                className="rounded-md border border-surface-border px-3 py-1.5 text-sm text-slate-300 hover:border-slate-500"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleGrant}
                disabled={!grantReason.trim()}
                className="rounded-md bg-indigo-500 px-3 py-1.5 text-sm font-semibold text-white hover:bg-indigo-400 disabled:opacity-60"
              >
                Grant
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
