/**
 * Internal, privacy-conscious event hooks. No third-party vendor is wired up
 * - events are logged locally (dev console) only. Never pass a downloaded
 * URL, title, or any other media-identifying value as an event property.
 */
export type AnalyticsEvent =
  | "signup"
  | "login"
  | "pricing_view"
  | "checkout_started"
  | "subscription_activated"
  | "subscription_canceled"
  | "download_started"
  | "download_completed"
  | "download_failed"
  | "upgrade_prompt_shown";

export function track(event: AnalyticsEvent, props?: Record<string, string | number | boolean>): void {
  if (import.meta.env.DEV) {
    console.debug(`[analytics] ${event}`, props ?? {});
  }
}
