const API_BASE = import.meta.env.VITE_PLATFORM_API_BASE_URL || "http://localhost:8100";

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
  created_at: string;
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
