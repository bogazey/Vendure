import type { ReactElement } from "react";
import { NavLink } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import LoadyLogo from "./LoadyLogo";

interface SidebarLink {
  to: string;
  label: string;
  icon: ReactElement;
}

function icon(d: string) {
  return (
    <svg viewBox="0 0 24 24" width={18} height={18} fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round">
      <path d={d} />
    </svg>
  );
}

const LINKS: SidebarLink[] = [
  { to: "/dashboard", label: "Download", icon: icon("M12 4v11m0 0-4-4m4 4 4-4M5 19h14") },
  { to: "/history", label: "My Downloads", icon: icon("M4 5h16M4 12h16M4 19h10") },
  { to: "/account", label: "Account", icon: icon("M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm-7 8a7 7 0 0 1 14 0") },
  { to: "/settings", label: "Settings", icon: icon("M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM4.5 12h1M18.5 12h1M12 4.5v1M12 18.5v1M6.5 6.5l.7.7M16.8 16.8l.7.7M6.5 17.5l.7-.7M16.8 7.2l.7-.7") },
  { to: "/billing", label: "Billing", icon: icon("M3 7h18v10H3zM3 10h18") },
];

/**
 * Left sidebar for the authenticated product shell - Loady's own app
 * (Dashboard/My Downloads/Account/Settings/Billing) uses a persistent
 * sidebar rather than the marketing top nav, per the master website
 * reference. Desktop only (lg+); mobile keeps the existing Header
 * hamburger drawer, which already lists the same links.
 */
export default function Sidebar() {
  const { account, logout } = useAuth();

  return (
    <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-white/[0.06] px-4 py-6 lg:flex">
      <NavLink to="/" className="mb-8 px-2">
        <LoadyLogo size={26} />
      </NavLink>

      <nav className="flex flex-1 flex-col gap-1">
        {LINKS.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-xl border-l-2 px-3 py-2.5 text-sm font-medium transition-colors ${
                isActive
                  ? "border-brand-purple bg-white/[0.06] text-slate-50"
                  : "border-transparent text-slate-400 hover:bg-white/[0.03] hover:text-slate-200"
              }`
            }
          >
            {link.icon}
            {link.label}
          </NavLink>
        ))}
        {account?.user.role === "admin" && (
          <NavLink
            to="/admin"
            className={({ isActive }) =>
              `mt-1 flex items-center gap-3 rounded-xl border-l-2 px-3 py-2.5 text-sm font-medium transition-colors ${
                isActive
                  ? "border-brand-purple bg-white/[0.06] text-slate-50"
                  : "border-transparent text-slate-400 hover:bg-white/[0.03] hover:text-slate-200"
              }`
            }
          >
            {icon("M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7l8-4Z")}
            Admin
          </NavLink>
        )}
      </nav>

      <button
        type="button"
        onClick={() => logout()}
        className="flex items-center gap-3 rounded-xl border-l-2 border-transparent px-3 py-2.5 text-left text-sm font-medium text-red-400 transition-colors hover:bg-red-500/10"
      >
        {icon("M9 5H6a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h3M16 15l4-3-4-3M20 12H9")}
        Sign out
      </button>
    </aside>
  );
}
