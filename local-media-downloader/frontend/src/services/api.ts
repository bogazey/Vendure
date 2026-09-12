import type {
  AnalyzeResponse,
  AppSettings,
  CreateDownloadRequest,
  DownloadJobOut,
  GuestQuotaOut,
  HealthResponse,
  HistoryRecordOut,
  UpdateSettingsRequest,
  ValidateFolderResponse,
} from "../types/api";
import type {
  AccountOut,
  AdminActionLogOut,
  AdminAdPlacementOut,
  AdminBillingEventOut,
  AdminHealthOut,
  AdminOverviewOut,
  AdminUpdateAdPlacementRequest,
  AdminUserListOut,
  AdminUserOut,
  AdPlacementOut,
  BillingPeriod,
  PaymentHistory,
  PaymentCheckout,
  CheckoutResponse,
  DownloadPreferencesOut,
  Plan,
  UpdateDownloadPreferencesRequest,
  UserOut,
} from "../types/commercial";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.DEV ? "http://127.0.0.1:8000" : "");

export const downloadFileUrl = (id: string) => `${API_BASE}/api/downloads/${encodeURIComponent(id)}/file`;

// A temporary, invisible same-origin-navigating <a> - not window.open() (which
// popup blockers can kill) and not a fetch-into-Blob (which would pull large
// media files fully into JS memory first). The endpoint already responds
// with a Content-Disposition: attachment header (see routes_downloads.py's
// FileResponse), so the browser downloads it directly; the auth cookie rides
// along exactly as it does for the existing manual download link, since this
// is just a normal top-level GET navigation under the hood.
export const triggerFileDownload = (id: string): void => {
  const anchor = document.createElement("a");
  anchor.href = downloadFileUrl(id);
  anchor.rel = "noopener";
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
};

export class ApiError extends Error {
  technical?: string | null;
  code?: string | null;
  status: number;

