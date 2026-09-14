import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api, ApiError, type ProductOnboardResponse, type ProductOut } from "../services/api";
import ErrorState from "../components/ErrorState";

const emptyForm = {
  id: "",
  name: "",
  domain: "",
  description: "",
  isDiscoverable: true,
  status: "planned",
  clientId: "",
  clientName: "",
  redirectUris: "",
};

export default function Products() {
  const { t } = useTranslation();
  const [products, setProducts] = useState<ProductOut[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [form, setForm] = useState(emptyForm);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [onboarded, setOnboarded] = useState<ProductOnboardResponse | null>(null);

  const load = () => {
    api.listProducts().then(setProducts).catch(setError);
  };
  useEffect(load, []);

  const setField = <K extends keyof typeof emptyForm>(key: K, value: (typeof emptyForm)[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  // Convenience default (`${id}-client`) so an admin doesn't have to
  // invent a second slug - stops applying the instant the admin types
  // into Client ID directly, tracked via a ref rather than by comparing
  // against the reconstructed previous default (which broke on every
  // keystroke past the first once `id` was more than one character).
  const clientIdTouched = useRef(false);
  useEffect(() => {
    if (!clientIdTouched.current && form.id.trim()) setField("clientId", `${form.id.trim()}-client`);
  }, [form.id]);
  const setClientId = (value: string) => {
    clientIdTouched.current = true;
    setField("clientId", value);
  };

  const canSubmit =
    form.id.trim() && form.name.trim() && form.domain.trim() && form.clientId.trim() && form.clientName.trim() && form.redirectUris.trim();

  const handleOnboard = async () => {
    setFormError(null);
    setSubmitting(true);
    try {
      const redirect_uris = form.redirectUris
        .split(/[\n,]/)
        .map((s) => s.trim())
        .filter(Boolean);
      const result = await api.onboardProduct({
        id: form.id.trim(),
        name: form.name.trim(),
        domain: form.domain.trim(),
        description: form.description.trim() || undefined,
        is_discoverable: form.isDiscoverable,
        status: form.status,
        client_id: form.clientId.trim(),
        client_name: form.clientName.trim(),
        redirect_uris,
      });
      setOnboarded(result);
      setForm(emptyForm);
      clientIdTouched.current = false;
      load();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : t("common.error"));
    } finally {
      setSubmitting(false);
    }
  };

  if (error) return <ErrorState error={error} />;

  return (
    <div className="flex flex-col gap-6">
      <div className="glass-panel overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-surface-border text-xs uppercase text-slate-500">
              <th className="px-4 py-3">{t("products.id")}</th>
              <th className="px-4 py-3">{t("products.name")}</th>
              <th className="px-4 py-3">{t("products.domain")}</th>
              <th className="px-4 py-3">{t("products.status")}</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {products.map((p) => (
              <tr key={p.id} className="border-b border-surface-border/60 text-slate-300">
                <td className="px-4 py-3 font-mono text-xs">{p.id}</td>
                <td className="px-4 py-3">{p.name}</td>
                <td className="px-4 py-3">{p.domain}</td>
                <td className="px-4 py-3">
                  <span className="rounded-full bg-white/5 px-2 py-0.5 text-xs">{t(`products.${p.status}`, { defaultValue: p.status })}</span>
                </td>
                <td className="px-4 py-3">
                  <Link to={`/products/${p.id}`} className="btn-glass !px-3 !py-1 text-xs">
                    {t("products.manage")}
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="glass-panel flex flex-col gap-4 p-5">
        <div>
          <h2 className="font-display text-lg font-semibold text-slate-50">{t("products.addProduct")}</h2>
          <p className="text-xs text-slate-500">{t("products.addProductHint")}</p>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label={t("products.id")}>
            <input className="input-glass" value={form.id} onChange={(e) => setField("id", e.target.value)} placeholder="filey" />
          </Field>
          <Field label={t("products.name")}>
            <input className="input-glass" value={form.name} onChange={(e) => setField("name", e.target.value)} placeholder="Filey" />
          </Field>
          <Field label={t("products.domain")}>
            <input className="input-glass" value={form.domain} onChange={(e) => setField("domain", e.target.value)} placeholder="filey.cc" />
          </Field>
          <Field label={t("products.status")}>
            <select className="input-glass" value={form.status} onChange={(e) => setField("status", e.target.value)}>
              <option value="planned">{t("products.planned")}</option>
              <option value="building">{t("products.building")}</option>
              <option value="live">{t("products.live")}</option>
            </select>
          </Field>
          <div className="sm:col-span-2">
            <Field label={t("products.description")}>
              <textarea
                className="input-glass min-h-[64px]"
                value={form.description}
                onChange={(e) => setField("description", e.target.value)}
                placeholder={t("products.descriptionPlaceholder")}
              />
            </Field>
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-300 sm:col-span-2">
            <input type="checkbox" checked={form.isDiscoverable} onChange={(e) => setField("isDiscoverable", e.target.checked)} />
            {t("products.discoverable")}
          </label>
        </div>

        <div className="border-t border-surface-border/60 pt-4">
          <h3 className="mb-2 text-sm font-semibold text-slate-200">{t("products.initialOauthClient")}</h3>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label={t("products.clientId")}>
              <input className="input-glass font-mono" value={form.clientId} onChange={(e) => setClientId(e.target.value)} placeholder="filey-client" />
            </Field>
            <Field label={t("products.clientName")}>
              <input className="input-glass" value={form.clientName} onChange={(e) => setField("clientName", e.target.value)} placeholder="Filey Web Client" />
            </Field>
            <div className="sm:col-span-2">
              <Field label={t("products.redirectUris")}>
                <textarea
                  className="input-glass min-h-[64px] font-mono text-xs"
                  value={form.redirectUris}
                  onChange={(e) => setField("redirectUris", e.target.value)}
                  placeholder={"https://filey.cc/auth/callback"}
                />
              </Field>
              <p className="mt-1 text-xs text-slate-500">{t("products.redirectUrisHint")}</p>
            </div>
          </div>
        </div>

        <div>
          <button type="button" className="btn-gradient" onClick={handleOnboard} disabled={!canSubmit || submitting}>
            {submitting ? t("common.loading") : t("products.addProduct")}
          </button>
        </div>
        {formError && <p className="text-sm text-red-400">{formError}</p>}
      </div>

      {onboarded && <SecretRevealModal result={onboarded} onClose={() => setOnboarded(null)} />}
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-xs text-slate-500">{label}</label>
      {children}
    </div>
  );
}

function SecretRevealModal({ result, onClose }: { result: ProductOnboardResponse; onClose: () => void }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(result.client_secret);
      setCopied(true);
    } catch {
      // Clipboard access can fail (permissions, insecure context) - the
      // secret is still fully visible and selectable in the field below,
      // so this is a convenience feature, not the only way to get it.
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="glass-panel w-full max-w-lg p-6">
        <h2 className="font-display text-lg font-semibold text-slate-50">{t("products.productOnboarded")}</h2>
        <p className="mt-1 text-sm text-slate-300">
          {t("products.productOnboardedHint", { name: result.product.name, clientId: result.client_id })}
        </p>

        <div className="mt-4 rounded-lg border border-amber-400/40 bg-amber-400/10 p-3 text-sm font-semibold text-amber-300">
          {t("products.secretShownOnce")}
        </div>

        <label className="mb-1 mt-4 block text-xs text-slate-500">{t("products.clientSecret")}</label>
        <div className="flex items-center gap-2">
          <input readOnly className="input-glass flex-1 font-mono text-xs" value={result.client_secret} onFocus={(e) => e.target.select()} />
          <button type="button" className="btn-glass !px-3 !py-2 text-xs" onClick={copy}>
            {copied ? t("products.copied") : t("products.copy")}
          </button>
        </div>

        <div className="mt-6 flex justify-end">
          <button type="button" className="btn-gradient" onClick={onClose}>
            {t("products.doneSecretSaved")}
          </button>
        </div>
      </div>
    </div>
  );
}
