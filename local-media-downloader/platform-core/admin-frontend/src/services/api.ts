// `??` (not `||`): an explicitly empty VITE_PLATFORM_API_BASE_URL means
// "same-origin" (e.g. staging/production behind a reverse proxy that
// routes /api/* to the backend on this same host) and must NOT fall
// through to the localhost dev default - only a genuinely unset
// (`undefined`) build-time value should do that.
const API_BASE = import.meta.env.VITE_PLATFORM_API_BASE_URL ?? "http://localhost:8100";

export class ApiError extends Error {
  code: string;
  status: number;
  constructor(code: string, message: string, status: number) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new ApiError(body.code || "UNKNOWN_ERROR", body.message || "Something went wrong.", res.status);
  }
  return body as T;
}

export interface CurrentUser {
  id: string;
  email: string;
  email_verified: boolean;
  status: string;
  created_at: string;
}

export interface RoleAssignmentOut {
  role_slug: string;
  scope: string;
  granted_by: string | null;
  created_at: string;
}

export interface AdminUserOut {
  id: string;
  email: string;
  email_verified: boolean;
  status: string;
  created_at: string;
  roles: RoleAssignmentOut[];
  entitlement_count: number;
  gifted_entitlement_count: number;
}

export interface AdminOverviewOut {
  total_users: number;
  active_users: number;
  total_products: number;
  paid_entitlements: number;
  gifted_entitlements: number;
  revenue_available: boolean;
  revenue_note: string;
}

export interface ProductOut {
  id: string;
  name: string;
  domain: string;
  status: string;
  icon_ref: string | null;
  description: string | null;
  is_discoverable: boolean;
  created_at: string;
}

export interface OAuthClientOut {
  client_id: string;
  name: string;
  product_id: string | null;
  redirect_uris: string[];
  is_active: boolean;
}

export interface ProductOnboardRequest {
  id: string;
  name: string;
  domain: string;
  description?: string;
  is_discoverable: boolean;
  status: string;
  client_id: string;
  client_name: string;
  redirect_uris: string[];
}

export interface ProductOnboardResponse {
  product: ProductOut;
  client_id: string;
  client_secret: string;
}

export interface EntitlementView {
  id: string;
  product_id: string;
  plan_slug: string | null;
  source: string;
  status: string;
  starts_at: string;
  expires_at: string | null;
  granted_by_email: string | null;
  reason: string | null;
}

export interface GiftedAccessRow {
  id: string;
  user_id: string;
  user_email: string;
  product_id: string;
  plan_slug: string | null;
  source: string;
  expires_at: string | null;
  granted_by_email: string | null;
  reason: string | null;
  created_at: string;
}

export interface AuditLogOut {
  id: string;
  actor_user_id: string | null;
  actor_email: string | null;
  action: string;
  target_type: string;
  target_id: string | null;
  product_id: string | null;
  before_state: Record<string, unknown> | null;
  after_state: Record<string, unknown> | null;
  reason: string | null;
  created_at: string;
}

// --- Mission 6 continuation: Product Subscription Manager -------------------

export interface CatalogPlanOut {
  id: string;
  product_id: string;
  slug: string;
  name: string;
  description: string | null;
  status: string;
  is_public: boolean;
  sort_order: number;
  upgrade_rank: number;
  gifted_eligible: boolean;
  trial_eligible: boolean;
  current_version_id: string | null;
}

export interface PlanVersionOut {
  id: string;
  plan_id: string;
  version_number: number;
  status: string;
  capability_snapshot: Record<string, boolean | number | string>;
  published_at: string | null;
}

export interface PriceOut {
  id: string;
  product_id: string;
  plan_id: string;
  plan_version_id: string | null;
  provider: string;
  provider_price_id: string | null;
  currency: string;
  amount_cents: number;
  interval: string;
  interval_count: number;
  is_public: boolean;
  is_active: boolean;
  created_at: string;
  retired_at: string | null;
}

export interface CapabilityDefOut {
  id: string;
  key: string;
  value_type: "boolean" | "integer" | "string" | "enum";
  description: string | null;
  allowed_values: string[] | null;
}

export interface PlanStatsOut {
  plan_id: string;
  paid_subscriptions: number;
  gifted: number;
  promotions: number;
  trials: number;
  legacy_entitlements: number;
}

export interface BundleOut {
  id: string;
  slug: string;
  name: string;
  status: string;
}

export interface RevenueMetricsOut {
  scope: { product_id: string | null; plan_id: string | null; start: string | null; end: string | null };
  revenue_cents: number;
  refunded_cents: number;
  net_revenue_cents: number;
  paid_subscribers: number;
  mrr_cents: number | null;
  arr_cents: number | null;
  arpu_cents: number | null;
  churn_rate: number | null;
  notes: string[];
}

