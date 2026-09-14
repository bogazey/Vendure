// `??` (not `||`): an explicitly empty VITE_PLATFORM_API_BASE_URL means
// "same-origin" and must NOT fall through to the localhost dev default -
// only a genuinely unset (`undefined`) build-time value should do that.
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
  pending_new_email: string | null;
}

export interface Membership {
  product_id: string;
  status: string;
  first_seen_at: string;
  last_seen_at: string;
}

export interface EntitlementView {
  product_id: string;
  plan_slug: string | null;
  plan_name: string | null;
  source: string;
  status: string;
  starts_at: string;
  expires_at: string | null;
}

export interface ProductOut {
  id: string;
  name: string;
  domain: string;
  status: string;
  icon_ref: string | null;
}

export interface SubscriptionOut {
  id: string;
  product_id: string;
  provider: string;
  status: string;
  current_period_start: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
}

export interface SessionOut {
  id: string;
  device_label: string | null;
  created_at: string;
  last_used_at: string;
  expires_at: string;
  is_current: boolean;
}

export interface SecurityEvent {
  action: string;
  created_at: string;
  target_type: string;
}

export interface ClosureRequest {
  id: string;
  status: string;
  reason: string | null;
  requested_at: string;
  confirmed_at: string | null;
}

export const api = {
  signup: (email: string, password: string) =>
    request<CurrentUser>("/api/v1/auth/signup", { method: "POST", body: JSON.stringify({ email, password }) }),
  login: (email: string, password: string) =>
    request<CurrentUser>("/api/v1/auth/login", { method: "POST", body: JSON.stringify({ email, password, remember_me: true }) }),
  me: () => request<CurrentUser>("/api/v1/auth/me"),
  logout: () => request<void>("/api/v1/auth/logout", { method: "POST" }),
  logoutAll: () => request<void>("/api/v1/auth/logout-all", { method: "POST" }),
  changePassword: (current_password: string, new_password: string, revoke_other_sessions: boolean) =>
    request<void>("/api/v1/auth/change-password", {
      method: "POST",
      body: JSON.stringify({ current_password, new_password, revoke_other_sessions }),
    }),
  requestEmailChange: (new_email: string) =>
    request<void>("/api/v1/auth/request-email-change", { method: "POST", body: JSON.stringify({ new_email }) }),

  sessions: () => request<SessionOut[]>("/api/v1/auth/sessions"),
  revokeSession: (id: string) => request<void>(`/api/v1/auth/sessions/${id}`, { method: "DELETE" }),

  myMemberships: () => request<Membership[]>("/api/v1/me/memberships"),
  myEntitlements: () => request<EntitlementView[]>("/api/v1/me/entitlements"),
  mySecurityEvents: () => request<SecurityEvent[]>("/api/v1/me/security-events"),
  listProducts: () => request<ProductOut[]>("/api/v1/products"),
  mySubscriptions: () => request<SubscriptionOut[]>("/api/v1/billing/subscriptions/me"),

  closureStatus: () => request<ClosureRequest | null>("/api/v1/account/closure"),
  requestClosure: (reason?: string) => request<ClosureRequest>("/api/v1/account/closure", { method: "POST", body: JSON.stringify({ reason }) }),
  confirmClosure: (id: string) => request<ClosureRequest>(`/api/v1/account/closure/${id}/confirm`, { method: "POST" }),
  cancelClosure: (id: string) => request<ClosureRequest>(`/api/v1/account/closure/${id}/cancel`, { method: "POST" }),
};
