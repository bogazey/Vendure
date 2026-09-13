import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../context/AuthContext";

const TABS = [
  { to: "/", key: "overview", end: true },
  { to: "/users", key: "users", end: false },
  { to: "/products", key: "products", end: false },
  { to: "/gifted-access", key: "giftedAccess", end: false },
  { to: "/audit-log", key: "auditLog", end: false },
] as const;

export default function AdminLayout() {
  const { t, i18n } = useTranslation();
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const toggleLanguage = () => {
    void i18n.changeLanguage(i18n.language === "ar" ? "en" : "ar");
  };

  const handleLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className="bg-aurora min-h-screen">
      <header className="border-b border-surface-border/60 bg-surface-raised/60 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-5 py-4 sm:px-8">
          <div>
            <p className="font-display text-lg font-bold tracking-tight text-slate-50">
              <span className="bg-brand-gradient bg-clip-text text-transparent">{t("app.title")}</span>
            </p>
            <p className="text-xs text-slate-500">{t("app.subtitle")}</p>
          </div>
          <div className="flex items-center gap-3 text-sm text-slate-300">
            <button type="button" onClick={toggleLanguage} className="btn-glass !px-3 !py-1.5 text-xs">
              {t("common.language")}
            </button>
            <span className="hidden sm:inline">{user?.email}</span>
            <button type="button" onClick={handleLogout} className="btn-glass !px-3 !py-1.5 text-xs">
              {t("common.signOut")}
            </button>
          </div>
        </div>
        <nav className="mx-auto flex max-w-7xl gap-1 overflow-x-auto px-5 pb-2 sm:px-8" aria-label="Grand Admin">
          {TABS.map((tab) => (
            <NavLink
              key={tab.key}
              to={tab.to}
              end={tab.end}
              className={({ isActive }) =>
                `whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                  isActive ? "bg-white/10 text-slate-50" : "text-slate-400 hover:text-slate-200"
                }`
              }
            >
              {t(`nav.${tab.key}`)}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-5 py-8 sm:px-8">
        <Outlet />
      </main>
    </div>
  );
}