  constructor(message: string, status: number, technical?: string | null, code?: string | null) {
    super(message);
    this.status = status;
    this.technical = technical;
    this.code = code;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      // Auth is httpOnly-cookie based (never localStorage/JS-readable
      // tokens), so every request - including cross-origin dev requests to
      // :8000 from the :5173 Vite server - must carry credentials.
      credentials: "include",
      headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    });
  } catch {
    throw new ApiError("Could not reach the local backend. Is it running?", 0);
  }

  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    let technical: string | undefined;
    let code: string | undefined;
    try {
      const body = await response.json();
      message = body.message || message;
      technical = body.technical;
      code = body.code;
    } catch {
      // ignore parse errors, use default message
    }
    throw new ApiError(message, response.status, technical, code);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<HealthResponse>("/api/health"),

  analyze: (url: string) =>
    request<AnalyzeResponse>("/api/analyze", { method: "POST", body: JSON.stringify({ url }) }),

  createDownload: (payload: CreateDownloadRequest) =>
    request<DownloadJobOut>("/api/downloads", { method: "POST", body: JSON.stringify(payload) }),

  listDownloads: () => request<DownloadJobOut[]>("/api/downloads"),

  cancelDownload: (id: string) => request<DownloadJobOut>(`/api/downloads/${id}/cancel`, { method: "POST" }),

  retryDownload: (id: string) => request<DownloadJobOut>(`/api/downloads/${id}/retry`, { method: "POST" }),

  getGuestQuota: () => request<GuestQuotaOut>("/api/downloads/guest-quota"),

  listHistory: (params: { search?: string; platform?: string; status?: string; order?: string }) => {
    const query = new URLSearchParams();
    if (params.search) query.set("search", params.search);
    if (params.platform) query.set("platform", params.platform);
    if (params.status) query.set("status", params.status);
    if (params.order) query.set("order", params.order);
    const qs = query.toString();
    return request<HistoryRecordOut[]>(`/api/history${qs ? `?${qs}` : ""}`);
  },

  deleteHistoryRecord: (id: string, deleteFile: boolean) =>
    request<void>(`/api/history/${id}?delete_file=${deleteFile}`, { method: "DELETE" }),

  clearHistory: (deleteFiles: boolean) =>
    request<void>("/api/history/clear", { method: "POST", body: JSON.stringify({ delete_files: deleteFiles }) }),

  getSettings: () => request<AppSettings>("/api/settings"),

  updateSettings: (patch: UpdateSettingsRequest) =>
    request<AppSettings>("/api/settings", { method: "PUT", body: JSON.stringify(patch) }),

  openPath: (path: string) => request<void>("/api/fs/open", { method: "POST", body: JSON.stringify({ path }) }),

  openContainingFolder: (path: string) =>
    request<void>("/api/fs/open-folder", { method: "POST", body: JSON.stringify({ path }) }),

  validateFolder: (path: string) =>
    request<ValidateFolderResponse>("/api/fs/validate-folder", {
      method: "POST",
      body: JSON.stringify({ path }),
    }),

  // --- Auth ---
  signup: (email: string, password: string) =>
    request<UserOut>("/api/auth/signup", { method: "POST", body: JSON.stringify({ email, password }) }),

  login: (email: string, password: string) =>
    request<UserOut>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),

  logout: () => request<void>("/api/auth/logout", { method: "POST" }),

  me: () => request<UserOut>("/api/auth/me"),

  forgotPassword: (email: string) =>
    request<void>("/api/auth/forgot-password", { method: "POST", body: JSON.stringify({ email }) }),

  resetPassword: (token: string, newPassword: string) =>
    request<void>("/api/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({ token, new_password: newPassword }),
    }),

  resendVerification: () => request<void>("/api/auth/resend-verification", { method: "POST" }),

  verifyEmail: (token: string) =>
    request<void>("/api/auth/verify-email", { method: "POST", body: JSON.stringify({ token }) }),

  // --- Account / billing ---
  getAccount: () => request<AccountOut>("/api/account"),

  // Per-user - never shared with any other account. See types/commercial.ts.
  getDownloadPreferences: () => request<DownloadPreferencesOut>("/api/account/download-preferences"),

  updateDownloadPreferences: (patch: UpdateDownloadPreferencesRequest) =>
    request<DownloadPreferencesOut>("/api/account/download-preferences", {
      method: "PUT",
      body: JSON.stringify(patch),
    }),

  createCheckout: (plan: Plan, billingPeriod: BillingPeriod) =>
    request<CheckoutResponse>("/api/billing/checkout", {
      method: "POST",
      body: JSON.stringify({ plan, billing_period: billingPeriod }),
    }),

  manageSubscription: (action: "cancel" | "resume" | "change-plan", plan?: Plan, period?: BillingPeriod) =>
    request<{ status: string }>(`/api/billing/subscription/${action}`, {
      method: "POST", body: plan ? JSON.stringify({ plan, billing_period: period }) : undefined,
    }),
  updatePaymentMethod: () => request<PaymentCheckout>("/api/billing/payment-method", { method: "POST" }),
  paymentHistory: (after?: string) => request<PaymentHistory>(`/api/billing/history${after ? `?after=${encodeURIComponent(after)}` : ""}`),
  invoice: (id: string) => request<{ url: string }>(`/api/billing/history/${encodeURIComponent(id)}/invoice`),

  // --- Admin ---
  adminListUsers: (params: { search?: string; limit?: number; offset?: number } = {}) => {
    const query = new URLSearchParams();
    if (params.search) query.set("search", params.search);
    if (params.limit) query.set("limit", String(params.limit));
    if (params.offset) query.set("offset", String(params.offset));
    const qs = query.toString();
    return request<AdminUserListOut>(`/api/admin/users${qs ? `?${qs}` : ""}`);
  },

  adminGrantCredits: (userId: string, credits: number, reason: string) =>
    request<AdminUserOut>(`/api/admin/users/${userId}/grant-credits`, {
      method: "POST",
      body: JSON.stringify({ credits, reason }),
    }),

  adminSetAccountStatus: (userId: string, status: "active" | "disabled") =>
    request<AdminUserOut>(`/api/admin/users/${userId}/status`, {
      method: "POST",
      body: JSON.stringify({ status }),
    }),

  adminListBillingEvents: (limit = 50) =>
    request<AdminBillingEventOut[]>(`/api/admin/billing-events?limit=${limit}`),

  adminGetOverview: () => request<AdminOverviewOut>("/api/admin/overview"),

  adminGetHealth: () => request<AdminHealthOut>("/api/admin/health"),

  adminGetUser: (userId: string) => request<AdminUserOut>(`/api/admin/users/${userId}`),

  adminListAuditLog: (params: { limit?: number; targetUserId?: string } = {}) => {
    const query = new URLSearchParams();
    if (params.limit) query.set("limit", String(params.limit));
    if (params.targetUserId) query.set("target_user_id", params.targetUserId);
    const qs = query.toString();
    return request<AdminActionLogOut[]>(`/api/admin/audit-log${qs ? `?${qs}` : ""}`);
  },

  // --- Ads ---
  listAdPlacements: () => request<AdPlacementOut[]>("/api/ads/placements"),

  adminListAdPlacements: () => request<AdminAdPlacementOut[]>("/api/admin/ads/placements"),

  adminUpdateAdPlacement: (placementId: string, payload: AdminUpdateAdPlacementRequest) =>
    request<AdminAdPlacementOut>(`/api/admin/ads/placements/${placementId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
};

export const PROGRESS_STREAM_URL = `${API_BASE}/api/progress/stream`;
