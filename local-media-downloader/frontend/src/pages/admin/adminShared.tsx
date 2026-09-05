import type { AdminActionType } from "../../types/commercial";

/** Small colored status dot - same visual language as the old header health
 * pill, reused here since that's exactly what this replaces. */
export function HealthDot({ ok }: { ok: boolean }) {
  return (
    <span
      className={`inline-block h-1.5 w-1.5 rounded-full ${ok ? "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.8)]" : "bg-amber-400"}`}
      aria-hidden
    />
  );
}

const ACTION_LABEL_KEYS: Record<AdminActionType, string> = {
  grant_credits: "admin.activity.grantCredits",
  disable_account: "admin.activity.disableAccount",
  reactivate_account: "admin.activity.reactivateAccount",
};

export function actionLabelKey(action: AdminActionType): string {
  return ACTION_LABEL_KEYS[action] ?? action;
}

export type BillingOutcomeTone = "success" | "failure" | "neutral";

/** Maps a Paddle event_type to a human payment/business outcome, kept
 * strictly separate from BillingEvent.status (the webhook's own processing
 * result - "processed"/"ignored"/"failed"). A webhook can be successfully
 * "processed" while the underlying payment failed, so the two must never
 * share one badge/color. */
const BILLING_OUTCOMES: Record<string, { key: string; tone: BillingOutcomeTone }> = {
  "transaction.completed": { key: "admin.billing.outcomeCompleted", tone: "success" },
  "transaction.payment_failed": { key: "admin.billing.outcomeFailed", tone: "failure" },
  "subscription.created": { key: "admin.billing.outcomeCreated", tone: "neutral" },
  "subscription.activated": { key: "admin.billing.outcomeActivated", tone: "success" },
  "subscription.updated": { key: "admin.billing.outcomeUpdated", tone: "neutral" },
  "subscription.canceled": { key: "admin.billing.outcomeCanceled", tone: "neutral" },
  "subscription.paused": { key: "admin.billing.outcomePaused", tone: "neutral" },
  "subscription.resumed": { key: "admin.billing.outcomeResumed", tone: "success" },
};

export function billingOutcome(eventType: string): { key: string; tone: BillingOutcomeTone } {
  return BILLING_OUTCOMES[eventType] ?? { key: "admin.billing.outcomeUnknown", tone: "neutral" };
}

const OUTCOME_TONE_CLASS: Record<BillingOutcomeTone, string> = {
  success: "text-emerald-400",
  failure: "font-medium text-red-400",
  neutral: "text-slate-400",
};

export function billingOutcomeClass(tone: BillingOutcomeTone): string {
  return OUTCOME_TONE_CLASS[tone];
}

/** Placement identifiers are stable/technical (see backend AdPlacementId)
 * and stay LTR/untranslated wherever shown; their human label/description
 * are looked up here rather than trusting the backend's English-only
 * `description` field, so EN/AR both get a real translation. */
export function adPlacementLabelKey(placementId: string): string {
  return `admin.ads.placements.${placementId}.label`;
}

export function adPlacementDescriptionKey(placementId: string): string {
  return `admin.ads.placements.${placementId}.description`;
}
