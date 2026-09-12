import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { adminPageShell } from "../../styles/ui";

const TABS = [
  { to: "/admin", end: true, key: "overview" },
  { to: "/admin/statistics", end: false, key: "statistics" },
  { to: "/admin/users", end: false, key: "users" },
  { to: "/admin/billing", end: false, key: "billing" },
  { to: "/admin/activity", end: false, key: "activity" },
  { to: "/admin/system", end: false, key: "system" },
  { to: "/admin/ads", end: false, key: "ads" },
] as const;

/**
 * Shared chrome for every admin section: page heading + a compact tab strip
 * (Overview/Users/Billing/Activity/System) rather than a second nested
 * sidebar - the primary app Sidebar already owns top-level navigation, this
 * just switches between admin sub-views within that one "Admin" destination.
 */
export default function AdminLayout({ children }: { children: ReactNode }) {
  const { t } = useTranslation();

  const tabClass = ({ isActive }: { isActive: boolean }) =>
    `rounded-full px-3.5 py-1.5 text-sm font-medium transition-colors ${
      isActive ? "bg-white/[0.08] text-slate-50" : "text-slate-400 hover:text-slate-100"
    }`;

  return (
    <div className={adminPageShell}>
      <div className="flex flex-col gap-4">
        <div>
          <h1 className="font-display text-xl font-bold text-slate-50">{t("admin.title")}</h1>
          <p className="text-sm text-slate-500">{t("admin.subtitle")}</p>
        </div>
        <nav
          aria-label={t("admin.nav.label")}
          className="flex w-full flex-wrap items-center gap-1 rounded-full border border-white/10 bg-white/[0.03] p-1 backdrop-blur-xl sm:w-fit"
        >
          {TABS.map((tab) => (
            <NavLink key={tab.to} to={tab.to} end={tab.end} className={tabClass}>
              {t(`admin.nav.${tab.key}`)}
            </NavLink>
          ))}
        </nav>
      </div>
      {children}
    </div>
  );
}
