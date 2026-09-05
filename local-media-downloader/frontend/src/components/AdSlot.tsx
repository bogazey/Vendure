import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../context/AuthContext";
import { api } from "../services/api";
import type { AdPlacementName, AdPlacementOut } from "../types/commercial";

/**
 * Architecture-only placeholder for a future real ad network integration -
 * no ad network is wired up (see admin Ads page / ad_placement_service).
 * Renders nothing for signed-out visitors (ads only apply once a plan is
 * known), nothing once features.ads_enabled is false (Pro/Creator), and
 * nothing while the placement itself is disabled in /admin/ads. Never a
 * fake button, popunder, or redirect - just a clearly-labeled placeholder
 * box reserving the layout space a real slot will occupy later, whether or
 * not a provider has been configured yet.
 */
export default function AdSlot({ placement }: { placement: AdPlacementName }) {
  const { t } = useTranslation();
  const { account } = useAuth();
  const eligible = !!account?.features.ads_enabled;
  const [config, setConfig] = useState<AdPlacementOut | null>(null);

  useEffect(() => {
    if (!eligible) return;
    let cancelled = false;
    api
      .listAdPlacements()
      .catch(() => [])
      .then((placements) => {
        if (!cancelled) setConfig(placements.find((p) => p.id === placement) ?? null);
      });
    return () => {
      cancelled = true;
    };
  }, [eligible, placement]);

  if (!eligible || !config?.enabled) return null;

  return (
    <div className="flex items-center justify-center rounded-2xl border border-dashed border-white/10 bg-white/[0.02] px-4 py-6 text-xs text-slate-500 backdrop-blur-xl">
      <span data-placement={placement}>{t("app.ad")}</span>
    </div>
  );
}
