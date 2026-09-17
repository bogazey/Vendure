import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { oauthClientsApi, type OAuthClientInventoryOut } from "../services/api";
import ErrorState from "../components/ErrorState";

// A global, cross-product inventory (mission 17) - `GET
// /api/v1/admin/oauth-clients` is scoped exactly like `GET /products`
// (`admin_visible_product_ids`): a global admin sees every client here, a
// product-scoped admin sees only their own product's. Never shows a
// secret or a hash - only what an admin can already see per-product on
// each Product's own Configuration tab, just aggregated across products
// in one place.

export default function OAuthClients() {
  const { t } = useTranslation();
  const [clients, setClients] = useState<OAuthClientInventoryOut[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [pending, setPending] = useState<string | null>(null);

  const load = () => {
    oauthClientsApi.list().then(setClients).catch(setError);
  };
  useEffect(load, []);

  const toggleActive = async (client: OAuthClientInventoryOut) => {
    const key = client.is_active ? "oauthClients.disableConfirm" : "oauthClients.enableConfirm";
    if (!window.confirm(t(key, { clientId: client.client_id }))) return;
    setPending(client.client_id);
    try {
      await oauthClientsApi.setActive(client.client_id, !client.is_active);
      load();
    } catch (err) {
      setError(err);
    } finally {
      setPending(null);
    }
  };

  if (error) return <ErrorState error={error} />;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-display text-2xl font-bold text-slate-50">{t("nav.oauthClients")}</h1>
        <p className="text-sm text-slate-400">{t("oauthClients.subtitle")}</p>
      </div>
      <div className="glass-panel overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-surface-border text-xs uppercase text-slate-500">
              <th className="px-4 py-3">{t("products.clientId")}</th>
              <th className="px-4 py-3">{t("products.clientName")}</th>
              <th className="px-4 py-3">{t("oauthClients.product")}</th>
              <th className="px-4 py-3">{t("products.redirectUris")}</th>
              <th className="px-4 py-3">{t("oauthClients.postLogoutRedirectUris")}</th>
              <th className="px-4 py-3">{t("common.status")}</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {(clients ?? []).map((c) => (
              <tr key={c.client_id} className="border-b border-surface-border/60 text-slate-300">
                <td className="px-4 py-3 font-mono text-xs">{c.client_id}</td>
                <td className="px-4 py-3">{c.name}</td>
                <td className="px-4 py-3 font-mono text-xs">{c.product_id ?? "—"}</td>
                <td className="px-4 py-3 font-mono text-xs">{c.redirect_uris.join(", ") || "—"}</td>
                <td className="px-4 py-3 font-mono text-xs">{c.post_logout_redirect_uris.join(", ") || "—"}</td>
                <td className="px-4 py-3">
                  <span className={c.is_active ? "text-emerald-400" : "text-rose-400"}>
                    {c.is_active ? t("productDetail.configuration.active") : t("productDetail.configuration.inactive")}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <button
                    type="button"
                    className="btn-glass !px-3 !py-1 text-xs"
                    disabled={pending === c.client_id}
                    onClick={() => toggleActive(c)}
                  >
                    {c.is_active ? t("oauthClients.disable") : t("oauthClients.enable")}
                  </button>
                </td>
              </tr>
            ))}
            {clients !== null && clients.length === 0 && (
              <tr><td colSpan={7} className="px-4 py-6 text-center text-slate-500">{t("oauthClients.empty")}</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
