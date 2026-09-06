export type Plan = "free" | "pro" | "creator";
export type BillingPeriod = "monthly" | "annual";
export type SubscriptionStatus = "trialing" | "active" | "past_due" | "paused" | "canceled" | "none";
export type UserRole = "user" | "admin";

export interface UserOut {
  id: string;
  email: string;
  email_verified: boolean;
  role: UserRole;
  status: string;
  created_at: string;
}

export interface PlanFeaturesOut {
  plan: Plan;
  max_resolution_height: number | null;
  can_use_4k: boolean;
  can_use_batch: boolean;
  can_use_advanced_formats: boolean;
  can_use_clip_range: boolean;
  can_use_browser_cookies: boolean;
  can_use_original_container: boolean;
  can_use_creator_tools: boolean;
  ads_enabled: boolean;
  queue_priority: number;
  monthly_credits: number | null;
  daily_free_downloads: number | null;
}

export interface UsageOut {
  plan: Plan;
  period_start: string;
  period_end: string;
  credits_included: number | null;
  credits_used: number;
  credits_remaining: number | null;
  daily_free_downloads_used: number | null;
  daily_free_downloads_remaining: number | null;
}

export interface SubscriptionOut {
  plan: Plan;
  status: SubscriptionStatus;
  billing_period: BillingPeriod | null;
  current_period_start: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
}

export interface AccountOut {
  user: UserOut;
  subscription: SubscriptionOut;
  usage: UsageOut;
  features: PlanFeaturesOut;
}

export interface CheckoutResponse {
  price_id: string;
  client_token: string;
  /** "sandbox" | "production" - drives Paddle.Environment.set(), never hardcoded client-side. */
  environment: string;
  plan: Plan;
  billing_period: BillingPeriod;
  custom_data: Record<string, unknown>;
}

export interface PaymentCheckout {
  transaction_id: string;
  client_token: string;
  environment: string;
}
export interface PaymentHistory {
  items: { id: string; date: string; status: string; total: string; currency: string; invoice_available: boolean }[];
  next: string | null;
}

// Per-user download preferences - deliberately NOT part of AppSettings
// (types/api.ts): those come from a global row shared by every account, and
// container_mode/cookie_source/cookie_file_path must never be. See
// COMMERCIAL_ARCHITECTURE.md for why this was split out.
export interface DownloadPreferencesOut {
  container_mode: "compatibility" | "original";
  cookie_source: "none" | "chrome" | "firefox" | "edge" | "safari" | "file";
  cookie_file_path: string | null;
}

export type UpdateDownloadPreferencesRequest = Partial<DownloadPreferencesOut>;

export interface AdminUserOut {
  id: string;
  email: string;
  status: string;
  role: UserRole;
  plan: Plan;
  subscription_status: SubscriptionStatus;
  credits_used: number;
  credits_included: number | null;
  /** Portion of credits_included beyond the plan's own base allocation
   * (i.e. cumulative admin grants this period) - null wherever
   * credits_included itself is null (Free plan). */
  credits_bonus: number | null;
  created_at: string;
}

export interface AdminUserListOut {
  users: AdminUserOut[];
  total: number;
}

export type AdminActionType = "grant_credits" | "disable_account" | "reactivate_account";

export interface AdminBillingEventOut {
  provider_event_id: string;
  event_type: string;
  processed_at: string;
  status: string;
  user_id: string | null;
  user_email: string | null;
}

export interface AdminActionLogOut {
  id: string;
  admin_id: string;
  admin_email: string | null;
  action: AdminActionType;
  target_user_id: string | null;
  target_email: string | null;
  details: Record<string, unknown>;
  created_at: string;
}

/** Admin System page health snapshot - deliberately excludes ffmpeg_path and
 * download_dir (see HealthResponse in types/api.ts): the admin panel must
 * never display absolute server filesystem paths. */
export interface AdminHealthOut {
  status: string;
  database_ok: boolean;
  ffmpeg_available: boolean;
  ytdlp_version: string | null;
  download_dir_writable: boolean;
}

export interface AdminOverviewOut {
  total_users: number;
  active_users: number;
  disabled_users: number;
  paid_subscribers: number;
  free_count: number;
  pro_count: number;
  creator_count: number;
  credits_consumed_current_period: number;
  recent_billing_failures: AdminBillingEventOut[];
  recent_admin_actions: AdminActionLogOut[];
}

/** Public, non-secret ad placement config - what AdSlot needs at runtime.
 * Never carries API keys or private ad network tokens. */
export type AdPlacementName = "LANDING_DOWNLOADER" | "DOWNLOAD_RESULT" | "USER_DASHBOARD" | "DOWNLOAD_HISTORY";

export interface AdPlacementOut {
  id: string;
  enabled: boolean;
  provider: string | null;
  public_slot_id: string | null;
}

export interface AdminAdPlacementOut extends AdPlacementOut {
  description: string;
  updated_at: string;
}

export interface AdminUpdateAdPlacementRequest {
  enabled?: boolean;
  provider?: string | null;
  public_slot_id?: string | null;
}

export const PLAN_LABELS: Record<Plan, string> = {
  free: "Free",
  pro: "Pro",
  creator: "Creator",
};

export const PLAN_PRICES: Record<"pro" | "creator", { monthly: number; annual: number }> = {
  pro: { monthly: 4.99, annual: 49 },
  creator: { monthly: 9.99, annual: 99 },
};
