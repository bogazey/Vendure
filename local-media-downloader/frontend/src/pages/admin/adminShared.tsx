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
