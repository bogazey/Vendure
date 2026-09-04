import { useAuth } from "../context/AuthContext";

type AdPlacement = "below-url-input" | "history-page" | "processing-state" | "post-download";

const PLACEMENT_LABEL: Record<AdPlacement, string> = {
  "below-url-input": "Sponsored",
  "history-page": "Sponsored",
  "processing-state": "Sponsored",
  "post-download": "Sponsored",
};

/**
 * Architecture-only placeholder for a future real ad network integration -
 * no ad network is wired up. Renders nothing for signed-out visitors (ads
 * only apply once a plan is known) and nothing once features.ads_enabled is
 * false (Pro/Creator, or a Free account not currently rated for ads). Never
 * a fake button, popunder, or redirect - just a clearly-labeled placeholder
 * box reserving the layout space a real slot will occupy later.
 */
export default function AdSlot({ placement }: { placement: AdPlacement }) {
  const { account } = useAuth();
  if (!account || !account.features.ads_enabled) return null;

  return (
    <div className="flex items-center justify-center rounded-lg border border-dashed border-surface-border bg-surface-raised/40 px-4 py-6 text-xs text-slate-500">
      <span>{PLACEMENT_LABEL[placement]} · Ad space reserved for Free plan — upgrade to Pro to remove ads</span>
    </div>
  );
}