export interface SystemHealthOut {
  database: boolean;
  signing_key_configured: boolean;
  outbox: { pending: number; failed: number };
  billing_webhooks: { pending: number; failed: number };
}

export const catalogApi = {
  listPlans: (productId: string) => request<CatalogPlanOut[]>(`/api/v1/admin/catalog/products/${productId}/plans`),
  createPlan: (productId: string, payload: Partial<CatalogPlanOut> & { slug: string; name: string }) =>
    request<CatalogPlanOut>(`/api/v1/admin/catalog/products/${productId}/plans`, { method: "POST", body: JSON.stringify(payload) }),
  updatePlan: (planId: string, payload: Record<string, unknown>) =>
    request<CatalogPlanOut>(`/api/v1/admin/catalog/plans/${planId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  archivePlan: (planId: string) => request<CatalogPlanOut>(`/api/v1/admin/catalog/plans/${planId}/archive`, { method: "POST" }),
  activatePlan: (planId: string) => request<CatalogPlanOut>(`/api/v1/admin/catalog/plans/${planId}/activate`, { method: "POST" }),
  planStats: (planId: string) => request<PlanStatsOut>(`/api/v1/admin/catalog/plans/${planId}/stats`),

  listVersions: (planId: string) => request<PlanVersionOut[]>(`/api/v1/admin/catalog/plans/${planId}/versions`),
  publishVersion: (planId: string) => request<PlanVersionOut>(`/api/v1/admin/catalog/plans/${planId}/versions`, { method: "POST" }),

  listPrices: (planId: string) => request<PriceOut[]>(`/api/v1/admin/catalog/plans/${planId}/prices`),
  createPrice: (planId: string, payload: { provider: string; currency: string; amount_cents: number; interval: string; interval_count?: number; provider_price_id?: string; is_public?: boolean }) =>
    request<PriceOut>(`/api/v1/admin/catalog/plans/${planId}/prices`, { method: "POST", body: JSON.stringify(payload) }),
  retirePrice: (priceId: string, reason?: string) =>
    request<PriceOut>(`/api/v1/admin/catalog/prices/${priceId}/retire`, { method: "POST", body: JSON.stringify({ reason }) }),
  setPriceVisibility: (priceId: string, is_public: boolean) =>
    request<PriceOut>(`/api/v1/admin/catalog/prices/${priceId}/visibility`, { method: "PATCH", body: JSON.stringify({ is_public }) }),

  listCapabilities: (productId: string) => request<CapabilityDefOut[]>(`/api/v1/admin/products/${productId}/capabilities`),
  defineCapability: (productId: string, payload: { key: string; value_type: string; description?: string; allowed_values?: string[] }) =>
    request<CapabilityDefOut>(`/api/v1/admin/products/${productId}/capabilities`, { method: "POST", body: JSON.stringify(payload) }),
  getPlanCapabilities: (planId: string) => request<Record<string, boolean | number | string>>(`/api/v1/admin/plans/${planId}/capabilities`),
  setPlanCapability: (planId: string, key: string, value: boolean | number | string) =>
    request<{ plan_id: string; key: string; value: unknown }>(`/api/v1/admin/plans/${planId}/capabilities/${key}`, { method: "PUT", body: JSON.stringify({ value }) }),
};

export const bundlesApi = {
  list: () => request<BundleOut[]>("/api/v1/admin/bundles"),
  create: (slug: string, name: string) => request<BundleOut>("/api/v1/admin/bundles", { method: "POST", body: JSON.stringify({ slug, name }) }),
  get: (bundleId: string) => request<BundleOut & { products: Array<{ product_id: string; plan_id: string }> }>(`/api/v1/admin/bundles/${bundleId}`),
  addProduct: (bundleId: string, productId: string, planSlug: string) =>
    request(`/api/v1/admin/bundles/${bundleId}/products`, { method: "POST", body: JSON.stringify({ product_id: productId, plan_slug: planSlug }) }),
  grantAccess: (userId: string, bundleId: string, source: string) =>
    request(`/api/v1/admin/users/${userId}/bundles/${bundleId}/access`, { method: "POST", body: JSON.stringify({ source }) }),
};

export const revenueApi = {
  metrics: (params: { product_id?: string; plan_id?: string; start?: string; end?: string }) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][]).toString();
    return request<RevenueMetricsOut>(`/api/v1/admin/revenue/metrics${qs ? `?${qs}` : ""}`);
  },
};

export const systemHealthApi = {
  get: () => request<SystemHealthOut>("/api/v1/admin/system-health"),
};

export const subscriptionsApi = {
  list: (params: { user_id?: string } = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][]).toString();
    return request<Array<{ id: string; user_id: string; product_id: string; provider: string; status: string; current_period_end: string | null; cancel_at_period_end: boolean }>>(`/api/v1/admin/subscriptions${qs ? `?${qs}` : ""}`);
  },
};

export const paymentsApi = {
  list: (params: { user_id?: string } = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][]).toString();
    return request<Array<{ id: string; user_id: string; product_id: string; provider: string; amount_cents: number; currency: string; status: string; refunded_amount_cents: number | null; created_at: string }>>(`/api/v1/admin/payments${qs ? `?${qs}` : ""}`);
  },
};

export const billingEventsApi = {
  list: (status?: string) => request<Array<{ id: string; provider: string; event_type: string; status: string; failure_reason: string | null; retry_count: number; received_at: string }>>(`/api/v1/admin/billing/webhooks${status ? `?status=${status}` : ""}`),
  replay: (id: string) => request(`/api/v1/admin/billing/webhooks/${id}/replay`, { method: "POST" }),
};

export const api = {
  login: (email: string, password: string) =>
    request<CurrentUser>("/api/v1/auth/login", { method: "POST", body: JSON.stringify({ email, password, remember_me: true }) }),
  me: () => request<CurrentUser>("/api/v1/auth/me"),
  logout: () => request<void>("/api/v1/auth/logout", { method: "POST" }),

  overview: () => request<AdminOverviewOut>("/api/v1/admin/overview"),
  listUsers: (q?: string) => request<AdminUserOut[]>(`/api/v1/admin/users${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  getUser: (id: string) => request<AdminUserOut>(`/api/v1/admin/users/${id}`),
  getUserMemberships: (id: string) =>
    request<Array<{ product_id: string; status: string; first_seen_at: string; last_seen_at: string }>>(
      `/api/v1/admin/users/${id}/memberships`
    ),
  getUserEntitlements: (id: string) => request<EntitlementView[]>(`/api/v1/admin/users/${id}/entitlements`),
  getUserAuditLog: (id: string) => request<AuditLogOut[]>(`/api/v1/admin/users/${id}/audit-log`),
  setUserStatus: (id: string, status: "active" | "disabled") =>
    request<AdminUserOut>(`/api/v1/admin/users/${id}/status`, { method: "PATCH", body: JSON.stringify({ status }) }),
  assignRole: (id: string, role_slug: string, scope: string) =>
    request<AdminUserOut>(`/api/v1/admin/users/${id}/roles`, { method: "POST", body: JSON.stringify({ role_slug, scope }) }),
  revokeRole: (id: string, role_slug: string, scope: string) =>
    request<AdminUserOut>(`/api/v1/admin/users/${id}/roles`, { method: "DELETE", body: JSON.stringify({ role_slug, scope }) }),

  listProducts: () => request<ProductOut[]>("/api/v1/admin/products"),
  createProduct: (payload: { id: string; name: string; domain: string; status: string }) =>
    request<ProductOut>("/api/v1/admin/products", { method: "POST", body: JSON.stringify(payload) }),
  onboardProduct: (payload: ProductOnboardRequest) =>
    request<ProductOnboardResponse>("/api/v1/admin/products/onboard", { method: "POST", body: JSON.stringify(payload) }),
  listClients: () => request<OAuthClientOut[]>("/api/v1/admin/clients"),
  rotateClientSecret: (clientId: string) =>
    request<{ client_id: string; client_secret: string }>(`/api/v1/admin/clients/${clientId}/rotate-secret`, { method: "POST" }),
  listPlans: (productId: string) => request<Array<{ id: string; slug: string; name: string }>>(`/api/v1/admin/products/${productId}/plans`),
  createPlan: (productId: string, slug: string, name: string) =>
    request<{ id: string; slug: string; name: string }>(
      `/api/v1/admin/products/${productId}/plans?slug=${encodeURIComponent(slug)}&name=${encodeURIComponent(name)}`,
      { method: "POST" }
    ),

  listGiftedAccess: () => request<GiftedAccessRow[]>("/api/v1/admin/gifted-access"),
  grantEntitlement: (userId: string, payload: { product_id: string; plan_slug: string; source: string; reason?: string }) =>
    request<{ id: string; status: string; source: string }>(`/api/v1/admin/users/${userId}/entitlements`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  revokeEntitlement: (userId: string, productId: string, reason?: string) =>
    request<{ revoked: boolean }>(`/api/v1/admin/users/${userId}/entitlements/${productId}`, {
      method: "DELETE",
      body: JSON.stringify({ reason }),
    }),

  auditLog: (limit = 100) => request<AuditLogOut[]>(`/api/v1/admin/audit-log?limit=${limit}`),
};
