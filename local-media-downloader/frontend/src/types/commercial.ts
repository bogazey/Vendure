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
  plan: Plan;
  billing_period: BillingPeriod;
  custom_data: Record<string, unknown>;
}

export interface BillingPortalResponse {
  url: string | null;
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
  created_at: string;
}

export interface AdminUserListOut {
  users: AdminUserOut[];
  total: number;
}

export interface AdminBillingEventOut {
  provider_event_id: string;
  event_type: string;
  processed_at: string;
  status: string;
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
