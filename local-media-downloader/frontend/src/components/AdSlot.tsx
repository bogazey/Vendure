import { useAuth } from "../context/AuthContext";
import { useTranslation } from "react-i18next";

type AdPlacement = "below-url-input" | "history-page" | "processing-state" | "post-download";

/**
 * Architecture-only placeholder for a future real ad network integration -
 * no ad network is wired up. Renders nothing for signed-out visitors (ads
 * only apply once a plan is known) and nothing once features.ads_enabled is
 * false (Pro/Creator, or a Free account not currently rated for ads). Never
 * a fake button, popunder, or redirect - just a clearly-labeled placeholder
 * box reserving the layout space a real slot will occupy later.
 */
export default function AdSlot({ placement }: { placement: AdPlacement }) {
  const { t } = useTranslation();
  const { account } = useAuth();
  if (!account || !account.features.ads_enabled) return null;

  return (
    <div className="flex items-center justify-center rounded-2xl border border-dashed border-white/10 bg-white/[0.02] px-4 py-6 text-xs text-slate-500 backdrop-blur-xl">
      <span data-placement={placement}>{t("app.ad")}</span>
    </div>
  );
}
